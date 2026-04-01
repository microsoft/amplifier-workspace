"""Workspace lifecycle functions: scaffold files, set up git, launch amplifier."""

from __future__ import annotations

import importlib.resources
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

from amplifier_workspace.config import WorkspaceConfig
from amplifier_workspace import git as _git
from amplifier_workspace import tmux


# ---------------------------------------------------------------------------
# File scaffolding
# ---------------------------------------------------------------------------


def create_agents_md(workdir: Path, config: WorkspaceConfig) -> None:
    """Write AGENTS.md to *workdir* unless it already exists.

    Resolution order:
    1. Skip if AGENTS.md already exists (idempotent).
    2. Copy from ``config.agents_template`` if the path is set and exists.
    3. Warn and fall back to builtin if the custom path is set but missing.
    4. Use builtin template via importlib.resources.
    5. Last resort: write minimal placeholder content.
    """
    target = workdir / "AGENTS.md"
    if target.exists():
        return

    # Attempt custom template
    if config.agents_template:
        custom = Path(config.agents_template)
        if custom.exists():
            shutil.copy(custom, target)
            return
        warnings.warn(
            f"agents_template path does not exist: {config.agents_template!r}; "
            "falling back to builtin template.",
            stacklevel=2,
        )

    # Builtin template via importlib.resources
    try:
        pkg_file = (
            importlib.resources.files("amplifier_workspace") / "templates" / "AGENTS.md"
        )
        content = pkg_file.read_bytes().decode()
        target.write_text(content)
        return
    except Exception:
        warnings.warn(
            "Could not load builtin AGENTS.md template; writing minimal placeholder.",
            stacklevel=2,
        )
        pass

    # Last resort: minimal content
    target.write_text("# AGENTS.md\n\nWorkspace guidance for agents.\n")


def create_amplifier_settings(workdir: Path, config: WorkspaceConfig) -> None:
    """Write .amplifier/settings.yaml to *workdir* unless it already exists.

    Creates the ``.amplifier`` directory if needed.  Idempotent.
    """
    amplifier_dir = workdir / ".amplifier"
    settings_path = amplifier_dir / "settings.yaml"

    if settings_path.exists():
        return

    amplifier_dir.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(f"bundle:\n  active: {config.bundle}\n")


# ---------------------------------------------------------------------------
# Workspace orchestration
# ---------------------------------------------------------------------------


def setup_workspace(workdir: Path, config: WorkspaceConfig) -> None:
    """Set up a workspace directory.

    If *workdir* is not yet a git repository:
    - Initialise the repo.
    - Add configured repos as submodules.
    - Checkout submodules if any repos were specified.
    - Create an initial commit.

    Always (idempotently):
    - Write AGENTS.md (skipped if already present).
    - Write .amplifier/settings.yaml (skipped if already present).
    """
    workdir.mkdir(parents=True, exist_ok=True)

    if not _git.is_git_repo(workdir):
        _git.init_repo(workdir)
        for url in config.default_repos:
            _git.add_submodule(workdir, url)
        if config.default_repos:
            _git.checkout_submodules(workdir)
        _git.initial_commit(workdir, "chore: initialise workspace")

    create_agents_md(workdir, config)
    create_amplifier_settings(workdir, config)


# ---------------------------------------------------------------------------
# Amplifier launchers
# ---------------------------------------------------------------------------


def _launch_with_tmux(workdir: Path, config: WorkspaceConfig) -> None:
    """Create a tmux session for *workdir* and attach to it.

    Creates the session via ``tmux.create_session`` then attaches/switches to
    it via ``tmux.attach_session``.  On POSIX the current process is replaced
    by tmux; on Windows ``sys.exit`` is called after attach.
    """
    tmux.create_session(workdir, config.tmux)
    name = tmux.session_name_from_path(workdir)
    tmux.attach_session(name)


def _launch_amplifier(workdir: Path) -> None:
    """Launch (or resume) an Amplifier session rooted at *workdir*.

    Checks for existing sessions via ``amplifier session list``.  If sessions
    exist, resumes the most recent one; otherwise starts a fresh session.

    On POSIX systems the current process is *replaced* via ``os.execvp`` so
    that the shell / calling process gets the right exit code.  On Windows,
    ``subprocess.run`` is used followed by ``sys.exit``.
    """
    result = subprocess.run(
        ["amplifier", "session", "list"],
        cwd=workdir,
        capture_output=True,
    )
    has_sessions = result.returncode == 0 and result.stdout.strip()

    if has_sessions:
        cmd = ["amplifier", "resume"]
    else:
        cmd = ["amplifier"]

    if os.name == "nt":
        # Windows: subprocess then exit
        completed = subprocess.run(cmd, cwd=workdir)
        sys.exit(completed.returncode)
    else:
        # POSIX: replace current process
        os.execvp(cmd[0], cmd)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def run_workspace(
    workdir: Path,
    config: WorkspaceConfig,
    *,
    kill: bool = False,
    destroy: bool = False,
    fresh: bool = False,
) -> None:
    """Orchestrate the full workspace lifecycle.

    kill:
        If tmux is enabled, kill the tmux session for *workdir* and return
        immediately (the directory is preserved).  No-op when tmux is disabled.

    destroy (without fresh):
        If tmux is enabled, kill the tmux session first.  Then remove the
        workspace directory and return — no further action.

    fresh:
        If tmux is enabled, kill the tmux session and remove the directory.
        Then fall through to normal setup.

    Default:
        Set up the workspace and launch Amplifier (or tmux if enabled).
    """
    # First-run wizard trigger — lazy imports avoid circular dependency through wizard
    from amplifier_workspace.config_manager import CONFIG_PATH  # noqa: PLC0415
    from amplifier_workspace.config import load_config  # noqa: PLC0415
    from amplifier_workspace.wizard import run_wizard  # noqa: PLC0415

    if not CONFIG_PATH.exists():
        run_wizard()

    config = load_config()  # re-load config (wizard may have just written it)

    # 1) kill flag: terminate tmux session without touching the directory
    if kill:
        if config.tmux.enabled:
            name = tmux.session_name_from_path(workdir)
            tmux.kill_session(name)
        return

    # 2) destroy flag: kill tmux session first (if enabled), then remove directory
    if destroy and not fresh:
        if config.tmux.enabled:
            name = tmux.session_name_from_path(workdir)
            tmux.kill_session(name)
        if workdir.exists():
            shutil.rmtree(workdir)
        return

    # 3) fresh flag: kill tmux session (if enabled) and remove directory, then fall through
    if fresh:
        if config.tmux.enabled:
            name = tmux.session_name_from_path(workdir)
            tmux.kill_session(name)
        if workdir.exists():
            shutil.rmtree(workdir)

    # 4) Normal path: set up workspace, then launch (with or without tmux)
    setup_workspace(workdir, config)
    if config.tmux.enabled:
        _launch_with_tmux(workdir, config)
    else:
        _launch_amplifier(workdir)
