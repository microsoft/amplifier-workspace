"""Git utilities: pure functions and subprocess wrappers."""

from __future__ import annotations

import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def repo_name_from_url(url: str) -> str:
    """Extract a repository name from an HTTPS or SSH git URL.

    Examples:
        https://github.com/org/my-repo.git  → "my-repo"
        https://github.com/org/my-repo      → "my-repo"
        git@github.com:org/repo.git         → "repo"
    """
    # SSH format: contains ':' and does not start with http:// or https://
    if ":" in url and not url.startswith(("http://", "https://")):
        # git@github.com:org/repo.git  →  take everything after ':'
        url = url.split(":", 1)[1]

    name = Path(url).name
    if name.endswith(".git"):
        name = name[:-4]
    return name


def is_git_repo(path: Path) -> bool:
    """Return True if *path* is the root of a git repository.

    Both a .git directory (normal clone) and a .git file (submodule) are
    recognised.  Returns False if the path does not exist.
    """
    return (path / ".git").exists()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path) -> None:
    """Run *cmd* in *cwd*, raising on non-zero exit."""
    subprocess.run(cmd, cwd=cwd, check=True)


# ---------------------------------------------------------------------------
# Subprocess wrappers
# ---------------------------------------------------------------------------


def init_repo(path: Path) -> None:
    """Initialise a new git repository at *path*.

    Creates the directory if it does not exist.  No-op if the path is
    already a git repository.
    """
    path.mkdir(parents=True, exist_ok=True)
    if is_git_repo(path):
        return
    _run(["git", "init"], cwd=path)


def add_submodule(repo_path: Path, url: str) -> None:
    """Add *url* as a git submodule inside *repo_path*.

    No-op if a directory with the inferred repository name already exists.
    """
    name = repo_name_from_url(url)
    if (repo_path / name).exists():
        return
    _run(["git", "submodule", "add", url], cwd=repo_path)


def checkout_submodules(repo_path: Path) -> None:
    """Check out the main (or master) branch in every registered submodule."""
    _run(
        ["git", "submodule", "foreach", "git checkout main || git checkout master"],
        cwd=repo_path,
    )


def initial_commit(repo_path: Path, message: str) -> None:
    """Stage everything and create the first commit in *repo_path*."""
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", message], cwd=repo_path)
