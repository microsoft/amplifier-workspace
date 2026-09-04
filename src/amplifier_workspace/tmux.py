"""tmux utilities for amplifier-workspace: session management helpers."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amplifier_workspace.config import TmuxConfig

__all__ = [
    "SESSION_NAME_MAX_FALLBACK",
    "SessionNameTooLongError",
    "session_name_max",
    "session_name_from_path",
    "session_exists",
    "kill_session",
    "create_session",
    "attach_session",
]

# ---------------------------------------------------------------------------
# Session-name length
# ---------------------------------------------------------------------------
#
# A session name is derived from the workspace *directory's* basename, so the
# only real ceiling is the filesystem's own per-component limit (NAME_MAX) --
# and NAME_MAX is counted in BYTES, not characters.
#
# Measured on the reference host (2026-09-04, tmux 3.4, ext4):
#
#   tmux   No session-name length limit found.  Names of 41, 64, 128, 200 and
#          255 characters each created rc=0 and round-tripped byte-exact via
#          `list-sessions`; a 255-BYTE multibyte name also worked.
#   ext4   NAME_MAX = 255 BYTES.  mkdir of 255 ASCII chars succeeds and 256
#          fails (ENAMETOOLONG); mkdir of 85 CJK chars (255 bytes) succeeds and
#          86 CJK chars (258 bytes) fails -- proving the limit counts bytes.
#
# So the cap is asked of the filesystem at call time rather than hardcoded.  The
# previous hardcoded 32 protected nothing: ~/dev on the reporting host already
# holds 41-character directories that tmux and ext4 both handle without
# complaint, while the cap silently renamed every session longer than 32.

SESSION_NAME_MAX_FALLBACK: int = 255
"""Cap in BYTES used only when the platform cannot report its own NAME_MAX.

