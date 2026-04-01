# amplifier-workspace Phase 3: Session Manager

> **For execution:** Use `/execute-plan` mode or the subagent-driven-development recipe.

**Goal:** Add the tmux session manager (Tier 2). After Phase 3, the tool is complete — `amplifier-workspace ~/dev/task` creates or reattaches a tmux session with configured windows, the wizard covers all 4 steps, and doctor checks tmux and tool availability.

**Requires:** Phase 1 (core infrastructure) and Phase 2 (setup, health, upgrade) complete.

**Tech Stack:** Python 3.11+, stdlib only. tmux (external, optional — tested with mocks).

---

## Assumptions About Phase 1 & 2 Output

These files exist after Phase 1 and 2. The implementations below depend on them.

**`src/amplifier_workspace/config.py`** — defines `AppConfig`, `TmuxConfig`:
```python
from dataclasses import dataclass, field

@dataclass
class TmuxConfig:
    enabled: bool = False
    windows: dict[str, str] = field(default_factory=dict)

@dataclass
class WorkspaceSection:
    default_repos: list[str] = field(default_factory=list)
    bundle: str = "amplifier-dev"
    agents_template: str = ""

@dataclass
class AppConfig:
    workspace: WorkspaceSection = field(default_factory=WorkspaceSection)
    tmux: TmuxConfig = field(default_factory=TmuxConfig)
```

**`src/amplifier_workspace/workspace.py`** — key existing signatures:
```python
def run_workspace(workdir: Path, config: AppConfig, *, destroy: bool = False, fresh: bool = False, kill: bool = False) -> None: ...
def setup_workspace(workdir: Path, config: AppConfig) -> None: ...
def _launch_amplifier(workdir: Path) -> None: ...
```

**`src/amplifier_workspace/wizard.py`** — key existing function:
```python
def run_wizard() -> None:
    # ... runs _step1, _step2, _step3, then writes config
```

**`src/amplifier_workspace/doctor.py`** — key existing function:
```python
def run_doctor() -> int:
    # ... always-run checks, returns 0 or 1
```

---

## Overview of Changes

| File | Action | What |
|---|---|---|
| `src/amplifier_workspace/tmux.py` | **Create** | Full tmux session/window management |
| `tests/test_tmux.py` | **Create** | Tests for tmux.py |
| `src/amplifier_workspace/workspace.py` | **Modify** | Tier 2 integration (kill flag, tmux-aware destroy, _launch_with_tmux) |
| `tests/test_workspace.py` | **Modify** | Add Tier 2 test cases |
| `src/amplifier_workspace/cli.py` | **Modify** | Wire up `-k` flag |
| `tests/test_cli.py` | **Modify** | Test -k flag routing |
| `src/amplifier_workspace/wizard.py` | **Modify** | Add Step 4 (session manager opt-in) |
| `tests/test_wizard.py` | **Modify** | Test Step 4 flows |
| `src/amplifier_workspace/doctor.py` | **Modify** | Add tmux-aware checks |
| `tests/test_doctor.py` | **Modify** | Test tmux check paths |

---

## Task 1: tmux.py — Scaffold + `session_name_from_path` + `session_exists`

**Files:**
- Create: `src/amplifier_workspace/tmux.py`
- Create: `tests/test_tmux.py`

### Step 1: Write the failing tests

Create `tests/test_tmux.py` with this content:

```python
"""Tests for tmux session management."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from amplifier_workspace.tmux import session_exists, session_name_from_path


class TestSessionNameFromPath:
    def test_simple_directory_name(self):
        path = Path("/home/user/dev/my-feature")
        assert session_name_from_path(path) == "my-feature"

    def test_trailing_slash_ignored(self):
        # Path normalizes trailing slashes
        path = Path("/home/user/dev/my-feature/")
        assert session_name_from_path(path) == "my-feature"

    def test_long_name_truncated_to_32(self):
        long_name = "a" * 40
        path = Path(f"/home/user/{long_name}")
        result = session_name_from_path(path)
        assert len(result) <= 32

    def test_spaces_replaced_with_dashes(self):
        path = Path("/home/user/my feature")
        result = session_name_from_path(path)
        assert " " not in result

    def test_colons_replaced_with_dashes(self):
        # Colons break tmux target syntax
        path = Path("/home/user/fix:auth")
        result = session_name_from_path(path)
        assert ":" not in result

    def test_dots_replaced_with_dashes(self):
        path = Path("/home/user/my.feature")
        result = session_name_from_path(path)
        assert "." not in result

    def test_returns_string(self):
        path = Path("/home/user/dev/task")
        assert isinstance(session_name_from_path(path), str)


class TestSessionExists:
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_returns_true_when_session_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert session_exists("my-session") is True
        mock_run.assert_called_once_with(
            ["tmux", "has-session", "-t", "my-session"],
            capture_output=True,
        )

    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_returns_false_when_session_missing(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert session_exists("nonexistent") is False

    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_passes_name_exactly(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        session_exists("my-workspace-abc")
        args = mock_run.call_args[0][0]
        assert args[-1] == "my-workspace-abc"
```

### Step 2: Run to verify it fails

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
pytest tests/test_tmux.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'amplifier_workspace.tmux'`

### Step 3: Create `src/amplifier_workspace/tmux.py`

```python
"""Tmux session management for amplifier-workspace.

Tier 2 — only active when config.tmux.enabled is True.
All subprocess calls use list form (no shell=True) to avoid quoting issues.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amplifier_workspace.config import TmuxConfig

__all__ = [
    "session_name_from_path",
    "session_exists",
    "kill_session",
    "create_session",
    "attach_session",
]

SESSION_NAME_MAX = 32  # tmux session name length limit


def session_name_from_path(workdir: Path) -> str:
    """Derive a tmux session name from a workspace directory path.

    Uses the directory's basename, sanitized for tmux compatibility
    and truncated to SESSION_NAME_MAX characters.
    """
    name = workdir.name
    # Replace characters tmux treats specially
    for char in (" ", ":", ".", "/"):
        name = name.replace(char, "-")
    # Collapse repeated dashes and strip leading/trailing dashes
    while "--" in name:
        name = name.replace("--", "-")
    name = name.strip("-")
    # Enforce length limit
    return name[:SESSION_NAME_MAX]


def session_exists(name: str) -> bool:
    """Return True if a tmux session with this name is running."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestSessionNameFromPath tests/test_tmux.py::TestSessionExists -v
```

Expected: All 10 tests PASS.

### Step 5: Commit

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
git add src/amplifier_workspace/tmux.py tests/test_tmux.py
git commit -m "feat(tmux): add tmux.py skeleton, session_name_from_path, session_exists"
```

---

## Task 2: `kill_session`

**Files:**
- Modify: `src/amplifier_workspace/tmux.py`
- Modify: `tests/test_tmux.py`

### Step 1: Add failing tests

Append to `tests/test_tmux.py`:

