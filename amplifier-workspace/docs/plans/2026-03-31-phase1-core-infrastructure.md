# amplifier-workspace Phase 1: Core Infrastructure

> **For execution:** Use `/execute-plan` mode or the subagent-driven-development recipe.

**Goal:** Build the core workspace engine — config, git, templates, and Tier 1 workspace create/resume/destroy. After Phase 1, `amplifier-workspace ~/dev/task` works end-to-end for users without tmux.

**Feeds into:** Phase 2 (setup wizard / doctor / upgrade) and Phase 3 (tmux session manager)

**Tech Stack:** Python 3.11+, stdlib only (tomllib, pathlib, dataclasses, argparse, subprocess, importlib.resources, os, shutil)

**Architecture:** A `src/`-layout Python package with hatchling build. `cli.py` is a thin arg-parser that calls `workspace.py` (orchestrator). `workspace.py` calls `git.py` (subprocess wrapper) and reads from `config.py` (dataclasses + file loader). `config_manager.py` owns TOML read/write/CRUD for the `config` subcommands. Bundled templates live in `src/amplifier_workspace/templates/` and are accessed via `importlib.resources`.

---

## Working directory contract

All `git add` and `git commit` commands run from
`/home/bkrabach/dev/workspace-tools` (the parent workspace repo — the new
tool lives as a subfolder, not its own git repo yet).

```bash
# Example — always use this pattern for commits:
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): ..."
```

---

## Task 1: Project scaffold

> **No TDD cycle for this task** — it creates the directory skeleton and
> verifies the package installs. Tests start in Task 3.

**Files to create:**

- Create: `amplifier-workspace/pyproject.toml`
- Create: `amplifier-workspace/src/amplifier_workspace/__init__.py`
- Create: `amplifier-workspace/src/amplifier_workspace/__main__.py`
- Create: `amplifier-workspace/src/amplifier_workspace/templates/.gitkeep`
- Create: `amplifier-workspace/tests/__init__.py`

### Step 1: Create directory structure

```bash
cd /home/bkrabach/dev/workspace-tools
mkdir -p amplifier-workspace/src/amplifier_workspace/templates
mkdir -p amplifier-workspace/tests
touch amplifier-workspace/tests/__init__.py
```

### Step 2: Write `amplifier-workspace/pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "amplifier-workspace"
version = "0.1.0"
description = "Create and manage Amplifier development workspaces"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
amplifier-workspace = "amplifier_workspace.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/amplifier_workspace"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### Step 3: Write `amplifier-workspace/src/amplifier_workspace/__init__.py`

```python
```
(Empty file — leave it blank.)

### Step 4: Write `amplifier-workspace/src/amplifier_workspace/__main__.py`

```python
"""Allow running as: python -m amplifier_workspace"""
from amplifier_workspace.cli import main

if __name__ == "__main__":
    main()
```

### Step 5: Install the package in editable mode

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
pip install -e ".[dev]" 2>/dev/null || pip install -e .
```

> **Why editable?** `importlib.resources` can only find bundled template files
> if the package is installed (even editable). Without this, template loading
> will silently fail during tests.

### Step 6: Verify the entry point exists

```bash
amplifier-workspace --help 2>&1 | head -5
python -m amplifier_workspace --help 2>&1 | head -5
```

Both commands will error (no `cli.py` yet) but should show an `ImportError`
or `ModuleNotFoundError` — not `command not found`. That confirms the entry
point wiring is correct.

### Step 7: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): project scaffold — pyproject.toml, package skeleton"
```

---

## Task 2: Templates

> **No TDD cycle for this task** — templates are content files, not logic.
> They must exist before `config.py` tests can pass (Task 6 depends on
> `default-config.toml` being loadable via `importlib.resources`).

**Files to create:**

- Create: `amplifier-workspace/src/amplifier_workspace/templates/AGENTS.md`
- Create: `amplifier-workspace/src/amplifier_workspace/templates/default-config.toml`

### Step 1: Write `templates/AGENTS.md`

```markdown
# Amplifier Development Workspace

This is an Amplifier development workspace. It is a **local-only git
repository** — ephemeral and disposable. The real code lives in the submodule
directories.

## Workspace structure

```
<workspace-root>/       ← local-only git repo (throwaway)
├── AGENTS.md           ← this file (your instructions)
├── SCRATCH.md          ← your working memory (create as needed)
├── .amplifier/
│   └── settings.yaml   ← tells Amplifier which bundle to use
├── amplifier/          ← git submodule → microsoft/amplifier
├── amplifier-core/     ← git submodule → microsoft/amplifier-core
└── amplifier-foundation/ ← git submodule → microsoft/amplifier-foundation
```

## What is persistent vs. ephemeral

| Location | Persistence |
|---|---|
| `amplifier/`, `amplifier-core/`, `amplifier-foundation/` | **Permanent.** These are real GitHub repos. Any commits or pushes here persist. |
| Everything else in the workspace root | **Ephemeral.** The workspace directory is disposable. |
| `~/.amplifier/cache/` | **Managed by Amplifier.** Do not edit files here directly — edit the submodules instead. |

**Important:** When you make changes to `amplifier/`, `amplifier-core/`, or
`amplifier-foundation/`, commit and push them using the normal git workflow
within those subdirectories. Those changes are permanent.

## SCRATCH.md pattern

Create `SCRATCH.md` at the workspace root as your working memory:
- Running notes, decisions, status
- Prune actively — keep it focused on the current task
- It is not committed; it disappears when the workspace is destroyed

## Workspace lifecycle

1. `amplifier-workspace ~/dev/<task-name>` — creates or resumes this workspace
2. Work in the submodule directories
3. Commit and push from within `amplifier/`, `amplifier-core/`, etc.
4. `amplifier-workspace -d ~/dev/<task-name>` — destroys workspace when done

## Adding more repos

```bash
# From the workspace root:
git submodule add https://github.com/microsoft/<repo>.git
git add .
git commit -m "Add <repo> submodule"
```

## Bundle

This workspace uses the `amplifier-dev` bundle (configured in
`.amplifier/settings.yaml`). The bundle is set at workspace creation time
based on your `~/.config/amplifier-workspace/config.toml`.
```

### Step 2: Write `templates/default-config.toml`

```toml
[workspace]
default_repos = [
    "https://github.com/microsoft/amplifier.git",
    "https://github.com/microsoft/amplifier-core.git",
    "https://github.com/microsoft/amplifier-foundation.git",
]
bundle = "amplifier-dev"
agents_template = ""

[tmux]
enabled = false

[tmux.windows]
amplifier = ""
shell = ""
```

### Step 3: Reinstall so templates are included

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
pip install -e .
```

### Step 4: Verify templates are importlib-accessible

```bash
python -c "
from importlib.resources import files
content = files('amplifier_workspace').joinpath('templates', 'AGENTS.md').read_text()
print('AGENTS.md OK, length:', len(content))
content = files('amplifier_workspace').joinpath('templates', 'default-config.toml').read_bytes()
print('default-config.toml OK, length:', len(content))
"
```

Expected output:
```
AGENTS.md OK, length: <some number > 0>
default-config.toml OK, length: <some number > 0>
```

### Step 5: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): add AGENTS.md and default-config.toml templates"
```

---

## Task 3: `git.py` — pure functions

**Files:**

- Create: `amplifier-workspace/src/amplifier_workspace/git.py`
- Create: `amplifier-workspace/tests/test_git.py`

### Step 1: Write the failing tests

Create `amplifier-workspace/tests/test_git.py`:

```python
"""Tests for git.py — pure functions first."""
from pathlib import Path

import pytest

from amplifier_workspace.git import is_git_repo, repo_name_from_url


class TestRepoNameFromUrl:
    def test_https_with_git_suffix(self):
        assert repo_name_from_url("https://github.com/microsoft/amplifier.git") == "amplifier"

    def test_https_without_git_suffix(self):
        assert repo_name_from_url("https://github.com/microsoft/amplifier") == "amplifier"

    def test_ssh_format(self):
        assert repo_name_from_url("git@github.com:microsoft/amplifier.git") == "amplifier"

    def test_hyphenated_name(self):
        assert repo_name_from_url("https://github.com/org/amplifier-core.git") == "amplifier-core"

    def test_simple_name(self):
        assert repo_name_from_url("https://github.com/org/myrepo.git") == "myrepo"


class TestIsGitRepo:
    def test_returns_true_when_dot_git_dir_exists(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        assert is_git_repo(tmp_path) is True

    def test_returns_false_when_no_dot_git(self, tmp_path: Path):
        assert is_git_repo(tmp_path) is False

    def test_returns_true_when_dot_git_is_file(self, tmp_path: Path):
        # git submodules use a .git file, not a directory
        (tmp_path / ".git").write_text("gitdir: ../.git/modules/foo")
        assert is_git_repo(tmp_path) is True

    def test_returns_false_for_nonexistent_path(self, tmp_path: Path):
        assert is_git_repo(tmp_path / "nonexistent") is False
```

### Step 2: Run tests — verify they fail

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_git.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'is_git_repo' from 'amplifier_workspace.git'`
(or `ModuleNotFoundError` — the module doesn't exist yet).

### Step 3: Write the implementation

Create `amplifier-workspace/src/amplifier_workspace/git.py`:

```python
"""Git repository and submodule operations."""
from pathlib import Path
import subprocess


def repo_name_from_url(url: str) -> str:
    """Extract repository name from a git URL.

    Handles HTTPS and SSH formats, strips .git suffix.

    Examples:
        >>> repo_name_from_url("https://github.com/org/repo.git")
        'repo'
        >>> repo_name_from_url("git@github.com:org/repo.git")
        'repo'
    """
    # SSH format: git@host:org/repo.git  →  strip everything before the colon
    if ":" in url and not url.startswith(("http://", "https://")):
        url = url.split(":")[-1]

    name = Path(url).name
    if name.endswith(".git"):
        name = name[:-4]
    return name


def is_git_repo(path: Path) -> bool:
    """Return True if path contains a .git entry (dir or file)."""
    return (path / ".git").exists()


def _run(cmd: list[str], *, cwd: Path) -> None:
    """Run a git command, raising subprocess.CalledProcessError on failure."""
    subprocess.run(cmd, cwd=cwd, check=True)


def init_repo(path: Path) -> None:
    """Git-init path, creating the directory if needed. Idempotent."""
    path.mkdir(parents=True, exist_ok=True)
    if is_git_repo(path):
        print(f"  already a git repo: {path}")
        return
    print(f"  git init: {path}")
    _run(["git", "init"], cwd=path)


def add_submodule(repo_path: Path, url: str) -> None:
    """Add a git submodule. Skips if the directory already exists."""
    name = repo_name_from_url(url)
    if (repo_path / name).exists():
        print(f"  submodule already exists, skipping: {name}")
        return
    print(f"  git submodule add: {name}")
    _run(["git", "submodule", "add", url], cwd=repo_path)


def checkout_submodules(repo_path: Path) -> None:
    """Checkout each submodule to main, falling back to master."""
    print("  checking out submodules (main || master)...")
    _run(
        ["git", "submodule", "foreach", "git checkout main || git checkout master"],
        cwd=repo_path,
    )


def initial_commit(repo_path: Path, message: str) -> None:
    """Stage all files and create an initial commit."""
    print(f"  initial commit: {message}")
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", message], cwd=repo_path)
```

### Step 4: Run tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_git.py -v
```

Expected output:
```
tests/test_git.py::TestRepoNameFromUrl::test_https_with_git_suffix PASSED
tests/test_git.py::TestRepoNameFromUrl::test_https_without_git_suffix PASSED
tests/test_git.py::TestRepoNameFromUrl::test_ssh_format PASSED
tests/test_git.py::TestRepoNameFromUrl::test_hyphenated_name PASSED
tests/test_git.py::TestRepoNameFromUrl::test_simple_name PASSED
tests/test_git.py::TestIsGitRepo::test_returns_true_when_dot_git_dir_exists PASSED
tests/test_git.py::TestIsGitRepo::test_returns_false_when_no_dot_git PASSED
tests/test_git.py::TestIsGitRepo::test_returns_true_when_dot_git_is_file PASSED
tests/test_git.py::TestIsGitRepo::test_returns_false_for_nonexistent_path PASSED

9 passed
```

### Step 5: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): git.py pure functions — repo_name_from_url, is_git_repo"
```

---

## Task 4: `git.py` — subprocess functions

**Files:**

- Modify: `amplifier-workspace/tests/test_git.py` (add new tests)
- Modify: `amplifier-workspace/src/amplifier_workspace/git.py` (already written above — no changes needed if Task 3 was completed in full)

> **Note:** `git.py` was written in full during Task 3. This task only adds
> the subprocess-mocking tests to verify each function's behavior.

### Step 1: Add subprocess tests to `test_git.py`

Append to the bottom of `amplifier-workspace/tests/test_git.py`:

```python
from unittest.mock import call, patch

from amplifier_workspace.git import (
    add_submodule,
    checkout_submodules,
    initial_commit,
    init_repo,
)