This is *not* the applied cap -- :func:`session_name_max` is.  255 is the
per-component limit shared by ext4, APFS and NTFS, so it is the least
surprising value to assume when ``os.pathconf`` is unavailable (Windows) or
declines to answer.
"""

_RESERVED_WINDOW_NAMES: frozenset[str] = frozenset({"amplifier", "shell"})


class SessionNameTooLongError(ValueError):
    """Raised when a derived session name does not fit the filesystem's NAME_MAX.

    Subclasses ``ValueError`` so existing ``except ValueError`` handling still
    catches it, and so the CLI's top-level handler reports it as a plain
    ``error: ...`` line rather than a traceback.
    """


def attach_session(name: str) -> None:
    """Attach to or switch to a tmux session by name.

    Never returns on POSIX — the current process is replaced by tmux via os.execvp.

    Behavior:
    - Outside tmux (TMUX env var not set): execvp 'tmux attach-session -t <name>'
    - Inside tmux (TMUX env var set): execvp 'tmux switch-client -t <name>'

    On Windows (sys.platform == 'win32'), falls back to subprocess.run +
    sys.exit(result.returncode) since os.execvp is unavailable.
    """
    if sys.platform == "win32":
        if os.environ.get("TMUX"):
            result = subprocess.run(["tmux", "switch-client", "-t", name])
        else:
            result = subprocess.run(["tmux", "attach-session", "-t", name])
        sys.exit(result.returncode)
    else:
        if os.environ.get("TMUX"):
            os.execvp("tmux", ["tmux", "switch-client", "-t", name])
        else:
            os.execvp("tmux", ["tmux", "attach-session", "-t", name])


def _nearest_existing_dir(path: Path) -> Path | None:
    """Return *path* or its closest existing ancestor directory, else None."""
    for candidate in (path, *path.parents):
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return None


def session_name_max(path: Path | None = None) -> int:
    """Return the maximum session-name length in BYTES for *path*'s filesystem.

    Reads the real limit via ``os.pathconf(dir, "PC_NAME_MAX")`` on the nearest
    existing ancestor of *path*, because the workspace may live on a different
    filesystem than the root one.  Falls back to
    :data:`SESSION_NAME_MAX_FALLBACK` when the platform has no ``os.pathconf``
    (Windows), does not recognise the name, or reports an indeterminate limit.
    """
    probe = _nearest_existing_dir(path) if path is not None else None
    if probe is not None:
        try:
            reported = os.pathconf(probe, "PC_NAME_MAX")
        except (AttributeError, KeyError, ValueError, OSError):
            reported = -1
        if reported > 0:
            return int(reported)
    return SESSION_NAME_MAX_FALLBACK


def session_name_from_path(workdir: Path, *, name_max: int | None = None) -> str:
    """Derive a tmux session name from a workspace directory path.

    Uses the directory's basename, sanitized for tmux compatibility:
    - Replaces spaces, colons, dots, and slashes with dashes
    - Collapses repeated dashes into a single dash
    - Strips leading/trailing dashes

    The result is then checked -- in BYTES, since NAME_MAX counts bytes -- against
    the filesystem's own limit (see :func:`session_name_max`).  A name that does
    not fit raises :class:`SessionNameTooLongError`.

    There is deliberately **no truncation**.  Silently returning a name other
    than the caller's directory is the bug this replaces: callers build session
    keys from the name they asked for, so a quiet rename makes every downstream
    lookup miss.  Because a directory cannot exist unless its basename already
    fits NAME_MAX -- and sanitizing only ever replaces one ASCII byte with
    another, collapses, or strips -- the error is unreachable for a workspace
    that exists on disk.  It fires only for a path that could not have been
    created in the first place, and says so.

    *name_max* overrides the derived cap (in bytes).  Intended for tests and for
    callers that already know their own limit.
    """
    name = workdir.name  # handles trailing slashes correctly via Path.name

    # Replace disallowed characters with dashes
    name = re.sub(r"[ :./\\]", "-", name)

    # Collapse repeated dashes
    name = re.sub(r"-{2,}", "-", name)

    # Strip leading/trailing dashes
    name = name.strip("-")

    limit = session_name_max(workdir.parent) if name_max is None else name_max
    encoded_length = len(name.encode("utf-8"))
    if encoded_length > limit:
        raise SessionNameTooLongError(
            f"session name derived from {str(workdir)!r} is {encoded_length} bytes "
            f"({len(name)} characters), over this filesystem's {limit}-byte name "
            "limit (NAME_MAX). Rename the workspace directory to something shorter."
        )

    return name


def session_exists(name: str) -> bool:
    """Return True if a tmux session with the given name is running.

    Calls 'tmux has-session -t <name>' and checks the return code.
    Returns False if the session does not exist or tmux is not available.
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def kill_session(name: str) -> None:
    """Kill a tmux session if it exists.

    Calls session_exists(name) first; if the session is running, calls
    'tmux kill-session -t <name>' to terminate it. No-op if the session
    does not exist.
    """
    if session_exists(name):
        # ignore return code — session may have died between exists-check and kill
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


def _main_rcfile_content(workdir: Path) -> str:
    """Generate rcfile content for the amplifier window.

    Matches the proven working pattern from amplifier-cli-tools: source bashrc,
    cd to workdir, settle terminal, check for existing sessions, run amplifier.
    No 'exec' before amplifier — bash stays alive so the window drops to a
    prompt when amplifier exits.
    """
    quoted_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc 2>/dev/null
cd {quoted_workdir}
sleep 0.5
read -t 0.2 -n 10000 discard 2>/dev/null || true
session_output=$(amplifier session list 2>/dev/null)
if echo "$session_output" | grep -q "No sessions found"; then
    amplifier
elif echo "$session_output" | grep -q "Session ID"; then
    amplifier resume
else
    amplifier