```python
from amplifier_workspace.tmux import kill_session


class TestKillSession:
    @patch("amplifier_workspace.tmux.session_exists")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_kills_existing_session(self, mock_run, mock_exists):
        mock_exists.return_value = True
        kill_session("my-session")
        mock_run.assert_called_once_with(
            ["tmux", "kill-session", "-t", "my-session"]
        )

    @patch("amplifier_workspace.tmux.session_exists")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_no_op_when_session_missing(self, mock_run, mock_exists):
        mock_exists.return_value = False
        kill_session("nonexistent")
        mock_run.assert_not_called()

    @patch("amplifier_workspace.tmux.session_exists")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_passes_name_to_kill(self, mock_run, mock_exists):
        mock_exists.return_value = True
        kill_session("workspace-abc123")
        args = mock_run.call_args[0][0]
        assert "workspace-abc123" in args
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_tmux.py::TestKillSession -v
```

Expected: `ImportError` — `kill_session` not yet defined.

### Step 3: Add `kill_session` to `src/amplifier_workspace/tmux.py`

Add after `session_exists`:

```python
def kill_session(name: str) -> None:
    """Kill a tmux session if it exists. No-op if it doesn't."""
    if session_exists(name):
        subprocess.run(["tmux", "kill-session", "-t", name])
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestKillSession -v
```

Expected: All 3 tests PASS.

### Step 5: Commit

```bash
git add src/amplifier_workspace/tmux.py tests/test_tmux.py
git commit -m "feat(tmux): add kill_session"
```

---

## Task 3: Rcfile Content Helpers — `_main_rcfile_content` + `_shell_rcfile_content`

**Files:**
- Modify: `src/amplifier_workspace/tmux.py`
- Modify: `tests/test_tmux.py`

### Step 1: Add failing tests

Append to `tests/test_tmux.py`:

```python
from amplifier_workspace.tmux import _main_rcfile_content, _shell_rcfile_content


class TestMainRcfileContent:
    def test_sources_bashrc(self):
        content = _main_rcfile_content(Path("/home/user/dev/task"))
        assert "source ~/.bashrc" in content

    def test_cds_to_workdir(self):
        content = _main_rcfile_content(Path("/home/user/dev/task"))
        assert "cd /home/user/dev/task" in content or "cd '/home/user/dev/task'" in content

    def test_has_sleep_for_terminal_settling(self):
        content = _main_rcfile_content(Path("/home/user/dev/task"))
        assert "sleep 0.5" in content

    def test_checks_for_existing_amplifier_sessions(self):
        content = _main_rcfile_content(Path("/home/user/dev/task"))
        assert "amplifier session list" in content

    def test_exec_amplifier_resume_when_sessions_found(self):
        content = _main_rcfile_content(Path("/home/user/dev/task"))
        assert "amplifier resume" in content

    def test_exec_amplifier_when_no_sessions(self):
        content = _main_rcfile_content(Path("/home/user/dev/task"))
        assert "exec amplifier" in content

    def test_workdir_with_spaces_is_safe(self):
        content = _main_rcfile_content(Path("/home/user/my project"))
        # Should be quoted — the literal unquoted path must not appear
        assert "cd /home/user/my project" not in content
        # But the escaped version must be present
        assert "/home/user/my project" in content


class TestShellRcfileContent:
    def test_sources_bashrc(self):
        content = _shell_rcfile_content(Path("/home/user/dev/task"))
        assert "source ~/.bashrc" in content

    def test_cds_to_workdir(self):
        content = _shell_rcfile_content(Path("/home/user/dev/task"))
        assert "/home/user/dev/task" in content

    def test_no_exec_command(self):
        # Shell window drops to interactive bash — no exec
        content = _shell_rcfile_content(Path("/home/user/dev/task"))
        assert "exec amplifier" not in content
        assert "exec lazygit" not in content
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_tmux.py::TestMainRcfileContent tests/test_tmux.py::TestShellRcfileContent -v
```

Expected: `ImportError` — functions not yet defined.

### Step 3: Add rcfile helpers to `src/amplifier_workspace/tmux.py`

Add after `kill_session`:

```python
def _main_rcfile_content(workdir: Path) -> str:
    """Generate rcfile content for the amplifier window.

    Sources bashrc, cds to workdir, waits for terminal to settle,
    then checks for existing Amplifier sessions:
      - Sessions found: exec amplifier resume
      - No sessions:    exec amplifier
    """
    import shlex

    escaped_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc 2>/dev/null
cd {escaped_workdir}
sleep 0.5
read -t 0.2 -n 10000 discard 2>/dev/null || true

session_output=$(amplifier session list 2>/dev/null)
if echo "$session_output" | grep -q "Session ID"; then
    echo "Existing Amplifier sessions found. Resuming..."
    exec amplifier resume
else
    exec amplifier
fi
"""


def _shell_rcfile_content(workdir: Path) -> str:
    """Generate rcfile content for the shell window.

    Sources bashrc and cds to workdir. No exec — drops to interactive bash.
    """
    import shlex

    escaped_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc 2>/dev/null
cd {escaped_workdir}
"""
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestMainRcfileContent tests/test_tmux.py::TestShellRcfileContent -v
```

Expected: All 10 tests PASS.

### Step 5: Commit

```bash
git add src/amplifier_workspace/tmux.py tests/test_tmux.py
git commit -m "feat(tmux): add _main_rcfile_content and _shell_rcfile_content"
```

---

## Task 4: `_window_rcfile_content` + `_write_rcfiles`

**Files:**
- Modify: `src/amplifier_workspace/tmux.py`
- Modify: `tests/test_tmux.py`

### Step 1: Add failing tests

Append to `tests/test_tmux.py`:

```python
from amplifier_workspace.config import TmuxConfig
from amplifier_workspace.tmux import _window_rcfile_content, _write_rcfiles


class TestWindowRcfileContent:
    def test_sources_bashrc(self):
        content = _window_rcfile_content(Path("/home/user/dev/task"), "lazygit")
        assert "source ~/.bashrc" in content

    def test_cds_to_workdir(self):
        content = _window_rcfile_content(Path("/home/user/dev/task"), "lazygit")
        assert "/home/user/dev/task" in content

    def test_has_sleep(self):
        content = _window_rcfile_content(Path("/home/user/dev/task"), "lazygit")
        assert "sleep 0.3" in content

    def test_execs_command(self):
        content = _window_rcfile_content(Path("/home/user/dev/task"), "lazygit")
        assert "exec lazygit" in content

    def test_command_with_args(self):
        content = _window_rcfile_content(Path("/home/user/dev/task"), "yazi .")
        assert "exec yazi" in content


class TestWriteRcfiles:
    def test_creates_rcfile_dir(self, tmp_path):
        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "shell": ""},
        )
        rcfile_dir = _write_rcfiles(tmp_path / "workspace", config, rcfile_base=tmp_path / "rcfiles")
        assert rcfile_dir.is_dir()

    def test_creates_amplifier_rcfile(self, tmp_path):
        config = TmuxConfig(enabled=True, windows={"amplifier": "", "shell": ""})
        rcfile_dir = _write_rcfiles(tmp_path, config, rcfile_base=tmp_path / "rcfiles")
        assert (rcfile_dir / "amplifier.rc").exists()

    def test_creates_shell_rcfile(self, tmp_path):
        config = TmuxConfig(enabled=True, windows={"amplifier": "", "shell": ""})
        rcfile_dir = _write_rcfiles(tmp_path, config, rcfile_base=tmp_path / "rcfiles")
        assert (rcfile_dir / "shell.rc").exists()

    def test_creates_tool_window_rcfile(self, tmp_path):
        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "shell": "", "git": "lazygit"},
        )
        rcfile_dir = _write_rcfiles(tmp_path, config, rcfile_base=tmp_path / "rcfiles")
        assert (rcfile_dir / "git.rc").exists()

    def test_tool_rcfile_has_correct_command(self, tmp_path):
        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "shell": "", "git": "lazygit"},
        )
        rcfile_dir = _write_rcfiles(tmp_path, config, rcfile_base=tmp_path / "rcfiles")
        content = (rcfile_dir / "git.rc").read_text()
        assert "exec lazygit" in content

    def test_skips_windows_with_empty_command(self, tmp_path):
        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "shell": "", "git": ""},
        )
        rcfile_dir = _write_rcfiles(tmp_path, config, rcfile_base=tmp_path / "rcfiles")
        # Empty command means no rcfile for that window
        assert not (rcfile_dir / "git.rc").exists()

    def test_rcfiles_are_executable(self, tmp_path):
        config = TmuxConfig(enabled=True, windows={"amplifier": "", "shell": ""})
        rcfile_dir = _write_rcfiles(tmp_path, config, rcfile_base=tmp_path / "rcfiles")
        amplifier_rc = rcfile_dir / "amplifier.rc"
        assert amplifier_rc.stat().st_mode & 0o111  # any execute bit set
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_tmux.py::TestWindowRcfileContent tests/test_tmux.py::TestWriteRcfiles -v
```

