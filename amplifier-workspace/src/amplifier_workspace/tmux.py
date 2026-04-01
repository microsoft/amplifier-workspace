"""tmux utilities for amplifier-workspace: session management helpers."""

from __future__ import annotations

import os  # noqa: F401  # available for future subprocess/path helpers
import re
import shlex
import subprocess
import tempfile  # noqa: F401  # available for future temp-file operations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amplifier_workspace.config import TmuxConfig  # noqa: F401  # used in type hints

__all__ = [
    "SESSION_NAME_MAX",
    "session_name_from_path",
    "session_exists",
    "kill_session",
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
    return (
        "source ~/.bashrc\n"
        f"cd {quoted_workdir}\n"
        "sleep 0.5\n"
        "read -t 0.1 -n 10000 _discard 2>/dev/null || true\n"
        "if amplifier session list 2>/dev/null | grep -q .; then\n"
        "    exec amplifier resume\n"
        "else\n"
        "    exec amplifier\n"
        "fi\n"
    )


def _shell_rcfile_content(workdir: Path) -> str:
    """Generate rcfile content for the shell window.

    Sources ~/.bashrc and cds to workdir, then drops to an interactive
    bash session (no exec command).
    """
    quoted_workdir = shlex.quote(str(workdir))
    return f"source ~/.bashrc\ncd {quoted_workdir}\n"