fi
"""


def _shell_rcfile_content(workdir: Path) -> str:
    """Generate rcfile content for the shell window."""
    quoted_workdir = shlex.quote(str(workdir))
    return f"source ~/.bashrc 2>/dev/null\ncd {quoted_workdir}\n"


def _window_rcfile_content(workdir: Path, command: str) -> str:
    """Generate rcfile content for a tool window (lazygit, yazi, etc.).

    Does NOT use 'exec' before the command — bash stays alive so the window
    drops to a prompt when the tool exits, matching the amplifier-cli-tools pattern.
    """
    quoted_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc 2>/dev/null
cd {quoted_workdir}
{command}
"""


def _write_rcfiles(
    workdir: Path,
    config: "TmuxConfig",
    *,
    rcfile_base: Path | None = None,
) -> Path:
    """Write rcfiles for all configured windows and return the rcfile directory.

    If rcfile_base is None, defaults to /tmp/amplifier-workspace-rcfiles-{pid}.
    Always writes amplifier.rc and shell.rc. For each additional window in
    config.windows (skipping 'amplifier', 'shell', and empty commands), writes
    {window_name}.rc using _window_rcfile_content.
    All rcfiles are chmod 0o755.
    """
    if rcfile_base is None:
        rcfile_base = Path(f"/tmp/amplifier-workspace-rcfiles-{os.getpid()}")

    rcfile_base.mkdir(parents=True, exist_ok=True)

    amplifier_rc = rcfile_base / "amplifier.rc"
    amplifier_rc.write_text(_main_rcfile_content(workdir))
    amplifier_rc.chmod(0o755)

    shell_rc = rcfile_base / "shell.rc"
    shell_rc.write_text(_shell_rcfile_content(workdir))
    shell_rc.chmod(0o755)

    for window_name, command in config.windows.items():
        if window_name in _RESERVED_WINDOW_NAMES:
            continue
        if not command:
            continue
        window_rc = rcfile_base / f"{window_name}.rc"
        window_rc.write_text(_window_rcfile_content(workdir, command))
        window_rc.chmod(0o755)

    return rcfile_base


def create_session(workdir: Path, config: "TmuxConfig") -> None:
    """Create a new tmux session for the given workspace directory.

    Window creation order:
    1. amplifier window (always first) — uses resume-detection rcfile
    2. Shell window (second, if configured) — single pane
    3. Tool windows from config.windows (in order; skips amplifier/shell keys and empty commands)
    4. Selects amplifier window so it is focused on attach

    Calls _write_rcfiles(workdir, config) to generate all rcfiles before creating any windows.
    Session name is derived via session_name_from_path(workdir).
    """
    name = session_name_from_path(workdir)
    rcfile_base = _write_rcfiles(workdir, config)

    amplifier_rc = rcfile_base / "amplifier.rc"
    shell_rc = rcfile_base / "shell.rc"

    # 1) Create session with amplifier window as the first window
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            name,
            "-n",
            "amplifier",
            f"exec bash --rcfile {shlex.quote(str(amplifier_rc))}",
        ],
        check=True,
    )

    # 2) Shell window (second, if configured) — single pane
    if "shell" in config.windows:
        subprocess.run(
            [
                "tmux",
                "new-window",
                "-t",
                name,
                "-n",
                "shell",
                f"exec bash --rcfile {shlex.quote(str(shell_rc))}",
            ],
            check=True,
        )

    # 3) Tool windows in config.windows order (skip reserved names, skip empty commands)
    for window_name, command in config.windows.items():
        if window_name in _RESERVED_WINDOW_NAMES:
            continue
        if not command:
            continue
        window_rc = rcfile_base / f"{window_name}.rc"
        subprocess.run(
            [
                "tmux",
                "new-window",
                "-t",
                name,
                "-n",
                window_name,
                f"exec bash --rcfile {shlex.quote(str(window_rc))}",
            ],
            check=True,
        )

    # 4) Select amplifier window so it is focused on attach
    subprocess.run(
        ["tmux", "select-window", "-t", f"{name}:amplifier"],
        check=True,
    )