Expected: `ImportError` — functions not yet defined.

### Step 3: Add `_window_rcfile_content` and `_write_rcfiles` to `src/amplifier_workspace/tmux.py`

Add after `_shell_rcfile_content`:

```python
def _window_rcfile_content(workdir: Path, command: str) -> str:
    """Generate rcfile content for a tool window (lazygit, yazi, etc.).

    Sources bashrc, cds to workdir, waits briefly, then execs the command.
    """
    import shlex

    escaped_workdir = shlex.quote(str(workdir))
    return f"""\
source ~/.bashrc 2>/dev/null
cd {escaped_workdir}
sleep 0.3
exec {command}
"""


def _write_rcfiles(
    workdir: Path,
    config: "TmuxConfig",
    *,
    rcfile_base: Path | None = None,
) -> Path:
    """Write rcfiles for all configured windows. Returns the rcfile directory.

    Args:
        workdir: The workspace directory (used in cd commands).
        config: The TmuxConfig with windows dict.
        rcfile_base: Override the base directory (used in tests). If None,
                     defaults to /tmp/amplifier-workspace-rcfiles-{pid}.
    """
    if rcfile_base is None:
        rcfile_base = (
            Path(tempfile.gettempdir()) / f"amplifier-workspace-rcfiles-{os.getpid()}"
        )
    rcfile_base.mkdir(parents=True, exist_ok=True)

    # Always write amplifier and shell rcfiles
    amplifier_rc = rcfile_base / "amplifier.rc"
    amplifier_rc.write_text(_main_rcfile_content(workdir))
    amplifier_rc.chmod(0o755)

    shell_rc = rcfile_base / "shell.rc"
    shell_rc.write_text(_shell_rcfile_content(workdir))
    shell_rc.chmod(0o755)

    # Write tool window rcfiles (skip amplifier, shell, and empty commands)
    for window_name, command in config.windows.items():
        if window_name in ("amplifier", "shell"):
            continue
        if not command:
            continue
        rc = rcfile_base / f"{window_name}.rc"
        rc.write_text(_window_rcfile_content(workdir, command))
        rc.chmod(0o755)

    return rcfile_base
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestWindowRcfileContent tests/test_tmux.py::TestWriteRcfiles -v
```

Expected: All 12 tests PASS.

### Step 5: Commit

```bash
git add src/amplifier_workspace/tmux.py tests/test_tmux.py
git commit -m "feat(tmux): add _window_rcfile_content and _write_rcfiles"
```

---

## Task 5: `create_session` — Session Creation + Amplifier Window

**Files:**
- Modify: `src/amplifier_workspace/tmux.py`
- Modify: `tests/test_tmux.py`

### Step 1: Add failing tests

Append to `tests/test_tmux.py`:

```python
from amplifier_workspace.tmux import create_session


class TestCreateSession:
    """Tests for create_session. All tmux subprocess calls are mocked."""

    def _minimal_config(self) -> TmuxConfig:
        """Minimal config with just amplifier window (no other windows)."""
        return TmuxConfig(enabled=True, windows={"amplifier": ""})

    def _full_config(self) -> TmuxConfig:
        """Full config with all standard windows."""
        return TmuxConfig(
            enabled=True,
            windows={
                "amplifier": "",
                "git": "lazygit",
                "files": "yazi",
                "shell": "",
            },
        )

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_creates_new_session_with_amplifier_window(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        create_session(workdir, self._minimal_config())

        # Find the new-session call
        calls = [c[0][0] for c in mock_run.call_args_list]
        new_session_call = next(c for c in calls if "new-session" in c)
        assert "-d" in new_session_call
        assert "-s" in new_session_call
        assert "-n" in new_session_call
        amplifier_idx = new_session_call.index("-n") + 1
        assert new_session_call[amplifier_idx] == "amplifier"

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_session_name_derived_from_workdir(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/fix-auth")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        create_session(workdir, self._minimal_config())

        calls = [c[0][0] for c in mock_run.call_args_list]
        new_session_call = next(c for c in calls if "new-session" in c)
        session_idx = new_session_call.index("-s") + 1
        assert new_session_call[session_idx] == "fix-auth"

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_uses_amplifier_rcfile_for_main_window(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        rcfile_dir = Path("/tmp/test-rcfiles")
        mock_write.return_value = rcfile_dir
        mock_run.return_value = MagicMock(returncode=0)

        create_session(workdir, self._minimal_config())

        calls = [c[0][0] for c in mock_run.call_args_list]
        new_session_call = next(c for c in calls if "new-session" in c)
        # Last arg is the shell command — must reference amplifier.rc
        shell_cmd = new_session_call[-1]
        assert "amplifier.rc" in shell_cmd
        assert "--rcfile" in shell_cmd

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_selects_amplifier_window_at_end(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        create_session(workdir, self._full_config())

        calls = [c[0][0] for c in mock_run.call_args_list]
        select_call = next((c for c in calls if "select-window" in c), None)
        assert select_call is not None
        # select-window -t <session>:amplifier
        target = select_call[select_call.index("-t") + 1]
        assert target.endswith(":amplifier")

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_calls_write_rcfiles(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        config = self._minimal_config()
        create_session(workdir, config)

        mock_write.assert_called_once_with(workdir, config)
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_tmux.py::TestCreateSession -v
```

Expected: `ImportError` — `create_session` not yet defined.

### Step 3: Add `create_session` skeleton to `src/amplifier_workspace/tmux.py`

Add after `_write_rcfiles`:

```python
def create_session(workdir: Path, config: "TmuxConfig") -> None:
    """Create a tmux session with windows per config.

    Window creation order:
      1. amplifier window (always first, uses resume detection rcfile)
      2. tool windows in config.windows order (skip amplifier and shell keys)
      3. shell window (always last, two-pane horizontal split)

    Finally selects the amplifier window so it is focused on attach.

    Args:
        workdir: Workspace directory — used for cd in rcfiles.
        config: TmuxConfig with enabled=True and a windows dict.
    """
    name = session_name_from_path(workdir)
    rcfile_dir = _write_rcfiles(workdir, config)
    amplifier_rc = rcfile_dir / "amplifier.rc"

    # 1. Create session with amplifier window (detached)
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s", name,
            "-n", "amplifier",
            f"exec bash --rcfile '{amplifier_rc}'",
        ],
        check=True,
    )

    # 2. Tool windows (skip amplifier, shell — handled separately)
    for window_name, command in config.windows.items():
        if window_name in ("amplifier", "shell"):
            continue
        if not command:
            continue
        window_rc = rcfile_dir / f"{window_name}.rc"
        subprocess.run(
            [
                "tmux",
                "new-window",
                "-t", name,
                "-n", window_name,
                f"exec bash --rcfile '{window_rc}'",
            ],
            check=True,
        )

    # 3. Shell window — two-pane horizontal split (always last)
    if "shell" in config.windows:
        shell_rc = rcfile_dir / "shell.rc"
        subprocess.run(
            [
                "tmux",
                "new-window",
                "-t", name,
                "-n", "shell",
                f"exec bash --rcfile '{shell_rc}'",
            ],
            check=True,
        )
        subprocess.run(
            [
                "tmux",
                "split-window",
                "-h",
                "-t", f"{name}:shell",
                f"exec bash --rcfile '{shell_rc}'",
            ],
            check=True,
        )

    # 4. Select amplifier window so we attach to it
    subprocess.run(
        ["tmux", "select-window", "-t", f"{name}:amplifier"],
        check=True,
    )
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestCreateSession -v
```

Expected: All 5 tests PASS.

### Step 5: Commit

```bash
git add src/amplifier_workspace/tmux.py tests/test_tmux.py
git commit -m "feat(tmux): add create_session"
```

---

## Task 6: `create_session` — Tool Windows + Shell Window Verification

**Files:**
- Modify: `tests/test_tmux.py`

These tests verify the window-creation behavior added in Task 5 in more detail.

### Step 1: Add failing tests

Append to `tests/test_tmux.py`:

```python
class TestCreateSessionWindows:
    """Verify tool windows and shell window are created correctly."""

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_tool_windows_created_before_shell(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "git": "lazygit", "shell": ""},
        )
        create_session(workdir, config)

        calls = [c[0][0] for c in mock_run.call_args_list]
        new_window_calls = [c for c in calls if "new-window" in c]
        # First new-window is tool window (git), second is shell
        names = [c[c.index("-n") + 1] for c in new_window_calls]
        assert names.index("git") < names.index("shell")

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_shell_window_gets_horizontal_split(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        config = TmuxConfig(enabled=True, windows={"amplifier": "", "shell": ""})
        create_session(workdir, config)

        calls = [c[0][0] for c in mock_run.call_args_list]
        split_calls = [c for c in calls if "split-window" in c]
        assert len(split_calls) == 1
        assert "-h" in split_calls[0]

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_no_split_when_no_shell_window(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        config = TmuxConfig(enabled=True, windows={"amplifier": ""})
        create_session(workdir, config)

        calls = [c[0][0] for c in mock_run.call_args_list]
        split_calls = [c for c in calls if "split-window" in c]
        assert len(split_calls) == 0

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_windows_with_empty_command_skipped(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        mock_write.return_value = Path("/tmp/rcfiles")
        mock_run.return_value = MagicMock(returncode=0)

        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "git": "", "shell": ""},
        )
        create_session(workdir, config)

        calls = [c[0][0] for c in mock_run.call_args_list]
        new_window_calls = [c for c in calls if "new-window" in c]
        names = [c[c.index("-n") + 1] for c in new_window_calls]
        # "git" has empty command — should not appear
        assert "git" not in names

    @patch("amplifier_workspace.tmux._write_rcfiles")
    @patch("amplifier_workspace.tmux.subprocess.run")
    def test_tool_window_uses_named_rcfile(self, mock_run, mock_write):
        workdir = Path("/home/user/dev/task")
        rcfile_dir = Path("/tmp/test-rcfiles")
        mock_write.return_value = rcfile_dir
        mock_run.return_value = MagicMock(returncode=0)

        config = TmuxConfig(
            enabled=True,
            windows={"amplifier": "", "git": "lazygit"},
        )
        create_session(workdir, config)

        calls = [c[0][0] for c in mock_run.call_args_list]
        new_window_calls = [c for c in calls if "new-window" in c]
        git_call = next(c for c in new_window_calls if "git" in c[c.index("-n") + 1])
        shell_cmd = git_call[-1]
        assert "git.rc" in shell_cmd
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_tmux.py::TestCreateSessionWindows -v
```

Expected: All 5 tests FAIL (function exists but logic not tested yet — some may pass incidentally; verify by inspecting output).

### Step 3: No implementation change needed

The implementation from Task 5 already covers these cases. Run and verify.

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestCreateSessionWindows -v
```

Expected: All 5 tests PASS.

### Step 5: Run full tmux test suite so far

```bash
pytest tests/test_tmux.py -v
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add tests/test_tmux.py
git commit -m "test(tmux): add window ordering and shell split verification tests"
```

---

## Task 7: `attach_session`

**Files:**
- Modify: `src/amplifier_workspace/tmux.py`
- Modify: `tests/test_tmux.py`

### Step 1: Add failing tests

Append to `tests/test_tmux.py`:

```python
import sys
from amplifier_workspace.tmux import attach_session