class TestInitRepo:
    @patch("amplifier_workspace.git.subprocess.run")
    def test_calls_git_init(self, mock_run, tmp_path: Path):
        init_repo(tmp_path)
        mock_run.assert_called_once_with(["git", "init"], cwd=tmp_path, check=True)

    @patch("amplifier_workspace.git.subprocess.run")
    def test_skips_if_already_git_repo(self, mock_run, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        init_repo(tmp_path)
        mock_run.assert_not_called()

    @patch("amplifier_workspace.git.subprocess.run")
    def test_creates_directory_if_missing(self, mock_run, tmp_path: Path):
        target = tmp_path / "new" / "deep" / "path"
        init_repo(target)
        assert target.exists()
        mock_run.assert_called_once()


class TestAddSubmodule:
    @patch("amplifier_workspace.git.subprocess.run")
    def test_calls_git_submodule_add(self, mock_run, tmp_path: Path):
        url = "https://github.com/microsoft/amplifier.git"
        add_submodule(tmp_path, url)
        mock_run.assert_called_once_with(
            ["git", "submodule", "add", url], cwd=tmp_path, check=True
        )

    @patch("amplifier_workspace.git.subprocess.run")
    def test_skips_if_directory_exists(self, mock_run, tmp_path: Path):
        (tmp_path / "amplifier").mkdir()
        add_submodule(tmp_path, "https://github.com/microsoft/amplifier.git")
        mock_run.assert_not_called()

    @patch("amplifier_workspace.git.subprocess.run")
    def test_derives_name_from_url(self, mock_run, tmp_path: Path):
        add_submodule(tmp_path, "https://github.com/org/amplifier-core.git")
        # Verify it would skip if amplifier-core/ exists
        (tmp_path / "amplifier-core").mkdir()
        mock_run.reset_mock()
        add_submodule(tmp_path, "https://github.com/org/amplifier-core.git")
        mock_run.assert_not_called()


class TestCheckoutSubmodules:
    @patch("amplifier_workspace.git.subprocess.run")
    def test_uses_main_with_master_fallback(self, mock_run, tmp_path: Path):
        checkout_submodules(tmp_path)
        mock_run.assert_called_once_with(
            [
                "git",
                "submodule",
                "foreach",
                "git checkout main || git checkout master",
            ],
            cwd=tmp_path,
            check=True,
        )


class TestInitialCommit:
    @patch("amplifier_workspace.git.subprocess.run")
    def test_stages_all_then_commits(self, mock_run, tmp_path: Path):
        initial_commit(tmp_path, "Initial workspace setup")
        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        assert calls[0] == call(["git", "add", "."], cwd=tmp_path, check=True)
        assert calls[1] == call(
            ["git", "commit", "-m", "Initial workspace setup"],
            cwd=tmp_path,
            check=True,
        )
```

### Step 2: Run new tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_git.py -v
```

Expected: all tests pass (the implementations were already written in Task 3).

### Step 3: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "test(amplifier-workspace): git.py subprocess function tests — init, add_submodule, checkout, commit"
```

---

## Task 5: `config.py` — dataclasses

**Files:**

- Create: `amplifier-workspace/src/amplifier_workspace/config.py`
- Create: `amplifier-workspace/tests/test_config.py`

### Step 1: Write the failing tests

Create `amplifier-workspace/tests/test_config.py`:

```python
"""Tests for config.py dataclasses and load_config."""
from pathlib import Path

import pytest

from amplifier_workspace.config import TmuxConfig, WorkspaceConfig


class TestWorkspaceConfigDefaults:
    def test_bundle_default(self):
        config = WorkspaceConfig()
        assert config.bundle == "amplifier-dev"

    def test_agents_template_default_is_empty_string(self):
        config = WorkspaceConfig()
        assert config.agents_template == ""

    def test_default_repos_includes_amplifier(self):
        config = WorkspaceConfig()
        assert any("amplifier.git" in r for r in config.default_repos)

    def test_default_repos_has_three_entries(self):
        config = WorkspaceConfig()
        assert len(config.default_repos) == 3

    def test_tmux_disabled_by_default(self):
        config = WorkspaceConfig()
        assert config.tmux.enabled is False

    def test_tmux_windows_is_dict(self):
        config = WorkspaceConfig()
        assert isinstance(config.tmux.windows, dict)


class TestTmuxConfig:
    def test_enabled_defaults_false(self):
        t = TmuxConfig()
        assert t.enabled is False

    def test_windows_defaults_to_amplifier_and_shell(self):
        t = TmuxConfig()
        assert "amplifier" in t.windows
        assert "shell" in t.windows

    def test_custom_windows(self):
        t = TmuxConfig(enabled=True, windows={"git": "lazygit"})
        assert t.windows["git"] == "lazygit"
```

### Step 2: Run tests — verify they fail

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_config.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'TmuxConfig' from 'amplifier_workspace.config'`

### Step 3: Write the implementation

Create `amplifier-workspace/src/amplifier_workspace/config.py`:

```python
"""Configuration dataclasses and file loading for amplifier-workspace.

Config file: ~/.config/amplifier-workspace/config.toml

Example config:
    [workspace]
    bundle = "amplifier-dev"
    default_repos = ["https://github.com/microsoft/amplifier.git"]
    agents_template = ""

    [tmux]
    enabled = false

    [tmux.windows]
    amplifier = ""
    shell = ""
"""
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
import tomllib


CONFIG_PATH = Path.home() / ".config" / "amplifier-workspace" / "config.toml"

_DEFAULT_REPOS = [
    "https://github.com/microsoft/amplifier.git",
    "https://github.com/microsoft/amplifier-core.git",
    "https://github.com/microsoft/amplifier-foundation.git",
]

_DEFAULT_WINDOWS = {"amplifier": "", "shell": ""}


@dataclass
class TmuxConfig:
    """Configuration for the tmux session manager (Tier 2).

    Attributes:
        enabled: Whether tmux is enabled. False = Tier 1 direct launch.
        windows: Ordered dict of window_name -> command.
                 Presence of a key = window is enabled.
                 Empty string command = shell only (no command run).
    """

    enabled: bool = False
    windows: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_WINDOWS))


@dataclass
class WorkspaceConfig:
    """Root configuration for amplifier-workspace.

    Attributes:
        default_repos: Git URLs cloned as submodules into new workspaces.
        bundle: Amplifier bundle name written to .amplifier/settings.yaml.
        agents_template: Path to custom AGENTS.md template.
                         Empty string = use built-in template.
        tmux: Tmux session manager config (Tier 2).
    """

    default_repos: list[str] = field(default_factory=lambda: list(_DEFAULT_REPOS))
    bundle: str = "amplifier-dev"
    agents_template: str = ""
    tmux: TmuxConfig = field(default_factory=TmuxConfig)


def _load_bundled_defaults() -> dict:
    """Load default-config.toml from the bundled templates directory."""
    try:
        template_bytes = (
            resources.files(__package__)
            .joinpath("templates", "default-config.toml")
            .read_bytes()
        )
        return tomllib.loads(template_bytes.decode("utf-8"))
    except (FileNotFoundError, TypeError, tomllib.TOMLDecodeError):
        return {}


def load_config(config_path: Path | None = None) -> WorkspaceConfig:
    """Load WorkspaceConfig, merging user file over defaults.

    Args:
        config_path: Path to TOML config file. Defaults to CONFIG_PATH.
                     If the file doesn't exist, returns defaults — never fails.

    Returns:
        WorkspaceConfig with file values overriding defaults.
    """
    defaults = WorkspaceConfig()

    path = config_path if config_path is not None else CONFIG_PATH

    if not path.exists():
        return defaults

    with open(path, "rb") as f:
        data = tomllib.load(f)

    ws = data.get("workspace", {})
    tmux_data = data.get("tmux", {})
    windows_data = tmux_data.get("windows", None)

    return WorkspaceConfig(
        default_repos=ws.get("default_repos", defaults.default_repos),
        bundle=ws.get("bundle", defaults.bundle),
        agents_template=_expand_path(ws.get("agents_template", defaults.agents_template)),
        tmux=TmuxConfig(
            enabled=tmux_data.get("enabled", defaults.tmux.enabled),
            windows=windows_data if windows_data is not None else defaults.tmux.windows,
        ),
    )


def _expand_path(path_str: str) -> str:
    """Expand ~ in path strings. Returns empty string unchanged."""
    if not path_str:
        return path_str
    return str(Path(path_str).expanduser())
```

### Step 4: Run tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_config.py -v
```

Expected output:
```
tests/test_config.py::TestWorkspaceConfigDefaults::test_bundle_default PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_agents_template_default_is_empty_string PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_default_repos_includes_amplifier PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_default_repos_has_three_entries PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_tmux_disabled_by_default PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_tmux_windows_is_dict PASSED
tests/test_config.py::TestTmuxConfig::test_enabled_defaults_false PASSED
tests/test_config.py::TestTmuxConfig::test_windows_defaults_to_amplifier_and_shell PASSED
tests/test_config.py::TestTmuxConfig::test_custom_windows PASSED

9 passed
```

### Step 5: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): config.py dataclasses — WorkspaceConfig, TmuxConfig"
```

---

## Task 6: `config.py` — load_config

**Files:**

- Modify: `amplifier-workspace/tests/test_config.py` (add load_config tests)
- No changes to `config.py` — `load_config` was already written in Task 5

### Step 1: Add load_config tests to `test_config.py`

Append to the bottom of `amplifier-workspace/tests/test_config.py`:

```python
from amplifier_workspace.config import load_config


class TestLoadConfig:
    def test_returns_defaults_when_file_missing(self, tmp_path: Path):
        config = load_config(config_path=tmp_path / "nonexistent.toml")
        assert config.bundle == "amplifier-dev"
        assert len(config.default_repos) == 3
        assert config.tmux.enabled is False

    def test_merges_bundle_from_file(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[workspace]\nbundle = "my-custom-bundle"\n')
        config = load_config(config_path=config_file)
        assert config.bundle == "my-custom-bundle"
        # Other defaults are preserved
        assert len(config.default_repos) == 3

    def test_merges_repos_from_file(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[workspace]\ndefault_repos = ["https://github.com/org/custom.git"]\n'
        )
        config = load_config(config_path=config_file)
        assert config.default_repos == ["https://github.com/org/custom.git"]

    def test_merges_tmux_enabled(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[tmux]\nenabled = true\n")
        config = load_config(config_path=config_file)
        assert config.tmux.enabled is True

    def test_merges_tmux_windows(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[tmux]\nenabled = true\n\n[tmux.windows]\namplifier = \"\"\ngit = \"lazygit\"\n"
        )
        config = load_config(config_path=config_file)
        assert config.tmux.windows == {"amplifier": "", "git": "lazygit"}

    def test_expands_tilde_in_agents_template(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[workspace]\nagents_template = "~/my-template.md"\n')
        config = load_config(config_path=config_file)
        assert not config.agents_template.startswith("~")
        assert config.agents_template.endswith("my-template.md")

    def test_partial_tmux_config_keeps_defaults(self, tmp_path: Path):
        # Only set enabled, don't specify windows
        config_file = tmp_path / "config.toml"
        config_file.write_text("[tmux]\nenabled = true\n")
        config = load_config(config_path=config_file)
        assert config.tmux.enabled is True
        # Default windows preserved
        assert "amplifier" in config.tmux.windows
```

### Step 2: Run new tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_config.py -v
```

Expected: all tests pass (including the new load_config tests).

### Step 3: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "test(amplifier-workspace): load_config tests — merge, partial, tilde expansion"
```

---

## Task 7: `config_manager.py` — read/write/TOML serializer

**Files:**

- Create: `amplifier-workspace/src/amplifier_workspace/config_manager.py`
- Create: `amplifier-workspace/tests/test_config_manager.py`

### Step 1: Write the failing tests

Create `amplifier-workspace/tests/test_config_manager.py`:

```python
"""Tests for config_manager.py TOML read/write operations."""
from pathlib import Path

import pytest

from amplifier_workspace.config_manager import _toml_value, read_config_raw, write_config_raw


class TestTomlValue:
    def test_bool_true(self):
        assert _toml_value(True) == "true"

    def test_bool_false(self):
        assert _toml_value(False) == "false"

    def test_string(self):
        assert _toml_value("hello") == '"hello"'

    def test_string_with_double_quotes(self):
        result = _toml_value('say "hi"')
        assert result == '"say \\"hi\\""'

    def test_string_with_backslash(self):
        result = _toml_value("C:\\path")
        assert result == '"C:\\\\path"'

    def test_integer(self):
        assert _toml_value(42) == "42"

    def test_float(self):
        assert _toml_value(3.14) == "3.14"

    def test_list_of_strings(self):
        result = _toml_value(["a", "b"])
        assert result == '["a", "b"]'

    def test_empty_list(self):
        assert _toml_value([]) == "[]"

    def test_list_of_urls(self):
        urls = [
            "https://github.com/microsoft/amplifier.git",
            "https://github.com/microsoft/amplifier-core.git",
        ]
        result = _toml_value(urls)
        assert "amplifier.git" in result
        assert "amplifier-core.git" in result


class TestReadWriteConfigRaw:
    def test_read_returns_empty_when_file_missing(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", tmp_path / "config.toml")
        result = read_config_raw()
        assert result == {}

    def test_write_creates_file_and_directory(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "subdir" / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"bundle": "test-bundle"}})
        assert config_path.exists()

    def test_write_produces_valid_toml_section(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"bundle": "my-bundle"}})
        content = config_path.read_text()
        assert "[workspace]" in content
        assert 'bundle = "my-bundle"' in content

    def test_write_handles_nested_section(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({
            "tmux": {
                "enabled": False,
                "windows": {"amplifier": "", "shell": ""},
            }
        })
        content = config_path.read_text()
        assert "[tmux]" in content
        assert "enabled = false" in content
        assert "[tmux.windows]" in content
        assert 'amplifier = ""' in content

    def test_roundtrip(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        original = {
            "workspace": {
                "bundle": "amplifier-dev",
                "default_repos": ["https://github.com/microsoft/amplifier.git"],
            },
            "tmux": {"enabled": False},
        }
        write_config_raw(original)
        result = read_config_raw()
        assert result["workspace"]["bundle"] == "amplifier-dev"
        assert result["tmux"]["enabled"] is False
```

### Step 2: Run tests — verify they fail

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_config_manager.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name '_toml_value' from 'amplifier_workspace.config_manager'`

### Step 3: Write the implementation

Create `amplifier-workspace/src/amplifier_workspace/config_manager.py`:

```python
"""TOML config file read/write/CRUD for amplifier-workspace.

Provides utilities for reading, writing, and modifying the user's config file
at ~/.config/amplifier-workspace/config.toml.

Dot-notation key convention:
    "workspace.bundle"          -> section=workspace, key=bundle
    "workspace.default_repos"   -> section=workspace, key=default_repos (list)
    "tmux.enabled"              -> section=tmux, key=enabled
    "tmux.windows.git"          -> section=tmux, key=windows, nested=git
"""
from pathlib import Path
from typing import Any
import tomllib

from .config import CONFIG_PATH


def config_exists() -> bool:
    """Return True if the config file exists."""
    return CONFIG_PATH.exists()


def read_config_raw(path: Path | None = None) -> dict:
    """Read raw TOML config as a dict. Returns empty dict if file missing."""
    p = path or CONFIG_PATH
    if not p.exists():
        return {}
    with open(p, "rb") as f:
        return tomllib.load(f)


def write_config_raw(data: dict, path: Path | None = None) -> None:
    """Write a dict to the config file in TOML format.

    Creates parent directories if needed. Handles one level of section
    nesting (e.g., [tmux.windows] nested inside [tmux]).
    """
    p = path or CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    for section, values in data.items():
        if not isinstance(values, dict):
            lines.append(f"{section} = {_toml_value(values)}")
            continue

        nested_sections: dict[str, dict] = {}
        flat_values: dict[str, Any] = {}

        for key, val in values.items():
            if isinstance(val, dict):
                nested_sections[key] = val
            else:
                flat_values[key] = val

        lines.append(f"[{section}]")
        for key, val in flat_values.items():
            lines.append(f"{key} = {_toml_value(val)}")
        lines.append("")

        for nested_name, nested_values in nested_sections.items():
            lines.append(f"[{section}.{nested_name}]")
            for key, val in nested_values.items():
                lines.append(f"{key} = {_toml_value(val)}")
            lines.append("")

    p.write_text("\n".join(lines))


def _toml_value(val: Any) -> str:
    """Serialize a Python value to its TOML string representation."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        items = ", ".join(_toml_value(v) for v in val)
        return f"[{items}]"
    return str(val)


def _parse_key(key: str) -> tuple[str, str, str | None]:
    """Parse a dot-notation key into (section, setting, nested_or_None).

    Examples:
        "workspace.bundle"      -> ("workspace", "bundle", None)
        "tmux.enabled"          -> ("tmux", "enabled", None)
        "tmux.windows.git"      -> ("tmux", "windows", "git")

    Raises:
        ValueError: If fewer than two parts are given.
    """
    parts = key.split(".")
    if len(parts) < 2:
        raise ValueError(
            f"Invalid key '{key}'. Use dot notation: 'section.key' or 'section.key.nested'"
        )
    section = parts[0]
    setting = parts[1]
    nested = ".".join(parts[2:]) if len(parts) > 2 else None
    return section, setting, nested


def get_nested_setting(key: str) -> Any:
    """Get a config value by dot-notation key (reads from file, no defaults).

    Returns None if the key doesn't exist.
    """
    section, setting, nested = _parse_key(key)
    data = read_config_raw()
    section_data = data.get(section, {})
    value = section_data.get(setting)
    if nested is not None:
        if not isinstance(value, dict):
            return None
        return value.get(nested)
    return value


def set_nested_setting(key: str, value: Any) -> None:
    """Set a config value by dot-notation key. Creates file if missing."""
    section, setting, nested = _parse_key(key)
    _ensure_config_exists()
    data = read_config_raw()

    if section not in data:
        data[section] = {}

    if nested is not None:
        if setting not in data[section]:
            data[section][setting] = {}
        if not isinstance(data[section][setting], dict):
            raise ValueError(f"'{section}.{setting}' is not a dict — cannot set nested key")
        data[section][setting][nested] = value
    else:
        data[section][setting] = value

    write_config_raw(data)


def add_to_setting(key: str, value: str) -> str:
    """Append to a list setting, or add a key to a dict setting.

    For lists:  add_to_setting("workspace.default_repos", "https://...")
    For dicts:  add_to_setting("tmux.windows.git", "lazygit")
                  (the third key segment is the dict entry name)

    Returns a human-readable success message.
    """
    section, setting, nested = _parse_key(key)
    _ensure_config_exists()
    data = read_config_raw()

    if section not in data:
        data[section] = {}

    if nested is not None:
        # e.g., "tmux.windows.git" -> data["tmux"]["windows"]["git"] = value
        if setting not in data[section]:
            data[section][setting] = {}
        if not isinstance(data[section][setting], dict):
            raise ValueError(f"'{section}.{setting}' is not a dict")
        data[section][setting][nested] = value
        write_config_raw(data)
        return f"Added {section}.{setting}.{nested}"

    current = data[section].get(setting)

    if current is None:
        # Infer list — can't add to something that doesn't exist as a list
        data[section][setting] = [value]
        write_config_raw(data)
        return f"Added to {key}"

    if isinstance(current, list):
        if value in current:
            return f"Already in {key}: {value}"
        current.append(value)
        write_config_raw(data)
        return f"Added to {key}"

    raise ValueError(f"'{key}' is not a list or dict (type: {type(current).__name__})")


def remove_from_setting(key: str, value: str | None = None) -> str:
    """Remove from a list (by value or index) or remove a dict entry.

    For lists:    remove_from_setting("workspace.default_repos", "https://...")
                  remove_from_setting("workspace.default_repos", "0")  # by index
    For dicts:    remove_from_setting("tmux.windows.git")
                    (the third key segment is the entry to remove)

    Returns a human-readable success message.
    """
    section, setting, nested = _parse_key(key)

    if not config_exists():
        raise ValueError("No config file exists")

    data = read_config_raw()

    if section not in data or setting not in data[section]:
        raise ValueError(f"Setting '{section}.{setting}' not found in config")

    current = data[section][setting]

    if nested is not None:
        if not isinstance(current, dict):
            raise ValueError(f"'{section}.{setting}' is not a dict")
        if nested not in current:
            raise ValueError(f"Key '{nested}' not found in {section}.{setting}")
        del current[nested]
        write_config_raw(data)
        return f"Removed {key}"

    if isinstance(current, list):
        if value is None:
            raise ValueError(f"'{key}' is a list — specify value or index to remove")
        if value.isdigit():
            idx = int(value)
            if idx >= len(current):
                raise ValueError(f"Index {idx} out of range (list has {len(current)} items)")
            removed = current.pop(idx)
            write_config_raw(data)
            return f"Removed [{idx}] from {key}: {removed}"
        if value not in current:
            raise ValueError(f"'{value}' not found in {key}")
        current.remove(value)
        write_config_raw(data)
        return f"Removed from {key}"

    raise ValueError(f"'{key}' is not a list or dict (type: {type(current).__name__})")


def _ensure_config_exists() -> None:
    """Seed config file from default-config.toml template if it doesn't exist."""
    if CONFIG_PATH.exists():
        return
    from importlib import resources
    try:
        template_bytes = (
            resources.files("amplifier_workspace")
            .joinpath("templates", "default-config.toml")
            .read_bytes()
        )
        data = tomllib.loads(template_bytes.decode("utf-8"))
    except Exception:
        data = {}
    write_config_raw(data)
```

### Step 4: Run tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_config_manager.py -v
```

Expected: all tests pass.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): config_manager.py — TOML read/write, _toml_value serializer"
```

---

## Task 8: `config_manager.py` — dot-notation CRUD

**Files:**

- Modify: `amplifier-workspace/tests/test_config_manager.py` (add CRUD tests)
- No changes to `config_manager.py` — CRUD was already written in Task 7

### Step 1: Add CRUD tests to `test_config_manager.py`

Append to the bottom of `amplifier-workspace/tests/test_config_manager.py`:

```python
from amplifier_workspace.config_manager import (
    add_to_setting,
    config_exists,
    get_nested_setting,
    remove_from_setting,
    set_nested_setting,
)


