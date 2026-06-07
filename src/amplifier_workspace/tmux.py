"""tmux utilities for amplifier-workspace: session management helpers."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amplifier_workspace.config import TmuxConfig

__all__ = [
    "SESSION_NAME_MAX",
    "session_name_from_path",
    "session_exists",
    "kill_session",
    "create_session",
    "attach_session",
]

SESSION_NAME_MAX: int = 32
_RESERVED_WINDOW_NAMES: frozenset[str] = frozenset({"amplifier", "shell"})


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


def session_name_from_path(workdir: Path) -> str:
    """Derive a tmux session name from a workspace directory path.

    Uses the directory's basename, sanitized for tmux compatibility:
    - Replaces spaces, colons, dots, and slashes with dashes
    - Collapses repeated dashes into a single dash
    - Strips leading/trailing dashes
    - Truncates to SESSION_NAME_MAX (32) characters
    """
    name = workdir.name  # handles trailing slashes correctly via Path.name

    # Replace disallowed characters with dashes
    name = re.sub(r"[ :./\\]", "-", name)

    # Collapse repeated dashes
    name = re.sub(r"-{2,}", "-", name)

    # Strip leading/trailing dashes
    name = name.strip("-")

    # Truncate to SESSION_NAME_MAX
    return name[:SESSION_NAME_MAX]


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


# Cross-platform clipboard tools, in preference order. Each entry is
# (binary_to_probe, full_command). First one found wins.
_CLIPBOARD_COMMANDS: tuple[tuple[str, str], ...] = (
    ("pbcopy", "pbcopy"),  # macOS
    ("wl-copy", "wl-copy"),  # Wayland
    ("xclip", "xclip -selection clipboard"),  # X11
    ("xsel", "xsel -ib"),  # X11
)


def _tmux_version() -> tuple[int, int] | None:
    """Return tmux's (major, minor) version, or None if it can't be determined.

    Parses output like ``tmux 3.3a`` or ``tmux next-3.4``. Mirrors the version
    parsing style used by doctor.py so behavior is consistent across the tool.
    """
    try:
        result = subprocess.run(
            ["tmux", "-V"], capture_output=True, text=True, timeout=5
        )
        match = re.search(r"(\d+)\.(\d+)", result.stdout or "")
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))
    except Exception:  # tmux missing, non-string stdout (mocks), parse error, etc.
        return None


def _resolve_clipboard_command() -> str | None:
    """Return the first available OS clipboard command, or None if none found."""
    for binary, command in _CLIPBOARD_COMMANDS:
        if shutil.which(binary):
            return command
    return None


def _set_option(name: str, option: str, value: str) -> None:
    """Run ``tmux set-option -t <name> <option> <value>``; never raises.

    Session-scoped: the ``-t <name>`` target means this affects ONLY this
    session, never the user's global config or other running sessions. A failure
    here must not abort session creation — the windows matter more than mouse
    mode — so all errors are logged to stderr and swallowed.
    """
    try:
        result = subprocess.run(
            ["tmux", "set-option", "-t", name, option, value],
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # tmux missing, OSError, etc.
        print(
            f"amplifier-workspace: could not set tmux option '{option}': {exc}",
            file=sys.stderr,
        )
        return
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        print(
            f"amplifier-workspace: tmux set-option {option} {value} failed"
            + (f": {detail}" if detail else ""),
            file=sys.stderr,
        )


def _apply_clipboard_binding(name: str) -> None:
    """Bind copy-mode MouseDragEnd to pipe the selection to the OS clipboard.

    OPT-IN ONLY (config.clipboard_binding). WARNING: tmux key bindings are
    SERVER-GLOBAL — this binding leaks into the user's other tmux sessions and
    persists for the tmux server's lifetime. It exists only for terminals that
    lack OSC-52 support (e.g. Apple Terminal.app). Failures are non-fatal.
    """
    command = _resolve_clipboard_command()
    if command is None:
        print(
            "amplifier-workspace: clipboard_binding enabled but no clipboard tool "
            "found (pbcopy/wl-copy/xclip/xsel); skipping binding",
            file=sys.stderr,
        )
        return
    for table in ("copy-mode", "copy-mode-vi"):
        try:
            subprocess.run(
                [
                    "tmux",
                    "bind-key",
                    "-T",
                    table,
                    "MouseDragEnd1Pane",
                    "send-keys",
                    "-X",
                    "copy-pipe-and-cancel",
                    command,
                ],
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            print(
                f"amplifier-workspace: could not bind clipboard in {table}: {exc}",
                file=sys.stderr,
            )


def _apply_session_options(name: str, config: "TmuxConfig") -> None:
    """Apply session-scoped mouse + clipboard options to a freshly-created session.

    All options are set with ``set-option -t <name>`` (session scope) so they
    NEVER modify the user's ~/.tmux.conf or any other running tmux session.
    Everything here is best-effort: option/binding failures are logged but do not
    abort session creation.
    """
    if config.mouse:
        # `mouse on` requires tmux >= 2.1. Older tmux uses the legacy
        # mode-mouse/mouse-* options; rather than guess, skip gracefully.
        version = _tmux_version()
        if version is not None and version < (2, 1):
            print(
                f"amplifier-workspace: tmux {version[0]}.{version[1]} < 2.1 — "
                "skipping 'mouse on' (mouse mode unavailable on this tmux)",
                file=sys.stderr,
            )
        else:
            _set_option(name, "mouse", "on")

    if config.set_clipboard:
        # set-clipboard makes tmux's default MouseDragEnd copy-and-cancel emit the
        # selection via OSC-52 — fixes the stuck highlight and system-clipboard
        # copy on OSC-52-capable terminals, with no global key-table changes.
        _set_option(name, "set-clipboard", "on")

    if config.clipboard_binding:
        _apply_clipboard_binding(name)


def create_session(workdir: Path, config: "TmuxConfig") -> None:
    """Create a new tmux session for the given workspace directory.

    Window creation order:
    1. amplifier window (always first) — uses resume-detection rcfile
    2. Shell window (second, if configured) — two-pane horizontal split
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

    # 1b) Apply session-scoped mouse + clipboard options immediately after the
    # session exists. These use `set-option -t <name>`, so they affect ONLY this
    # session — the user's ~/.tmux.conf and other tmux sessions are untouched.
    # Best-effort: failures here never abort session creation.
    _apply_session_options(name, config)

    # 2) Shell window (second, if configured) — create window then add a second pane via horizontal split
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
        subprocess.run(
            [
                "tmux",
                "split-window",
                "-h",
                "-t",
                f"{name}:shell",
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