class TestAttachSession:
    @patch.dict(os.environ, {}, clear=True)  # TMUX not set
    @patch("amplifier_workspace.tmux.os.execvp")
    def test_attach_outside_tmux_posix(self, mock_execvp):
        if sys.platform == "win32":
            return  # skip on Windows
        attach_session("my-session")
        mock_execvp.assert_called_once_with(
            "tmux", ["tmux", "attach-session", "-t", "my-session"]
        )

    @patch.dict(os.environ, {"TMUX": "/tmp/tmux-123/default,456,0"})
    @patch("amplifier_workspace.tmux.os.execvp")
    def test_switch_client_inside_tmux_posix(self, mock_execvp):
        if sys.platform == "win32":
            return  # skip on Windows
        attach_session("my-session")
        mock_execvp.assert_called_once_with(
            "tmux", ["tmux", "switch-client", "-t", "my-session"]
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("amplifier_workspace.tmux.os.execvp")
    def test_passes_session_name(self, mock_execvp):
        if sys.platform == "win32":
            return
        attach_session("workspace-fix-auth")
        args = mock_execvp.call_args[0][1]
        assert "workspace-fix-auth" in args
```

Note: `patch.dict(os.environ, {}, clear=True)` clears env vars for the test. Import `os` at top of test file if not already there.

**Add `import os` to the imports at the top of `tests/test_tmux.py`** (it is needed for `patch.dict(os.environ, ...)`):

```python
import os  # add this line near the other imports at the top
from unittest.mock import MagicMock, patch, patch  # already there
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_tmux.py::TestAttachSession -v
```

Expected: `ImportError` — `attach_session` not yet defined (or attribute error on os.environ patch).

### Step 3: Add `attach_session` to `src/amplifier_workspace/tmux.py`

Add after `create_session`:

```python
def attach_session(name: str) -> None:
    """Attach to (or switch to) a tmux session. Never returns on POSIX.

    - Outside tmux: ``tmux attach-session -t <name>``
    - Inside tmux:  ``tmux switch-client -t <name>``

    Uses ``os.execvp`` on POSIX so this process is replaced by tmux
    (clean process table, no zombie). On Windows, falls back to
    subprocess.run + sys.exit.
    """
    import sys

    inside_tmux = bool(os.environ.get("TMUX"))
    tmux_cmd = "switch-client" if inside_tmux else "attach-session"
    argv = ["tmux", tmux_cmd, "-t", name]

    if sys.platform == "win32":
        result = subprocess.run(argv)
        sys.exit(result.returncode)
    else:
        os.execvp("tmux", argv)
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_tmux.py::TestAttachSession -v
```

Expected: All 3 PASS (or 2 on Windows — platform-skipped tests show as PASS in pytest).

### Step 5: Run full tmux test suite

```bash
pytest tests/test_tmux.py -v
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/amplifier_workspace/tmux.py tests/test_tmux.py
git commit -m "feat(tmux): add attach_session (execvp-based, handles inside/outside tmux)"
```

---

## Task 8: `workspace.py` — Kill Flag + Tmux-Aware Destroy

**Files:**
- Modify: `src/amplifier_workspace/workspace.py`
- Modify: `tests/test_workspace.py`

### Step 1: Add failing tests

Open `tests/test_workspace.py` and append:

```python
from unittest.mock import patch, MagicMock
from pathlib import Path

from amplifier_workspace.config import AppConfig, TmuxConfig, WorkspaceSection
from amplifier_workspace.workspace import run_workspace


def _config_with_tmux(enabled: bool = True) -> AppConfig:
    """Build an AppConfig with tmux enabled or disabled."""
    return AppConfig(
        workspace=WorkspaceSection(default_repos=[], bundle="amplifier-dev"),
        tmux=TmuxConfig(
            enabled=enabled,
            windows={"amplifier": "", "shell": ""},
        ),
    )


class TestRunWorkspaceKillFlag:
    @patch("amplifier_workspace.workspace.tmux")
    def test_kill_calls_kill_session_when_tmux_enabled(self, mock_tmux, tmp_path):
        mock_tmux.session_name_from_path.return_value = "task"
        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config, kill=True)
        mock_tmux.kill_session.assert_called_once_with("task")

    @patch("amplifier_workspace.workspace.tmux")
    def test_kill_returns_without_modifying_directory(self, mock_tmux, tmp_path):
        mock_tmux.session_name_from_path.return_value = "task"
        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config, kill=True)
        assert tmp_path.exists()  # directory must still be there

    def test_kill_no_op_when_tmux_disabled(self, tmp_path, capsys):
        config = _config_with_tmux(enabled=False)
        # Should not raise — just silently does nothing (or prints a note)
        run_workspace(tmp_path, config, kill=True)
        # Directory untouched
        assert tmp_path.exists()


class TestRunWorkspaceDestroyWithTmux:
    @patch("amplifier_workspace.workspace.tmux")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    def test_destroy_kills_tmux_session_before_rmtree(self, mock_rmtree, mock_tmux, tmp_path):
        mock_tmux.session_name_from_path.return_value = "task"
        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config, destroy=True)
        mock_tmux.kill_session.assert_called_once_with("task")

    @patch("amplifier_workspace.workspace.tmux")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    def test_destroy_still_removes_directory(self, mock_rmtree, mock_tmux, tmp_path):
        mock_tmux.session_name_from_path.return_value = "task"
        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_called_once_with(tmp_path)
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_workspace.py::TestRunWorkspaceKillFlag tests/test_workspace.py::TestRunWorkspaceDestroyWithTmux -v
```

Expected: Tests fail — `kill` flag not yet wired up and tmux not yet imported.

### Step 3: Modify `src/amplifier_workspace/workspace.py`

Find the `run_workspace` function. It should look roughly like:

```python
def run_workspace(workdir: Path, config: AppConfig, *, destroy: bool = False, fresh: bool = False, kill: bool = False) -> None:
    if destroy:
        if workdir.exists():
            shutil.rmtree(workdir)
        return
    ...
```

**Replace the `destroy` block and add the `kill` block and tmux import:**

```python
from amplifier_workspace import tmux  # add this import at the top of workspace.py


def run_workspace(
    workdir: Path,
    config: AppConfig,
    *,
    destroy: bool = False,
    fresh: bool = False,
    kill: bool = False,
) -> None:
    """Create, resume, kill, or destroy a workspace.

    Args:
        workdir:  The workspace directory path.
        config:   Loaded AppConfig.
        destroy:  Kill tmux session AND delete the directory.
        fresh:    Kill tmux session, delete directory, then recreate.
        kill:     Kill the tmux session only — leave directory intact.
    """
    # -- kill: stop the session, leave files alone --------------------------
    if kill:
        if config.tmux.enabled:
            name = tmux.session_name_from_path(workdir)
            tmux.kill_session(name)
        return

    # -- destroy: stop session then delete directory ------------------------
    if destroy:
        if config.tmux.enabled:
            name = tmux.session_name_from_path(workdir)
            tmux.kill_session(name)
        if workdir.exists():
            shutil.rmtree(workdir)
        return

    # -- fresh: destroy then fall through to recreate -----------------------
    if fresh:
        if config.tmux.enabled:
            name = tmux.session_name_from_path(workdir)
            tmux.kill_session(name)
        if workdir.exists():
            shutil.rmtree(workdir)

    # -- normal path: setup then launch -------------------------------------
    setup_workspace(workdir, config)

    if config.tmux.enabled:
        _launch_with_tmux(workdir, config)
    else:
        _launch_amplifier(workdir)
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_workspace.py::TestRunWorkspaceKillFlag tests/test_workspace.py::TestRunWorkspaceDestroyWithTmux -v
```

Expected: All 5 tests PASS.

### Step 5: Run full workspace tests to catch regressions

```bash
pytest tests/test_workspace.py -v
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/amplifier_workspace/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): wire kill flag and tmux-aware destroy into run_workspace"
```

---

## Task 9: `workspace.py` — `_launch_with_tmux`

**Files:**
- Modify: `src/amplifier_workspace/workspace.py`
- Modify: `tests/test_workspace.py`

### Step 1: Add failing tests

Append to `tests/test_workspace.py`:

```python
class TestLaunchWithTmux:
    @patch("amplifier_workspace.workspace.tmux")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_creates_and_attaches_new_session(self, mock_setup, mock_tmux, tmp_path):
        mock_tmux.session_name_from_path.return_value = "task"
        mock_tmux.session_exists.return_value = False

        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config)

        mock_tmux.create_session.assert_called_once_with(tmp_path, config.tmux)
        mock_tmux.attach_session.assert_called_once_with("task")

    @patch("amplifier_workspace.workspace.tmux")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_reattaches_existing_session_without_create(self, mock_setup, mock_tmux, tmp_path):
        mock_tmux.session_name_from_path.return_value = "task"
        mock_tmux.session_exists.return_value = True

        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config)

        mock_tmux.create_session.assert_not_called()
        mock_tmux.attach_session.assert_called_once_with("task")

    @patch("amplifier_workspace.workspace.tmux")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_setup_runs_before_session_launch(self, mock_setup, mock_tmux, tmp_path):
        call_order = []
        mock_setup.side_effect = lambda *a: call_order.append("setup")
        mock_tmux.session_exists.return_value = False
        mock_tmux.session_name_from_path.return_value = "task"
        mock_tmux.create_session.side_effect = lambda *a: call_order.append("create")

        config = _config_with_tmux(enabled=True)
        run_workspace(tmp_path, config)

        assert call_order.index("setup") < call_order.index("create")

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    def test_tier1_fallback_when_tmux_disabled(self, mock_setup, mock_launch, tmp_path):
        config = _config_with_tmux(enabled=False)
        run_workspace(tmp_path, config)
        mock_launch.assert_called_once_with(tmp_path)
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_workspace.py::TestLaunchWithTmux -v
```

Expected: Tests fail — `_launch_with_tmux` does not exist yet.

### Step 3: Add `_launch_with_tmux` to `src/amplifier_workspace/workspace.py`

Add this private function near the end of `workspace.py`:

```python
def _launch_with_tmux(workdir: Path, config: AppConfig) -> None:
    """Create or reattach a tmux session for this workspace.

    - Session exists  → attach (never returns)
    - Session missing → create all windows, then attach (never returns)
    """
    name = tmux.session_name_from_path(workdir)
    if tmux.session_exists(name):
        tmux.attach_session(name)
    else:
        tmux.create_session(workdir, config.tmux)
        tmux.attach_session(name)
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_workspace.py::TestLaunchWithTmux -v
```

Expected: All 4 tests PASS.

### Step 5: Run full workspace + tmux suites

```bash
pytest tests/test_workspace.py tests/test_tmux.py -v
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/amplifier_workspace/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): add _launch_with_tmux (create or reattach tmux session)"
```

---

## Task 10: `cli.py` — Activate the `-k` Flag

**Files:**
- Modify: `src/amplifier_workspace/cli.py`
- Modify: `tests/test_cli.py`

### Step 1: Add failing tests

Open `tests/test_cli.py` and append:

```python
from unittest.mock import patch, MagicMock
from amplifier_workspace.cli import main


