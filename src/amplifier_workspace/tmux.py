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
    "SessionNameEmptyError",
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

# ---------------------------------------------------------------------------
# The empty session name
# ---------------------------------------------------------------------------
#
# Sanitizing can consume a basename entirely: every character of `...`, `/`, `.`
# and `- ` maps to a dash, and the dashes are then collapsed and stripped away,
# leaving ``''``.  An empty name must never reach tmux.
#
# Measured on the reference host (2026-09-04, tmux 3.4), on a dedicated socket:
#
#   new-session -d -s ''    rc=1, "invalid session: ".  tmux REFUSES the name --
#                           it does not auto-number, as originally suspected.
#   has-session  -t ''      rc=0 -- an empty TARGET is not "no session", it
#                           resolves to the most recently used session.
#   kill-session -t ''      rc=0, and with sessions alpha/beta/gamma running it
#                           killed *gamma* -- a session this tool never created.
#   new-window   -t ''      rc=0, and the window landed in an unrelated session.
#
# So an empty name is not merely useless, it is dangerous: the create path dies
# with a CalledProcessError traceback, while every -t path silently retargets
# some *other* session -- `--kill` on a pathological workspace path would kill a
# bystander's session.  Hence: refuse the empty name in this module, loudly,
# before any tmux argv is built.

_RESERVED_WINDOW_NAMES: frozenset[str] = frozenset({"amplifier", "shell"})


class SessionNameTooLongError(ValueError):
    """Raised when a derived session name does not fit the filesystem's NAME_MAX.

    Subclasses ``ValueError`` so existing ``except ValueError`` handling still
    catches it, and so the CLI's top-level handler reports it as a plain
    ``error: ...`` line rather than a traceback.
    """


class SessionNameEmptyError(ValueError):
    """Raised when a path yields no usable session name at all.

    Subclasses ``ValueError`` for the same reason as
    :class:`SessionNameTooLongError`: the CLI's top-level handler prints one
    ``error: ...`` line and exits 1, no traceback.
    """


def _sanitize_session_name(raw: str) -> str:
    """Return *raw* reduced to a tmux-safe session name (possibly empty).

    Replaces spaces, colons, dots and slashes with dashes, collapses runs of
    dashes, and strips leading/trailing dashes.  Never lengthens the input, so
    it can never push a name over NAME_MAX.
    """
    name = re.sub(r"[ :./\\]", "-", raw)
    name = re.sub(r"-{2,}", "-", name)
    return name.strip("-")


def _require_session_name(name: str, operation: str) -> None:
    """Refuse an empty session name before it becomes a tmux target.

    tmux treats ``-t ''`` as "the most recently used session" rather than as no
    session at all, so passing an empty name through would operate on -- or
    kill -- a session this tool never created.  See the module comment above for
    the measured behaviour.
    """
    if not name:
        raise SessionNameEmptyError(
            f"refusing to {operation} with an empty tmux session name: tmux reads "
            "an empty target as the most recently used session, so this would act "
            "on an unrelated session."
        )


def attach_session(name: str) -> None:
    """Attach to or switch to a tmux session by name.

    Never returns on POSIX — the current process is replaced by tmux via os.execvp.

    Behavior:
    - Outside tmux (TMUX env var not set): execvp 'tmux attach-session -t <name>'
    - Inside tmux (TMUX env var set): execvp 'tmux switch-client -t <name>'

    On Windows (sys.platform == 'win32'), falls back to subprocess.run +
    sys.exit(result.returncode) since os.execvp is unavailable.

    Raises :class:`SessionNameEmptyError` for an empty *name*, which tmux would
    otherwise resolve to the most recently used session.
    """
    _require_session_name(name, "attach to a tmux session")
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

    Sanitizing can also consume the basename entirely -- ``.``, ``..``, ``/``
    and a directory literally named ``...`` all reduce to ``''``.  An empty name
    is never returned: the path is resolved first (which turns ``.`` and ``..``
    into the directory's real name), and if *that* still yields nothing the
    function raises :class:`SessionNameEmptyError` rather than handing tmux a
    name it would either reject or, worse, read as "the most recently used
    session".  See the module comment for the measured behaviour.

    *name_max* overrides the derived cap (in bytes).  Intended for tests and for
    callers that already know their own limit.
    """
    # Path.name handles trailing slashes correctly.
    name = _sanitize_session_name(workdir.name)

    if not name:
        # The basename carries no usable characters.  For a relative path that
        # is merely because the name is positional ('.', '..', ''), so ask the
        # filesystem what this directory is actually called before giving up --
        # that is the same directory, correctly named, not a substitute for it.
        try:
            resolved = workdir.resolve()
        except OSError:
            resolved = workdir
        name = _sanitize_session_name(resolved.name)

    if not name:
        raise SessionNameEmptyError(
            f"cannot derive a tmux session name from {str(workdir)!r}: its "
            "directory name is made up entirely of characters that are not "
            "allowed in a session name (space, colon, dot, slash), leaving "
            "nothing behind. Use a workspace directory with a name that "
            "contains at least one other character."
        )

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

    Raises :class:`SessionNameEmptyError` for an empty *name*: `has-session -t ''`
    returns 0 whenever *any* session is running, which would report a session
    this tool never created as existing.
    """
    _require_session_name(name, "look up a tmux session")
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

    Raises :class:`SessionNameEmptyError` for an empty *name*.  This is the
    destructive case: `kill-session -t ''` exits 0 and kills the most recently
    used session -- measured, on a host with unrelated sessions running.
    """
    _require_session_name(name, "kill a tmux session")
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