class TestParseKey:
    def test_parse_key_two_parts(self):
        from amplifier_workspace.config_manager import _parse_key
        assert _parse_key("workspace.bundle") == ("workspace", "bundle", None)

    def test_parse_key_three_parts(self):
        from amplifier_workspace.config_manager import _parse_key
        assert _parse_key("tmux.windows.git") == ("tmux", "windows", "git")

    def test_parse_key_invalid_raises(self):
        from amplifier_workspace.config_manager import _parse_key
        with pytest.raises(ValueError, match="dot notation"):
            _parse_key("justonepart")


class TestGetSetNestedSetting:
    def test_set_and_get_scalar(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        set_nested_setting("tmux.enabled", True)
        result = get_nested_setting("tmux.enabled")
        assert result is True

    def test_set_and_get_string(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        set_nested_setting("workspace.bundle", "my-bundle")
        assert get_nested_setting("workspace.bundle") == "my-bundle"

    def test_set_nested_dict_entry(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        set_nested_setting("tmux.windows.git", "lazygit")
        assert get_nested_setting("tmux.windows.git") == "lazygit"

    def test_get_missing_key_returns_none(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        assert get_nested_setting("workspace.nonexistent") is None

    def test_creates_file_on_first_write(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "new" / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        set_nested_setting("workspace.bundle", "test")
        assert config_path.exists()


class TestAddToSetting:
    def test_add_to_list(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        # Seed with an existing list
        write_config_raw({"workspace": {"default_repos": ["https://github.com/a/b.git"]}})
        add_to_setting("workspace.default_repos", "https://github.com/c/d.git")
        raw = read_config_raw()
        assert "https://github.com/c/d.git" in raw["workspace"]["default_repos"]

    def test_add_to_list_no_duplicates(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": ["https://github.com/a/b.git"]}})
        msg = add_to_setting("workspace.default_repos", "https://github.com/a/b.git")
        assert "Already in" in msg

    def test_add_dict_entry(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        add_to_setting("tmux.windows.git", "lazygit")
        raw = read_config_raw()
        assert raw["tmux"]["windows"]["git"] == "lazygit"


class TestRemoveFromSetting:
    def test_remove_from_list_by_value(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": ["https://a.git", "https://b.git"]}})
        remove_from_setting("workspace.default_repos", "https://a.git")
        raw = read_config_raw()
        assert "https://a.git" not in raw["workspace"]["default_repos"]
        assert "https://b.git" in raw["workspace"]["default_repos"]

    def test_remove_from_list_by_index(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": ["https://a.git", "https://b.git"]}})
        msg = remove_from_setting("workspace.default_repos", "0")
        assert "https://a.git" in msg
        raw = read_config_raw()
        assert raw["workspace"]["default_repos"] == ["https://b.git"]

    def test_remove_dict_entry(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"tmux": {"windows": {"git": "lazygit", "shell": ""}}})
        remove_from_setting("tmux.windows.git")
        raw = read_config_raw()
        assert "git" not in raw["tmux"]["windows"]
        assert "shell" in raw["tmux"]["windows"]

    def test_remove_nonexistent_raises(self, tmp_path: Path, monkeypatch):
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr("amplifier_workspace.config_manager.CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": []}})
        with pytest.raises(ValueError, match="not found"):
            remove_from_setting("workspace.default_repos", "https://nonexistent.git")
```

### Step 2: Run new tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_config_manager.py -v
```

Expected: all tests pass.

### Step 3: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "test(amplifier-workspace): config_manager.py CRUD tests — get/set/add/remove dot-notation"
```

---

## Task 9: `workspace.py` — file scaffolding functions

**Files:**

- Create: `amplifier-workspace/src/amplifier_workspace/workspace.py`
- Create: `amplifier-workspace/tests/test_workspace.py`

### Step 1: Write the failing tests

Create `amplifier-workspace/tests/test_workspace.py`:

```python
"""Tests for workspace.py — create_agents_md and create_amplifier_settings."""
from pathlib import Path
from unittest.mock import patch

import pytest

from amplifier_workspace.config import WorkspaceConfig
from amplifier_workspace.workspace import create_agents_md, create_amplifier_settings


class TestCreateAgentsMd:
    def test_creates_from_builtin_template(self, tmp_path: Path):
        config = WorkspaceConfig()
        create_agents_md(tmp_path, config)
        agents_path = tmp_path / "AGENTS.md"
        assert agents_path.exists()
        content = agents_path.read_text()
        # Built-in template has real content
        assert len(content) > 100

    def test_skips_if_already_exists(self, tmp_path: Path):
        config = WorkspaceConfig()
        agents_path = tmp_path / "AGENTS.md"
        agents_path.write_text("# existing content — do not overwrite")
        create_agents_md(tmp_path, config)
        assert agents_path.read_text() == "# existing content — do not overwrite"

    def test_uses_custom_template_when_configured(self, tmp_path: Path):
        custom = tmp_path / "my-agents.md"
        custom.write_text("# Custom AGENTS.md for my team")
        workdir = tmp_path / "workspace"
        workdir.mkdir()
        config = WorkspaceConfig(agents_template=str(custom))
        create_agents_md(workdir, config)
        content = (workdir / "AGENTS.md").read_text()
        assert content == "# Custom AGENTS.md for my team"

    def test_falls_back_to_builtin_if_custom_missing(self, tmp_path: Path):
        config = WorkspaceConfig(agents_template="/nonexistent/path/template.md")
        create_agents_md(tmp_path, config)
        # Should still create a file (fallback to built-in)
        assert (tmp_path / "AGENTS.md").exists()

    def test_builtin_template_mentions_amplifier(self, tmp_path: Path):
        config = WorkspaceConfig()
        create_agents_md(tmp_path, config)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "amplifier" in content.lower()


class TestCreateAmplifierSettings:
    def test_creates_settings_yaml(self, tmp_path: Path):
        config = WorkspaceConfig(bundle="my-bundle")
        create_amplifier_settings(tmp_path, config)
        settings_path = tmp_path / ".amplifier" / "settings.yaml"
        assert settings_path.exists()

    def test_settings_contains_bundle_name(self, tmp_path: Path):
        config = WorkspaceConfig(bundle="my-custom-bundle")
        create_amplifier_settings(tmp_path, config)
        content = (tmp_path / ".amplifier" / "settings.yaml").read_text()
        assert "my-custom-bundle" in content

    def test_creates_amplifier_directory(self, tmp_path: Path):
        config = WorkspaceConfig()
        assert not (tmp_path / ".amplifier").exists()
        create_amplifier_settings(tmp_path, config)
        assert (tmp_path / ".amplifier").is_dir()

    def test_skips_if_settings_already_exists(self, tmp_path: Path):
        config = WorkspaceConfig(bundle="new-bundle")
        amp_dir = tmp_path / ".amplifier"
        amp_dir.mkdir()
        settings = amp_dir / "settings.yaml"
        settings.write_text("bundle:\n  active: original-bundle\n")
        create_amplifier_settings(tmp_path, config)
        # Must not overwrite
        assert "original-bundle" in settings.read_text()
        assert "new-bundle" not in settings.read_text()
```

### Step 2: Run tests — verify they fail

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_workspace.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'create_agents_md' from 'amplifier_workspace.workspace'`

### Step 3: Write the scaffolding functions in `workspace.py`

Create `amplifier-workspace/src/amplifier_workspace/workspace.py`:

```python
"""Workspace orchestration for amplifier-workspace.

Handles workspace create, resume, and destroy (Tier 1 — no tmux).
"""
from importlib import resources
from pathlib import Path
import os
import shutil
import subprocess
import sys

from .config import WorkspaceConfig
from . import git


def create_agents_md(workdir: Path, config: WorkspaceConfig) -> None:
    """Write AGENTS.md into workdir if it doesn't already exist.

    Priority:
    1. Skip entirely if AGENTS.md already exists.
    2. Copy from config.agents_template path (if set and the file exists).
    3. Use built-in template from templates/AGENTS.md.
    """
    target = workdir / "AGENTS.md"
    if target.exists():
        print("  AGENTS.md already exists, skipping")
        return

    # Try custom template
    if config.agents_template:
        custom = Path(config.agents_template)
        if custom.exists():
            print(f"  AGENTS.md from custom template: {custom}")
            shutil.copy(custom, target)
            return
        else:
            print(f"  warning: custom template not found: {custom}")

    # Fall back to built-in template
    try:
        content = (
            resources.files(__package__).joinpath("templates", "AGENTS.md").read_text()
        )
        print("  AGENTS.md from built-in template")
        target.write_text(content)
        return
    except (FileNotFoundError, TypeError):
        pass

    # Last resort: minimal content (shouldn't happen in a properly installed package)
    print("  AGENTS.md: writing minimal fallback content")
    target.write_text(
        "# Amplifier Development Workspace\n\nAdd your notes here.\n"
    )


def create_amplifier_settings(workdir: Path, config: WorkspaceConfig) -> None:
    """Write .amplifier/settings.yaml if it doesn't already exist."""
    amp_dir = workdir / ".amplifier"
    settings_path = amp_dir / "settings.yaml"

    if settings_path.exists():
        print("  .amplifier/settings.yaml already exists, skipping")
        return

    amp_dir.mkdir(exist_ok=True)
    settings_path.write_text(f"bundle:\n  active: {config.bundle}\n")
    print(f"  created .amplifier/settings.yaml (bundle: {config.bundle})")


def setup_workspace(workdir: Path, config: WorkspaceConfig) -> None:
    """Idempotent workspace setup: git init, submodules, templates.

    Safe to re-run on an existing workspace — each step checks before acting.
    """
    if not git.is_git_repo(workdir):
        print(f"Setting up new workspace: {workdir}")
        git.init_repo(workdir)
        for url in config.default_repos:
            git.add_submodule(workdir, url)
        if config.default_repos:
            git.checkout_submodules(workdir)
        git.initial_commit(workdir, "Initial workspace setup with Amplifier submodules")
    else:
        print(f"Workspace already initialized: {workdir}")

    create_agents_md(workdir, config)
    create_amplifier_settings(workdir, config)


def _launch_amplifier(workdir: Path) -> None:
    """Launch Amplifier in workdir, resuming an existing session if one exists.

    On POSIX: uses os.execvp() to replace the current process.
    On Windows: uses subprocess.run() + sys.exit().
    """
    if sys.platform != "win32":
        os.chdir(workdir)

    # Check for existing Amplifier sessions
    try:
        result = subprocess.run(
            ["amplifier", "session", "list"],
            capture_output=True,
            text=True,
        )
        has_sessions = (
            result.returncode == 0
            and "No sessions found" not in result.stdout
            and ("Session ID" in result.stdout or "\u2502" in result.stdout)
        )
    except FileNotFoundError:
        # amplifier not in PATH — still try to launch it (will fail with a clear error)
        has_sessions = False

    cmd = ["amplifier", "resume"] if has_sessions else ["amplifier"]
    print(f"  launching: {' '.join(cmd)}")

    if sys.platform == "win32":
        result = subprocess.run(cmd, cwd=workdir)
        sys.exit(result.returncode)
    else:
        os.execvp(cmd[0], cmd)


def run_workspace(
    workdir: Path,
    config: WorkspaceConfig,
    *,
    destroy: bool = False,
    fresh: bool = False,
) -> None:
    """Main entry point — create, resume, or destroy a workspace.

    Args:
        workdir: Absolute path to the workspace directory.
        config: Loaded WorkspaceConfig.
        destroy: If True, delete the workspace directory (caller confirmed).
        fresh: If True, delete the workspace directory and recreate from scratch.
    """
    if destroy and not fresh:
        if workdir.exists():
            print(f"Destroying workspace: {workdir}")
            shutil.rmtree(workdir)
        else:
            print(f"Workspace directory does not exist: {workdir}")
        return

    if fresh and workdir.exists():
        print(f"Removing existing workspace for fresh start: {workdir}")
        shutil.rmtree(workdir)

    setup_workspace(workdir, config)
    _launch_amplifier(workdir)
```

### Step 4: Run tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_workspace.py -v
```

Expected: all `TestCreateAgentsMd` and `TestCreateAmplifierSettings` tests pass.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): workspace.py — create_agents_md, create_amplifier_settings"
```

---

## Task 10: `workspace.py` — setup_workspace and run_workspace

**Files:**

- Modify: `amplifier-workspace/tests/test_workspace.py` (add orchestration tests)
- No changes to `workspace.py` — these functions were already written in Task 9

### Step 1: Add orchestration tests to `test_workspace.py`

Append to the bottom of `amplifier-workspace/tests/test_workspace.py`:

```python
from amplifier_workspace.workspace import run_workspace, setup_workspace


class TestSetupWorkspace:
    @patch("amplifier_workspace.workspace.git")
    def test_initializes_new_repo(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.init_repo.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace.git")
    def test_adds_all_default_repos_as_submodules(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        assert mock_git.add_submodule.call_count == len(config.default_repos)

    @patch("amplifier_workspace.workspace.git")
    def test_checkouts_submodules_after_adding(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.checkout_submodules.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace.git")
    def test_creates_initial_commit(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.initial_commit.assert_called_once()
        # Verify the commit message mentions "workspace"
        commit_msg = mock_git.initial_commit.call_args[0][1]
        assert "workspace" in commit_msg.lower()

    @patch("amplifier_workspace.workspace.git")
    def test_skips_git_init_for_existing_repo(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = True
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.init_repo.assert_not_called()
        mock_git.add_submodule.assert_not_called()
        mock_git.checkout_submodules.assert_not_called()

    @patch("amplifier_workspace.workspace.git")
    def test_creates_agents_md_for_existing_repo(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = True
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        assert (tmp_path / "AGENTS.md").exists()

    @patch("amplifier_workspace.workspace.git")
    def test_skips_submodule_checkout_when_no_repos(self, mock_git, tmp_path: Path):
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig(default_repos=[])
        setup_workspace(tmp_path, config)
        mock_git.checkout_submodules.assert_not_called()


class TestRunWorkspace:
    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_normal_path_calls_setup_then_launch(
        self, mock_setup, mock_launch, tmp_path: Path
    ):
        config = WorkspaceConfig()
        run_workspace(tmp_path, config)
        mock_setup.assert_called_once_with(tmp_path, config)
        mock_launch.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_destroy_removes_directory_skips_setup(
        self, mock_setup, mock_rmtree, tmp_path: Path
    ):
        config = WorkspaceConfig()
        tmp_path.mkdir(exist_ok=True)
        run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_called_once_with(tmp_path)
        mock_setup.assert_not_called()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_fresh_removes_then_recreates(
        self, mock_setup, mock_launch, tmp_path: Path
    ):
        config = WorkspaceConfig()
        # Create a real directory so fresh can rm it
        (tmp_path / "some_file.txt").write_text("old content")
        run_workspace(tmp_path, config, fresh=True)
        # setup_workspace and launch should both be called
        mock_setup.assert_called_once()
        mock_launch.assert_called_once()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_destroy_noop_when_dir_missing(
        self, mock_setup, mock_launch, tmp_path: Path
    ):
        config = WorkspaceConfig()
        nonexistent = tmp_path / "nope"
        run_workspace(nonexistent, config, destroy=True)
        # Should not raise, should not call setup or launch
        mock_setup.assert_not_called()
        mock_launch.assert_not_called()
```

### Step 2: Run new tests — verify they pass

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_workspace.py -v
```

Expected: all tests pass.

### Step 3: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "test(amplifier-workspace): workspace.py orchestration tests — setup_workspace, run_workspace"
```

---

## Task 11: `cli.py`

**Files:**

- Create: `amplifier-workspace/src/amplifier_workspace/cli.py`

> **No TDD cycle for cli.py** — argparse entry points are tested via
> integration/smoke tests, not unit tests. We verify with a live smoke test
> instead.

### Step 1: Write `cli.py`

Create `amplifier-workspace/src/amplifier_workspace/cli.py`:

```python
"""CLI entry point for amplifier-workspace.

Thin layer: parses arguments, routes to the right module.
All business logic lives in workspace.py, config_manager.py, etc.

Subcommands (all stubbed in Phase 1 — implemented in Phase 2/3):
    doctor    Health checks
    upgrade   Self-update
    setup     Interactive wizard
    config    Config CRUD
    list      Show active workspaces
"""
import argparse
import sys
from pathlib import Path

from .config import load_config


# Subcommands routed before the workspace parser runs.
_SUBCOMMANDS = ("doctor", "upgrade", "setup", "config", "list")


def _confirm_destroy(workdir: Path) -> None:
    """Prompt the user to confirm destruction. Exit if they decline."""
    print(f"This will permanently delete: {workdir}")
    try:
        response = input("Are you sure? [y/N] ").strip().lower()
    except EOFError:
        response = ""
    if response != "y":
        print("Aborted.")
        sys.exit(0)


def _stub_subcommand(name: str) -> None:
    """Placeholder for Phase 2/3 subcommands."""
    print(f"amplifier-workspace {name}: not yet implemented (coming in Phase 2)")
    sys.exit(0)


def main() -> None:
    """Entry point for the amplifier-workspace command."""
    # Fast-path: route known subcommands before workspace arg parsing
    if len(sys.argv) > 1 and sys.argv[1] in _SUBCOMMANDS:
        _stub_subcommand(sys.argv[1])
        return

    parser = argparse.ArgumentParser(
        prog="amplifier-workspace",
        description="Create and manage Amplifier development workspaces.",
        epilog="""\
Examples:
  amplifier-workspace ~/dev/fix-auth          Create or resume workspace
  amplifier-workspace -d ~/dev/fix-auth       Destroy workspace (with confirmation)
  amplifier-workspace -f ~/dev/fix-auth       Fresh start (destroy + recreate)
  amplifier-workspace setup                   Interactive first-run setup
  amplifier-workspace config list             Show current config
  amplifier-workspace doctor                  Health check
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "workdir",
        metavar="WORKDIR",
        type=Path,
        nargs="?",
        help="Workspace directory path (required for create/resume/destroy)",
    )
    parser.add_argument(
        "-d",
        "--destroy",
        action="store_true",
        help="Kill tmux session (if any) and delete the workspace directory",
    )
    parser.add_argument(
        "-f",
        "--fresh",
        action="store_true",
        help="Destroy existing workspace and recreate from scratch",
    )
    parser.add_argument(
        "-k",
        "--kill",
        action="store_true",
        help="Kill tmux session only, leave directory intact (Tier 2 — noop in Tier 1)",
    )

    args = parser.parse_args()

    if args.workdir is None:
        parser.print_help()
        sys.exit(0)

    workdir = args.workdir.expanduser().resolve()

    try:
        config = load_config()

        if args.destroy:
            _confirm_destroy(workdir)

        from .workspace import run_workspace
        run_workspace(workdir, config, destroy=args.destroy, fresh=args.fresh)

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

### Step 2: Run all tests to make sure nothing broke

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest -v
```

Expected: all tests pass (the cli.py has no unit tests but shouldn't break existing ones).

### Step 3: Smoke test — verify the CLI works

```bash
# Shows help
amplifier-workspace --help

# Shows stub message for subcommands
amplifier-workspace doctor
amplifier-workspace config list
amplifier-workspace setup

# Check version info reachable (no crash)
python -c "from amplifier_workspace.cli import main; print('cli.main importable OK')"
```

Expected output from `amplifier-workspace --help`:
```
usage: amplifier-workspace [-h] [-d] [-f] [-k] [WORKDIR]

Create and manage Amplifier development workspaces.
...
```

Expected output from `amplifier-workspace doctor`:
```
amplifier-workspace doctor: not yet implemented (coming in Phase 2)
```

### Step 4: Commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): cli.py — argparse entry point, stub subcommands, Tier 1 workspace routing"
```

---

## Task 12: Full suite run and Phase 1 tag

### Step 1: Run the full test suite

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest -v --tb=short
```

Expected output — all pass, zero failures:
```
tests/test_config.py::TestWorkspaceConfigDefaults::test_bundle_default PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_agents_template_default_is_empty_string PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_default_repos_includes_amplifier PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_default_repos_has_three_entries PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_tmux_disabled_by_default PASSED
tests/test_config.py::TestWorkspaceConfigDefaults::test_tmux_windows_is_dict PASSED
tests/test_config.py::TestTmuxConfig::test_enabled_defaults_false PASSED
tests/test_config.py::TestTmuxConfig::test_windows_defaults_to_amplifier_and_shell PASSED
tests/test_config.py::TestTmuxConfig::test_custom_windows PASSED
tests/test_config.py::TestLoadConfig::test_returns_defaults_when_file_missing PASSED
tests/test_config.py::TestLoadConfig::test_merges_bundle_from_file PASSED
tests/test_config.py::TestLoadConfig::test_merges_repos_from_file PASSED
tests/test_config.py::TestLoadConfig::test_merges_tmux_enabled PASSED
tests/test_config.py::TestLoadConfig::test_merges_tmux_windows PASSED
tests/test_config.py::TestLoadConfig::test_expands_tilde_in_agents_template PASSED
tests/test_config.py::TestLoadConfig::test_partial_tmux_config_keeps_defaults PASSED
tests/test_config_manager.py::TestTomlValue::... PASSED (x10)
tests/test_config_manager.py::TestReadWriteConfigRaw::... PASSED (x5)
tests/test_config_manager.py::TestParseKey::... PASSED (x3)
tests/test_config_manager.py::TestGetSetNestedSetting::... PASSED (x5)
tests/test_config_manager.py::TestAddToSetting::... PASSED (x3)
tests/test_config_manager.py::TestRemoveFromSetting::... PASSED (x4)
tests/test_git.py::TestRepoNameFromUrl::... PASSED (x5)
tests/test_git.py::TestIsGitRepo::... PASSED (x4)
tests/test_git.py::TestInitRepo::... PASSED (x3)
tests/test_git.py::TestAddSubmodule::... PASSED (x3)
tests/test_git.py::TestCheckoutSubmodules::... PASSED (x1)
tests/test_git.py::TestInitialCommit::... PASSED (x1)
tests/test_workspace.py::TestCreateAgentsMd::... PASSED (x5)
tests/test_workspace.py::TestCreateAmplifierSettings::... PASSED (x4)
tests/test_workspace.py::TestSetupWorkspace::... PASSED (x7)
tests/test_workspace.py::TestRunWorkspace::... PASSED (x4)

X passed in Y.YYs
```

If any test fails, fix the failure before proceeding. Do not skip.

### Step 2: Run a static analysis check

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace

# Check for import errors and obvious type problems
python -c "
import amplifier_workspace.cli
import amplifier_workspace.config
import amplifier_workspace.config_manager
import amplifier_workspace.git
import amplifier_workspace.workspace
print('All modules import cleanly.')
"
```

### Step 3: Verify zero runtime dependencies

```bash
# The package should have no third-party deps at all
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -c "
import importlib.metadata
dist = importlib.metadata.distribution('amplifier-workspace')
deps = dist.requires or []
print('Runtime dependencies:', deps)
assert deps == [], f'Expected zero runtime deps, got: {deps}'
print('Zero runtime dependencies confirmed.')
"
```

### Step 4: Final commit

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(amplifier-workspace): Phase 1 complete — core infrastructure end-to-end"
```

---

## Phase 1 completion checklist

After all 12 tasks, verify these are all true:

- [ ] `amplifier-workspace --help` shows usage without errors
- [ ] `amplifier-workspace doctor` shows stub message (not a crash)
- [ ] `amplifier-workspace ~/dev/test-workspace` would run (even if `amplifier` isn't found — it will fail at `_launch_amplifier`, which is correct)
- [ ] `python -m pytest -v` shows all tests passing
- [ ] Zero runtime dependencies (`pip show amplifier-workspace | grep Requires`)
- [ ] All files live under `amplifier-workspace/` in the parent workspace repo
- [ ] One git commit per task (check with `git log --oneline | head -15`)

---

## What Phase 1 does NOT include (by design)

These are explicitly deferred to later phases:

| Feature | Phase |
|---|---|
| `amplifier-workspace setup` (interactive wizard) | Phase 2 |
| `amplifier-workspace doctor` (health checks) | Phase 2 |
| `amplifier-workspace upgrade` (self-update) | Phase 2 |
| `amplifier-workspace config` subcommands wired to config_manager | Phase 2 |
| `amplifier-workspace list` | Phase 2 |
| tmux session manager (`tmux.py`) | Phase 3 |
| `-k` / `--kill` flag behavior | Phase 3 |
| Cross-platform tool installation (`install.py`) | Phase 3 |