class TestCliKillFlag:
    @patch("amplifier_workspace.cli.run_workspace")
    @patch("amplifier_workspace.cli.load_config")
    def test_kill_flag_passes_kill_true_to_run_workspace(self, mock_load, mock_run):
        mock_load.return_value = MagicMock()
        main(["-k", "/home/user/dev/task"])
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("kill") is True

    @patch("amplifier_workspace.cli.run_workspace")
    @patch("amplifier_workspace.cli.load_config")
    def test_no_kill_flag_passes_kill_false(self, mock_load, mock_run):
        mock_load.return_value = MagicMock()
        main(["/home/user/dev/task"])
        _, kwargs = mock_run.call_args
        assert kwargs.get("kill", False) is False

    @patch("amplifier_workspace.cli.run_workspace")
    @patch("amplifier_workspace.cli.load_config")
    def test_kill_flag_passes_correct_workdir(self, mock_load, mock_run):
        mock_load.return_value = MagicMock()
        main(["-k", "/home/user/dev/task"])
        args, _ = mock_run.call_args
        workdir = args[0]
        assert workdir.name == "task"
```

**Note:** `main` must accept an optional `argv` list for testability. If `cli.py`'s `main()` doesn't accept `argv`, you'll need to make this small change to the signature first:

```python
# In cli.py — change:
def main() -> None:
    args = parser.parse_args()

# To:
def main(argv: list[str] | None = None) -> None:
    args = parser.parse_args(argv)
```

Make that change to `cli.py` now if it isn't already there.

### Step 2: Run to verify it fails

```bash
pytest tests/test_cli.py::TestCliKillFlag -v
```

Expected: Tests fail — `kill` flag may not be forwarded to `run_workspace` yet.

### Step 3: Verify `cli.py` routes the `-k` flag

Find the section in `cli.py` that handles the path argument (looks like):

```python
if args.path:
    workdir = Path(args.path).expanduser().resolve()
    run_workspace(workdir, config, destroy=args.destroy, fresh=args.fresh)
```

Update it to include `kill`:

```python
if args.path:
    workdir = Path(args.path).expanduser().resolve()
    run_workspace(
        workdir,
        config,
        destroy=args.destroy,
        fresh=args.fresh,
        kill=args.kill,
    )
```

Verify the `-k` argument is defined in the parser. It should look like:

```python
parser.add_argument(
    "-k", "--kill",
    action="store_true",
    help="Kill the tmux session for this workspace (directory is preserved).",
)
```

If this line is missing, add it.

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_cli.py::TestCliKillFlag -v
```

Expected: All 3 tests PASS.

### Step 5: Run full CLI test suite

```bash
pytest tests/test_cli.py -v
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/amplifier_workspace/cli.py tests/test_cli.py
git commit -m "feat(cli): wire -k flag through to run_workspace(kill=True)"
```

---

## Task 11: `wizard.py` — Step 4 (Session Manager Opt-In)

**Files:**
- Modify: `src/amplifier_workspace/wizard.py`
- Modify: `tests/test_wizard.py`

### Step 1: Add failing tests

Open `tests/test_wizard.py` and append:

```python
from unittest.mock import patch, call
from amplifier_workspace.wizard import _step4_session_manager


class TestStep4SessionManager:
    def test_disabled_by_default_when_user_says_no(self):
        answers = {}
        with patch("amplifier_workspace.wizard._prompt_bool", return_value=False):
            _step4_session_manager(answers)
        assert answers["tmux_enabled"] is False

    def test_enabled_when_user_says_yes_and_tmux_found(self):
        answers = {}
        with (
            patch("amplifier_workspace.wizard._prompt_bool", return_value=True),
            patch("amplifier_workspace.wizard.shutil.which", return_value="/usr/bin/tmux"),
        ):
            _step4_session_manager(answers)
        assert answers["tmux_enabled"] is True

    def test_base_windows_set_when_enabled(self):
        answers = {}
        with (
            patch("amplifier_workspace.wizard._prompt_bool", return_value=True),
            patch("amplifier_workspace.wizard.shutil.which", return_value="/usr/bin/tmux"),
        ):
            _step4_session_manager(answers)
        assert "amplifier" in answers["tmux_windows"]
        assert "shell" in answers["tmux_windows"]

    def test_tmux_not_found_install_declined_leaves_disabled(self):
        answers = {}
        # First _prompt_bool call: "Enable session manager?" -> True
        # Second _prompt_bool call: "Install tmux?" -> False
        prompt_responses = [True, False]
        with (
            patch("amplifier_workspace.wizard._prompt_bool", side_effect=prompt_responses),
            patch("amplifier_workspace.wizard.shutil.which", return_value=None),
        ):
            _step4_session_manager(answers)
        assert answers["tmux_enabled"] is False

    def test_tool_window_added_when_found_and_user_says_yes(self):
        answers = {}
        # Prompt responses: enable=True, add-lazygit=True, add-yazi=False
        prompt_responses = [True, True, False]

        def which_side_effect(cmd):
            return "/usr/bin/tmux" if cmd == "tmux" else "/usr/bin/lazygit" if cmd == "lazygit" else None

        with (
            patch("amplifier_workspace.wizard._prompt_bool", side_effect=prompt_responses),
            patch("amplifier_workspace.wizard.shutil.which", side_effect=which_side_effect),
        ):
            _step4_session_manager(answers)

        assert answers["tmux_windows"].get("git") == "lazygit"
        assert "files" not in answers["tmux_windows"]

    def test_tool_window_skipped_when_user_declines(self):
        answers = {}
        # enable=True, add-lazygit=False, add-yazi=False
        prompt_responses = [True, False, False]

        with (
            patch("amplifier_workspace.wizard._prompt_bool", side_effect=prompt_responses),
            patch("amplifier_workspace.wizard.shutil.which", return_value="/usr/bin/tmux"),
        ):
            _step4_session_manager(answers)

        assert "git" not in answers["tmux_windows"]
        assert "files" not in answers["tmux_windows"]
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_wizard.py::TestStep4SessionManager -v
```

