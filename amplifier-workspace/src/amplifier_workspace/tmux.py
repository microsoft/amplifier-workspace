"""tmux utilities for amplifier-workspace: session management helpers."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amplifier_workspace.config import TmuxConfig

__all__ = [
    "SESSION_NAME_MAX",
    "session_name_from_path",
    "session_exists",
    "kill_session",
    "_main_rcfile_content",
    "_shell_rcfile_content",
    "_window_rcfile_content",
    "_write_rcfiles",
    "create_session",
]

SESSION_NAME_MAX: int = 32


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

    Sources ~/.bashrc, cds to workdir, adds a short sleep for terminal
    settling, discards stale input, then conditionally resumes an existing
    Amplifier session or starts a fresh one.
    """
    quoted_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc
cd {quoted_workdir}
sleep 0.5
read -t 0.1 -n 10000 _discard 2>/dev/null || true
if amplifier session list 2>/dev/null | grep -q .; then
    exec amplifier resume
else
    exec amplifier
fi
"""


def _shell_rcfile_content(workdir: Path) -> str:
    """Generate rcfile content for the shell window.

    Sources ~/.bashrc and cds to workdir, then drops to an interactive
    bash session (no exec command).
    """
    quoted_workdir = shlex.quote(str(workdir))
    return f"source ~/.bashrc\ncd {quoted_workdir}\n"


def _window_rcfile_content(workdir: Path, command: str) -> str:
    """Generate rcfile content for a tool window (lazygit, yazi, etc.).

    Sources ~/.bashrc, cds to workdir, sleeps 0.3 for terminal settling,
    then execs the given command.
    """
    quoted_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc
cd {quoted_workdir}
sleep 0.3
exec {command}
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
        if window_name in ("amplifier", "shell"):
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
    2. Tool windows from config.windows (in order; skips amplifier/shell keys and empty commands)
    3. Shell window (always last) — two-pane horizontal split
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

    # 2) Tool windows in config.windows order (skip amplifier/shell, skip empty commands)
    for window_name, command in config.windows.items():
        if window_name in ("amplifier", "shell"):
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

    # 3) Shell window (always last) — create window then add a second pane via horizontal split
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

    # 4) Select amplifier window so it is focused on attach
    subprocess.run(
        ["tmux", "select-window", "-t", f"{name}:amplifier"],
        check=True,
    )