Expected: `ImportError` — `_step4_session_manager` not yet defined.

### Step 3: Add `_step4_session_manager` to `src/amplifier_workspace/wizard.py`

Add this function near the other `_step*` functions:

```python
def _step4_session_manager(answers: dict) -> None:
    """Step 4 of the wizard: opt-in to tmux session manager (Tier 2).

    Checks for tmux, optionally offers to install it, then walks through
    each optional tool window (lazygit, yazi) and offers to install each.
    """
    import shutil
    from amplifier_workspace.install import install_tool

    print("\nStep 4 of 4: Session manager (optional)")
    print("  Enables tmux sessions with a multi-window workspace layout.")
    print("  Requires: tmux\n")

    enabled = _prompt_bool("Enable session manager?", default=False)
    if not enabled:
        answers["tmux_enabled"] = False
        return

    # Check for tmux
    if not shutil.which("tmux"):
        print("  tmux not found.")
        install_it = _prompt_bool("  Install tmux?", default=True)
        if install_it:
            success, msg = install_tool("tmux")
            if not success:
                print(f"  ✗ Install failed. Install manually: {msg}")
                answers["tmux_enabled"] = False
                return
            print("  ✓ tmux installed.")
        else:
            answers["tmux_enabled"] = False
            return

    answers["tmux_enabled"] = True
    answers["tmux_windows"] = {"amplifier": "", "shell": ""}

    # Per-tool window opt-in: (tool display name, window key, command)
    optional_tools = [
        ("lazygit", "git", "lazygit"),
        ("yazi", "files", "yazi"),
    ]

    for tool_name, window_key, command in optional_tools:
        print(f"\n  {tool_name} window:")
        if not shutil.which(command):
            print(f"  {tool_name} not found.")
            choice_responses = ["y", "n", "skip"]
            choice = _prompt_bool(f"  Install {tool_name}?", default=False)
            if choice:
                success, msg = install_tool(command)
                if success:
                    print(f"  ✓ {tool_name} installed.")
                    answers["tmux_windows"][window_key] = command
                else:
                    print(f"  ✗ Install failed. Install manually: {msg}")
                    print(
                        f"    Add later: amplifier-workspace config set "
                        f"tmux.windows.{window_key} {command}"
                    )
        else:
            add_it = _prompt_bool(f"  Add {tool_name} window?", default=True)
            if add_it:
                answers["tmux_windows"][window_key] = command
```

Now wire Step 4 into `run_wizard()`. Find the section that calls steps 1–3 and add step 4:

```python
def run_wizard() -> None:
    print("amplifier-workspace setup\n")
    answers: dict = {}
    try:
        _step1_default_repos(answers)
        _step2_bundle(answers)
        _step3_agents_template(answers)
        _step4_session_manager(answers)   # <-- add this line
        _write_config(answers)
        print("\nConfig written to ~/.config/amplifier-workspace/config.toml")
        print("\nRun `amplifier-workspace doctor` to verify your setup.")
    except KeyboardInterrupt:
        print("\n\nSetup cancelled. No config was written.")
```

Also ensure `_write_config` handles the `tmux_enabled` and `tmux_windows` keys. Find `_write_config` and add tmux handling:

```python
def _write_config(answers: dict) -> None:
    """Write the collected wizard answers to config.toml."""
    from amplifier_workspace.config_manager import write_config
    from amplifier_workspace.config import AppConfig, WorkspaceSection, TmuxConfig

    workspace = WorkspaceSection(
        default_repos=answers.get("default_repos", []),
        bundle=answers.get("bundle", "amplifier-dev"),
        agents_template=answers.get("agents_template", ""),
    )
    tmux_windows = answers.get("tmux_windows", {}) if answers.get("tmux_enabled") else {}
    tmux = TmuxConfig(
        enabled=answers.get("tmux_enabled", False),
        windows=tmux_windows,
    )
    config = AppConfig(workspace=workspace, tmux=tmux)
    write_config(config)
```

If `_write_config` already exists with different logic, merge the tmux fields into it rather than replacing it.

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_wizard.py::TestStep4SessionManager -v
```

Expected: All 6 tests PASS.

### Step 5: Run full wizard test suite

```bash
pytest tests/test_wizard.py -v
```

Expected: All tests PASS.

### Step 6: Commit

```bash
git add src/amplifier_workspace/wizard.py tests/test_wizard.py
git commit -m "feat(wizard): add Step 4 — session manager opt-in with per-tool window prompts"
```

---

## Task 12: `doctor.py` — Tmux-Aware Health Checks

**Files:**
- Modify: `src/amplifier_workspace/doctor.py`
- Modify: `tests/test_doctor.py`

### Step 1: Add failing tests

Open `tests/test_doctor.py` and append:

```python
from unittest.mock import patch, MagicMock
from amplifier_workspace.config import AppConfig, TmuxConfig, WorkspaceSection
from amplifier_workspace.doctor import run_doctor


def _config_tmux_enabled(windows: dict | None = None) -> AppConfig:
    if windows is None:
        windows = {"amplifier": "", "shell": ""}
    return AppConfig(
        workspace=WorkspaceSection(default_repos=[], bundle="amplifier-dev"),
        tmux=TmuxConfig(enabled=True, windows=windows),
    )


def _config_tmux_disabled() -> AppConfig:
    return AppConfig(
        workspace=WorkspaceSection(default_repos=[], bundle="amplifier-dev"),
        tmux=TmuxConfig(enabled=False),
    )


class TestDoctorTmuxChecks:
    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_tmux_check_runs_when_enabled(self, mock_which, mock_load, capsys):
        mock_load.return_value = _config_tmux_enabled()
        mock_which.return_value = "/usr/bin/tmux"

        run_doctor()

        captured = capsys.readouterr()
        assert "tmux" in captured.out.lower()

    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_tmux_skipped_when_disabled(self, mock_which, mock_load, capsys):
        mock_load.return_value = _config_tmux_disabled()
        mock_which.return_value = "/usr/bin/tmux"

        run_doctor()

        captured = capsys.readouterr()
        assert "skipped" in captured.out.lower() or "not enabled" in captured.out.lower()

    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_tmux_not_found_is_a_failure(self, mock_which, mock_load):
        mock_load.return_value = _config_tmux_enabled()

        def which_side_effect(cmd):
            return None if cmd == "tmux" else "/usr/bin/" + cmd

        mock_which.side_effect = which_side_effect

        result = run_doctor()
        assert result != 0  # failure exit code

    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_tool_window_checked_when_configured(self, mock_which, mock_load, capsys):
        mock_load.return_value = _config_tmux_enabled(
            windows={"amplifier": "", "shell": "", "git": "lazygit"}
        )
        mock_which.return_value = "/usr/bin/lazygit"

        run_doctor()

        captured = capsys.readouterr()
        assert "lazygit" in captured.out.lower()

    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_missing_tool_window_is_a_failure(self, mock_which, mock_load):
        mock_load.return_value = _config_tmux_enabled(
            windows={"amplifier": "", "shell": "", "git": "lazygit"}
        )

        def which_side_effect(cmd):
            return None if cmd == "lazygit" else "/usr/bin/" + cmd

        mock_which.side_effect = which_side_effect

        result = run_doctor()
        assert result != 0

    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_missing_tool_shows_install_hint(self, mock_which, mock_load, capsys):
        mock_load.return_value = _config_tmux_enabled(
            windows={"amplifier": "", "shell": "", "git": "lazygit"}
        )

        def which_side_effect(cmd):
            return None if cmd == "lazygit" else "/usr/bin/" + cmd

        mock_which.side_effect = which_side_effect

        run_doctor()

        captured = capsys.readouterr()
        # Should suggest how to remove the window from config
        assert "config" in captured.out.lower() or "remove" in captured.out.lower() or "install" in captured.out.lower()

    @patch("amplifier_workspace.doctor.load_config")
    @patch("amplifier_workspace.doctor.shutil.which")
    def test_windows_with_empty_command_not_checked(self, mock_which, mock_load, capsys):
        """Windows with empty command are always present (amplifier, shell) — skip tool check."""
        mock_load.return_value = _config_tmux_enabled(
            windows={"amplifier": "", "shell": ""}
        )
        mock_which.return_value = "/usr/bin/tmux"

        run_doctor()

        # Should pass — no tool windows to check
        captured = capsys.readouterr()
        # No failures
        assert "0 issue" in captured.out or "all checks passed" in captured.out.lower()
```

### Step 2: Run to verify it fails

```bash
pytest tests/test_doctor.py::TestDoctorTmuxChecks -v
```

Expected: Several tests fail — tmux checks not yet in `run_doctor`.

### Step 3: Add tmux checks to `src/amplifier_workspace/doctor.py`

Find `run_doctor()`. It will look roughly like:

```python
def run_doctor() -> int:
    config = load_config()
    failures = 0
    # ... existing checks ...
    # Summary
    if failures == 0:
        print("All checks passed.")
    else:
        print(f"{failures} issue(s) found. Run `amplifier-workspace setup` to reconfigure.")
    return 0 if failures == 0 else 1
```

Add the tmux block **before the summary**:

```python
    # ---- Tmux checks (only when tmux.enabled = true) ----------------------
    if config.tmux.enabled:
        tmux_found = shutil.which("tmux") is not None
        tmux_version = _get_version("tmux", "-V") if tmux_found else "not found"
        _print_check("tmux (session manager)", tmux_found, tmux_version)
        if not tmux_found:
            failures += 1

        # Count configured windows
        window_count = len(config.tmux.windows)
        _print_check("tmux windows", True, f"{window_count} configured")

        # Check each tool window (skip windows with empty command)
        for window_name, command in config.tmux.windows.items():
            if not command:
                continue  # amplifier and shell have no tool binary to check
            tool_found = shutil.which(command) is not None
            if tool_found:
                detail = command
            else:
                hint = get_install_hint(command)
                detail = f"{command} not found"
                if hint:
                    detail += f" — {hint}"
                detail += (
                    f"\n       or remove: amplifier-workspace config remove "
                    f"tmux.windows.{window_name}"
                )
                failures += 1
            _print_check(f"  {window_name} ({command})", tool_found, detail)
    else:
        _print_check("tmux", None, "skipped (not enabled)")
```

Make sure `shutil` is imported at the top of `doctor.py`. If `get_install_hint` doesn't exist yet, add a simple stub:

```python
def get_install_hint(command: str) -> str:
    """Return a platform-appropriate install hint for a known command."""
    from amplifier_workspace.install import get_install_hint as _hint
    return _hint(command)
```

If `install.py` doesn't export `get_install_hint`, add it inline:

```python
_INSTALL_HINTS: dict[str, str] = {
    "lazygit": "brew install lazygit  (macOS) or see github.com/jesseduffield/lazygit",
    "yazi": "brew install yazi  (macOS) or cargo install yazi-fm",
}

def get_install_hint(command: str) -> str:
    return _INSTALL_HINTS.get(command, f"see docs for {command}")
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_doctor.py::TestDoctorTmuxChecks -v
```

Expected: All 7 tests PASS.

### Step 5: Run full doctor test suite

```bash
pytest tests/test_doctor.py -v
```

Expected: All tests PASS.

### Step 6: Run the complete test suite

```bash
pytest -v
```

Expected: All tests PASS across all test files.

### Step 7: Commit

```bash
git add src/amplifier_workspace/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): add tmux-aware health checks (tmux binary + tool windows)"
```

---

## Phase 3 Complete — Final Verification

Run the full suite one final time:

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
pytest -v --tb=short
```

Expected output ends with:
```
======================== N passed in X.Xs ========================
```

No failures. No errors.

### What was built

| File | What changed |
|---|---|
| `src/amplifier_workspace/tmux.py` | New. Full tmux session management: `session_name_from_path`, `session_exists`, `kill_session`, `create_session`, `attach_session`, plus all rcfile helpers. |
| `tests/test_tmux.py` | New. Comprehensive mock-based test suite for all tmux functions. |
| `src/amplifier_workspace/workspace.py` | `run_workspace` now handles `kill` flag, tmux-aware `destroy`, and routes through `_launch_with_tmux` when `config.tmux.enabled`. |
| `src/amplifier_workspace/cli.py` | `-k` flag forwarded to `run_workspace(kill=True)`. |
| `src/amplifier_workspace/wizard.py` | `_step4_session_manager` added; wired into `run_wizard`. `_write_config` handles tmux fields. |
| `src/amplifier_workspace/doctor.py` | Tmux block added to `run_doctor`: checks tmux binary and each configured tool window. |

### Manual smoke test (requires tmux installed)

```bash
# Verify the full UX end-to-end:
amplifier-workspace setup          # Run wizard, enable tmux at Step 4
amplifier-workspace doctor         # Should show ✓ tmux (session manager)
amplifier-workspace ~/dev/test-ws  # Should create tmux session and attach
amplifier-workspace -k ~/dev/test-ws  # Should kill the session
```
