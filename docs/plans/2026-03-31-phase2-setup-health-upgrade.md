# amplifier-workspace Phase 2: Setup, Health & Self-Update

> **For execution:** Use `/execute-plan` mode or the subagent-driven-development recipe.

**Goal:** Add the wizard (first-run interactive setup), doctor (health checks), upgrade (self-update), and full config subcommands. After Phase 2, the tool is fully usable for Tier 1 users.

**Requires:** Phase 1 complete (config system, workspace engine, git module, CLI skeleton)

**Feeds into:** Phase 3 (session manager — extends wizard and doctor with tmux support)

**Tech Stack:** Python 3.11+, stdlib only (`tomllib`, `importlib.metadata`, `urllib.request`, `tarfile`, `platform`, `shutil`, `subprocess`)

---

## Phase 1 State

When Phase 2 begins, this structure exists at `/home/bkrabach/dev/workspace-tools/amplifier-workspace/`:

```
amplifier-workspace/
├── pyproject.toml
├── src/amplifier_workspace/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py               # parses path + -k/-d/-f flags, routes to workspace.run_workspace
│   ├── workspace.py         # run_workspace(path, force=False, kill=False, destroy=False)
│   ├── git.py               # git_init, add_submodule, update_submodules
│   ├── config.py            # DEFAULT_REPOS, DEFAULT_BUNDLE, WorkspaceConfig dataclass
│   ├── config_manager.py    # CONFIG_PATH, load_config, write_config, config_get/set/add/remove/reset
│   └── templates/
│       ├── AGENTS.md
│       └── default-config.toml
└── tests/
    ├── test_config.py
    ├── test_config_manager.py
    ├── test_git.py
    ├── test_workspace.py
    └── test_cli.py
```

**APIs this plan uses from Phase 1:**

```python
# config.py
DEFAULT_REPOS: list[str]          # 3 github.com/microsoft/*.git URLs
DEFAULT_BUNDLE: str               # "amplifier-dev"

# config_manager.py
CONFIG_PATH: Path                 # ~/.config/amplifier-workspace/config.toml
def load_config() -> dict         # reads TOML → dict; returns {} if file missing
def write_config(data: dict) -> None   # atomic write (temp file + rename)
def config_get(key: str) -> Any        # dot-notation, e.g. "workspace.bundle"
def config_set(key: str, value: Any) -> None
def config_add(key: str, value: str) -> None   # appends to a list value
def config_remove(key: str, value: str) -> None
def config_reset() -> None             # resets to defaults
```

---

## Working Directories

All **pytest commands** run from:
```
amplifier-workspace/
```

All **git commands** run from:
```
/home/bkrabach/dev/workspace-tools/
```

---

## Task 0: Baseline Verification

**No new code.** Confirm Phase 1 is healthy before adding any Phase 2 code.

**Step 1: Run all Phase 1 tests**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/ -v
```
Expected: All tests pass with no failures.

**Step 2: Confirm the package installs clean**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
pip install -e . --quiet
amplifier-workspace --help
```
Expected: Help text prints, no `ImportError`.

**Step 3: Create empty Phase 2 test files**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
touch tests/test_install.py tests/test_wizard.py tests/test_doctor.py tests/test_upgrade.py
```

**Step 4: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/tests/
git commit -m "chore: add empty Phase 2 test files"
```

---

## Task 1: `install.py` — KNOWN_TOOLS registry, platform detection, install hints

**Files:**
- Create: `src/amplifier_workspace/install.py`
- Test: `tests/test_install.py`

**Step 1: Write the failing tests**

Replace `tests/test_install.py` with:

```python
"""Tests for install.py — KNOWN_TOOLS registry and platform detection."""
import shutil
from unittest.mock import patch


def test_known_tools_has_required_entries():
    from amplifier_workspace.install import KNOWN_TOOLS
    assert "tmux" in KNOWN_TOOLS
    assert "lazygit" in KNOWN_TOOLS
    assert "yazi" in KNOWN_TOOLS


def test_known_tools_tmux_has_all_package_managers():
    from amplifier_workspace.install import KNOWN_TOOLS
    tmux = KNOWN_TOOLS["tmux"]
    assert tmux["brew"] == "tmux"
    assert tmux["apt"] == "tmux"
    assert tmux["dnf"] == "tmux"
    assert tmux["winget"] == "tmux"


def test_known_tools_lazygit_has_github_fallback():
    from amplifier_workspace.install import KNOWN_TOOLS
    lazygit = KNOWN_TOOLS["lazygit"]
    assert "github" in lazygit
    assert "jesseduffield/lazygit" in lazygit["github"]


def test_detect_package_manager_macos_brew():
    with patch("platform.system", return_value="Darwin"), \
         patch("shutil.which", return_value="/usr/local/bin/brew"):
        from amplifier_workspace.install import detect_package_manager
        assert detect_package_manager() == "brew"


def test_detect_package_manager_macos_no_brew():
    with patch("platform.system", return_value="Darwin"), \
         patch("shutil.which", return_value=None):
        from amplifier_workspace.install import detect_package_manager
        assert detect_package_manager() is None


def test_detect_package_manager_linux_apt_first():
    call_log: list[str] = []

    def mock_which(name: str) -> str | None:
        call_log.append(name)
        return "/usr/bin/apt" if name == "apt" else None

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", side_effect=mock_which):
        from amplifier_workspace.install import detect_package_manager
        result = detect_package_manager()

    assert result == "apt"


def test_detect_package_manager_linux_dnf_fallback():
    def mock_which(name: str) -> str | None:
        return "/usr/bin/dnf" if name == "dnf" else None

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", side_effect=mock_which):
        from amplifier_workspace.install import detect_package_manager
        result = detect_package_manager()

    assert result == "dnf"


def test_detect_package_manager_windows_winget():
    with patch("platform.system", return_value="Windows"), \
         patch("shutil.which", return_value="C:\\Windows\\winget.exe"):
        from amplifier_workspace.install import detect_package_manager
        assert detect_package_manager() == "winget"


def test_detect_package_manager_unknown_platform():
    with patch("platform.system", return_value="FreeBSD"), \
         patch("shutil.which", return_value=None):
        from amplifier_workspace.install import detect_package_manager
        assert detect_package_manager() is None


def test_get_install_hint_tmux_on_brew():
    with patch("amplifier_workspace.install.detect_package_manager", return_value="brew"):
        from amplifier_workspace.install import get_install_hint
        hint = get_install_hint("tmux")
    assert hint is not None
    assert "brew install tmux" in hint


def test_get_install_hint_tmux_on_apt():
    with patch("amplifier_workspace.install.detect_package_manager", return_value="apt"):
        from amplifier_workspace.install import get_install_hint
        hint = get_install_hint("tmux")
    assert hint is not None
    assert "tmux" in hint


def test_get_install_hint_unknown_tool_returns_none():
    with patch("amplifier_workspace.install.detect_package_manager", return_value="brew"):
        from amplifier_workspace.install import get_install_hint
        assert get_install_hint("unknown-tool-xyz-999") is None


def test_get_install_hint_no_package_manager_returns_none():
    with patch("amplifier_workspace.install.detect_package_manager", return_value=None):
        from amplifier_workspace.install import get_install_hint
        assert get_install_hint("tmux") is None
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_install.py -v
```
Expected: `ModuleNotFoundError` — `install.py` doesn't exist yet.

**Step 3: Create `src/amplifier_workspace/install.py`**

```python
"""Cross-platform tool installation and KNOWN_TOOLS registry."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

KNOWN_TOOLS: dict[str, dict[str, str]] = {
    "tmux": {
        "brew": "tmux",
        "apt": "tmux",
        "dnf": "tmux",
        "winget": "tmux",
    },
    "lazygit": {
        "brew": "lazygit",
        "winget": "JesseDuffield.lazygit",
        "github": "jesseduffield/lazygit",  # GitHub releases fallback for Linux
    },
    "yazi": {
        "brew": "yazi",
        "winget": "sxyazi.yazi",
        "manual": "cargo install yazi-fm yazi-cli  # or: https://github.com/sxyazi/yazi/releases",
    },
}

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def detect_package_manager() -> str | None:
    """Return the active package manager name, or None if none detected.

    Priority:
      macOS   → brew
      Linux   → apt first, then dnf
      Windows → winget
    """
    system = platform.system()
    if system == "Darwin":
        return "brew" if shutil.which("brew") else None
    elif system == "Linux":
        if shutil.which("apt"):
            return "apt"
        if shutil.which("dnf"):
            return "dnf"
        return None
    elif system == "Windows":
        return "winget" if shutil.which("winget") else None
    return None


def _has_sudo() -> bool:
    """Return True if sudo is available in PATH."""
    return shutil.which("sudo") is not None


def _get_arch() -> str:
    """Return the system architecture string for GitHub release downloads."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return machine


# ---------------------------------------------------------------------------
# Install hints
# ---------------------------------------------------------------------------


def get_install_hint(command: str) -> str | None:
    """Return a human-readable install hint for *command* on the current platform.

    Returns None if the command is not in KNOWN_TOOLS or no package manager
    is detected.
    """
    if command not in KNOWN_TOOLS:
        return None
    pkg_mgr = detect_package_manager()
    if pkg_mgr is None:
        return None
    tool = KNOWN_TOOLS[command]
    package = tool.get(pkg_mgr)
    if package is None:
        # Fall back to manual hint if present
        return tool.get("manual")
    if pkg_mgr == "brew":
        return f"brew install {package}"
    if pkg_mgr == "apt":
        return f"sudo apt install {package}"
    if pkg_mgr == "dnf":
        return f"sudo dnf install {package}"
    if pkg_mgr == "winget":
        return f"winget install {package}"
    return None
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_install.py -v
```
Expected: All 13 tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(install): KNOWN_TOOLS registry, detect_package_manager, get_install_hint"
```

---

## Task 2: `install.py` — `install_tool()` (package manager path + special cases)

**Files:**
- Modify: `src/amplifier_workspace/install.py`
- Test: `tests/test_install.py`

**Step 1: Write the failing tests**

Append to `tests/test_install.py`:

```python
# ---- install_tool tests ----

from unittest.mock import MagicMock


def test_install_tool_uses_brew_on_macos():
    from amplifier_workspace.install import install_tool

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("amplifier_workspace.install.detect_package_manager", return_value="brew"), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        success, msg = install_tool("tmux")

    assert success
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "brew"
    assert "tmux" in call_args


def test_install_tool_apt_uses_sudo_when_available():
    from amplifier_workspace.install import install_tool

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("amplifier_workspace.install.detect_package_manager", return_value="apt"), \
         patch("amplifier_workspace.install._has_sudo", return_value=True), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        success, msg = install_tool("tmux")

    assert success
    call_args = mock_run.call_args[0][0]
    assert "sudo" in call_args
    assert "apt" in call_args


def test_install_tool_apt_fails_without_sudo():
    from amplifier_workspace.install import install_tool

    with patch("amplifier_workspace.install.detect_package_manager", return_value="apt"), \
         patch("amplifier_workspace.install._has_sudo", return_value=False):
        success, msg = install_tool("tmux")

    assert not success
    assert "sudo" in msg.lower() or "apt install" in msg


def test_install_tool_no_package_manager():
    from amplifier_workspace.install import install_tool

    with patch("amplifier_workspace.install.detect_package_manager", return_value=None):
        success, msg = install_tool("tmux")

    assert not success
    assert "package manager" in msg.lower()


def test_install_tool_subprocess_failure():
    from amplifier_workspace.install import install_tool

    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch("amplifier_workspace.install.detect_package_manager", return_value="brew"), \
         patch("subprocess.run", return_value=mock_result):
        success, msg = install_tool("tmux")

    assert not success


def test_install_tool_yazi_linux_returns_manual_instructions():
    from amplifier_workspace.install import install_tool

    with patch("platform.system", return_value="Linux"), \
         patch("amplifier_workspace.install.detect_package_manager", return_value="apt"):
        success, msg = install_tool("yazi")

    assert not success
    assert "cargo" in msg or "manual" in msg.lower() or "yazi" in msg


def test_install_tool_lazygit_linux_routes_to_github_installer():
    """install_tool("lazygit") on Linux must delegate to _install_lazygit_linux."""
    from amplifier_workspace.install import install_tool

    called: list[bool] = []

    def fake_lazygit_linux() -> tuple[bool, str]:
        called.append(True)
        return True, "installed"

    with patch("platform.system", return_value="Linux"), \
         patch("amplifier_workspace.install._install_lazygit_linux",
               side_effect=fake_lazygit_linux):
        success, msg = install_tool("lazygit")

    assert called, "_install_lazygit_linux was not called"
    assert success
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_install.py::test_install_tool_uses_brew_on_macos -v
```
Expected: FAIL — `install_tool` not defined yet.

**Step 3: Append `install_tool()` to `src/amplifier_workspace/install.py`**

Add after `get_install_hint`:

```python
# ---------------------------------------------------------------------------
# Tool installation
# ---------------------------------------------------------------------------


def install_tool(name: str) -> tuple[bool, str]:
    """Attempt to install *name* using the platform package manager.

    Returns (success, message).

    Special cases:
      - lazygit on Linux: GitHub releases (no reliable apt/dnf package)
      - yazi on Linux: print manual instructions only
    """
    system = platform.system()

    # Special case: lazygit on Linux → GitHub releases
    if name == "lazygit" and system == "Linux":
        return _install_lazygit_linux()

    # Special case: yazi on Linux → manual instructions only
    if name == "yazi" and system == "Linux":
        manual = KNOWN_TOOLS["yazi"].get(
            "manual",
            "Install yazi manually: https://github.com/sxyazi/yazi/releases",
        )
        return False, f"No automated install for yazi on Linux.\n  {manual}"

    pkg_mgr = detect_package_manager()
    if pkg_mgr is None:
        return False, "No supported package manager found. Install the tool manually."

    tool = KNOWN_TOOLS.get(name, {})
    package = tool.get(pkg_mgr, name)  # fall back to tool name as package name

    # Build install command
    if pkg_mgr == "brew":
        cmd = ["brew", "install", package]
    elif pkg_mgr == "apt":
        if not _has_sudo():
            return False, f"sudo not available. Run manually: apt install {package}"
        cmd = ["sudo", "apt", "install", "-y", package]
    elif pkg_mgr == "dnf":
        if not _has_sudo():
            return False, f"sudo not available. Run manually: dnf install {package}"
        cmd = ["sudo", "dnf", "install", "-y", package]
    elif pkg_mgr == "winget":
        cmd = [
            "winget", "install", "--id", package,
            "--silent", "--accept-source-agreements", "--accept-package-agreements",
        ]
    else:
        return False, f"Unsupported package manager: {pkg_mgr}"

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, f"{name} installed successfully"
    return False, f"Install failed (exit {result.returncode}). Try manually: {' '.join(cmd)}"
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_install.py -v
```
Expected: All existing + new tests pass. (The `_install_lazygit_linux` body is called by the routing test but stubbed — that test only checks the call was dispatched.)

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(install): install_tool with pkg manager routing and special cases"
```

---

## Task 3: `install.py` — `_install_lazygit_linux()` (GitHub releases)

**Files:**
- Modify: `src/amplifier_workspace/install.py`
- Test: `tests/test_install.py`

**Step 1: Write the failing tests**

Append to `tests/test_install.py`:

```python
# ---- _install_lazygit_linux tests ----

import json
import shutil as _shutil
import tarfile as _tf


def _make_fake_tarball(tmp_path) -> "Path":
    """Create a real .tar.gz containing a fake lazygit binary."""
    from pathlib import Path
    binary = tmp_path / "lazygit"
    binary.write_bytes(b"#!/bin/sh\necho lazygit")
    tarball = tmp_path / "lazygit.tar.gz"
    with _tf.open(str(tarball), "w:gz") as t:
        t.add(str(binary), arcname="lazygit")
    return tarball


def test_install_lazygit_linux_installs_to_local_bin(tmp_path):
    """Without sudo, lazygit lands in ~/.local/bin."""
    from amplifier_workspace.install import _install_lazygit_linux

    fake_tarball = _make_fake_tarball(tmp_path)
    fake_release = json.dumps({"tag_name": "v0.44.1"}).encode()

    class FakeCtx:
        def read(self):
            return fake_release
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlretrieve(url: str, path: str) -> None:
        _shutil.copy2(str(fake_tarball), path)

    home_dir = tmp_path / "home"
    home_dir.mkdir()

    with patch("urllib.request.urlopen", return_value=FakeCtx()), \
         patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve), \
         patch("amplifier_workspace.install._has_sudo", return_value=False), \
         patch("amplifier_workspace.install._get_arch", return_value="x86_64"), \
         patch("pathlib.Path.home", return_value=home_dir):
        success, msg = _install_lazygit_linux()

    assert success
    installed_bin = home_dir / ".local" / "bin" / "lazygit"
    assert installed_bin.exists()


def test_install_lazygit_linux_handles_api_error():
    """Network errors return (False, error message)."""
    from amplifier_workspace.install import _install_lazygit_linux

    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        success, msg = _install_lazygit_linux()

    assert not success
    assert "network error" in msg.lower() or "failed" in msg.lower()


def test_install_lazygit_linux_rejects_unknown_arch():
    """Unsupported architectures bail out cleanly."""
    from amplifier_workspace.install import _install_lazygit_linux

    fake_release = json.dumps({"tag_name": "v0.44.1"}).encode()

    class FakeCtx:
        def read(self):
            return fake_release
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    with patch("urllib.request.urlopen", return_value=FakeCtx()), \
         patch("amplifier_workspace.install._get_arch", return_value="mips"):
        success, msg = _install_lazygit_linux()

    assert not success
    assert "arch" in msg.lower() or "unsupported" in msg.lower()
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_install.py::test_install_lazygit_linux_installs_to_local_bin -v
```
Expected: FAIL — `_install_lazygit_linux` body is just the stub `pass` / `return True` placeholder from Task 2's routing test.

**Step 3: Insert `_install_lazygit_linux()` into `src/amplifier_workspace/install.py`**

Add this function **before** `install_tool` (after `get_install_hint`):

```python
def _install_lazygit_linux() -> tuple[bool, str]:
    """Install lazygit on Linux via GitHub releases API.

    Falls back to ~/.local/bin when sudo is unavailable.
    Returns (success, message).
    """
    arch = _get_arch()
    if arch not in ("x86_64", "arm64"):
        return False, f"Unsupported architecture for automated lazygit install: {arch}"

    try:
        # Fetch latest release version
        api_url = "https://api.github.com/repos/jesseduffield/lazygit/releases/latest"
        with urllib.request.urlopen(api_url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        version = data["tag_name"].lstrip("v")

        # Build download URL
        tarball_url = (
            f"https://github.com/jesseduffield/lazygit/releases/download/"
            f"v{version}/lazygit_{version}_Linux_{arch}.tar.gz"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tarball_path = Path(tmpdir) / "lazygit.tar.gz"
            urllib.request.urlretrieve(tarball_url, str(tarball_path))

            with tarfile.open(str(tarball_path), "r:gz") as tar:
                tar.extract("lazygit", tmpdir)

            lazygit_bin = Path(tmpdir) / "lazygit"

            # Try /usr/local/bin with sudo first
            if _has_sudo():
                result = subprocess.run(
                    ["sudo", "install", str(lazygit_bin), "-D", "-t", "/usr/local/bin/"],
                    capture_output=True,
                )
                if result.returncode == 0:
                    return True, f"lazygit v{version} installed to /usr/local/bin"

            # Fallback: ~/.local/bin (no sudo needed)
            local_bin = Path.home() / ".local" / "bin"
            local_bin.mkdir(parents=True, exist_ok=True)
            dest = local_bin / "lazygit"
            shutil.copy2(str(lazygit_bin), str(dest))
            dest.chmod(0o755)
            return True, (
                f"lazygit v{version} installed to {dest} "
                f"(ensure {local_bin} is in your PATH)"
            )

    except Exception as exc:
        return False, f"Failed to install lazygit: {exc}"
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_install.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(install): _install_lazygit_linux via GitHub releases"
```

---

## Task 4: `upgrade.py` — `_get_install_info()` and `_check_for_update()`

**Files:**
- Create: `src/amplifier_workspace/upgrade.py`
- Test: `tests/test_upgrade.py`

**Step 1: Write the failing tests**

Replace `tests/test_upgrade.py` with:

```python
"""Tests for upgrade.py — PEP 610 install detection and update checking."""
from unittest.mock import MagicMock, patch


def test_get_install_info_returns_expected_keys():
    from amplifier_workspace.upgrade import _get_install_info
    info = _get_install_info()
    assert "source" in info
    assert "version" in info
    assert "commit" in info
    assert "url" in info


def test_get_install_info_detects_git_source():
    from amplifier_workspace.upgrade import _get_install_info

    fake_du = (
        '{"url": "https://github.com/microsoft/amplifier-workspace",'
        ' "vcs_info": {"vcs": "git", "commit_id": "abc1234567890"}}'
    )
    mock_dist = MagicMock()
    mock_dist.metadata = {"Version": "0.2.0"}
    mock_dist.read_text.return_value = fake_du

    with patch("importlib.metadata.distribution", return_value=mock_dist):
        info = _get_install_info()

    assert info["source"] == "git"
    assert info["commit"] == "abc1234567890"
    assert "github.com/microsoft/amplifier-workspace" in info["url"]
    assert info["version"] == "0.2.0"


def test_get_install_info_detects_editable_source():
    from amplifier_workspace.upgrade import _get_install_info

    fake_du = (
        '{"url": "file:///home/user/dev/amplifier-workspace",'
        ' "dir_info": {"editable": true}}'
    )
    mock_dist = MagicMock()
    mock_dist.metadata = {"Version": "0.0.0"}
    mock_dist.read_text.return_value = fake_du

    with patch("importlib.metadata.distribution", return_value=mock_dist):
        info = _get_install_info()

    assert info["source"] == "editable"


def test_get_install_info_returns_pypi_when_no_direct_url():
    from amplifier_workspace.upgrade import _get_install_info

    mock_dist = MagicMock()
    mock_dist.metadata = {"Version": "0.1.0"}
    mock_dist.read_text.return_value = None  # no direct_url.json

    with patch("importlib.metadata.distribution", return_value=mock_dist):
        info = _get_install_info()

    assert info["source"] == "pypi"


def test_get_install_info_returns_unknown_on_package_not_found():
    from importlib.metadata import PackageNotFoundError
    from amplifier_workspace.upgrade import _get_install_info

    with patch("importlib.metadata.distribution",
               side_effect=PackageNotFoundError("amplifier-workspace")):
        info = _get_install_info()

    assert info["source"] == "unknown"


def test_check_for_update_editable_always_false():
    from amplifier_workspace.upgrade import _check_for_update

    available, msg = _check_for_update(
        {"source": "editable", "url": None, "commit": None, "version": "0.1.0"}
    )
    assert available is False
    assert "editable" in msg.lower()


def test_check_for_update_unknown_source_always_true():
    from amplifier_workspace.upgrade import _check_for_update

    available, msg = _check_for_update(
        {"source": "unknown", "url": None, "commit": None, "version": "0.0.0"}
    )
    assert available is True


def test_check_for_update_git_up_to_date():
    from amplifier_workspace.upgrade import _check_for_update

    local_sha = "abc1234567890abcdef"
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = f"{local_sha}\tHEAD\n"

    with patch("subprocess.run", return_value=mock_result):
        available, msg = _check_for_update({
            "source": "git",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "commit": local_sha,
            "version": "0.1.0",
        })

    assert available is False
    assert "up to date" in msg.lower()


def test_check_for_update_git_update_available():
    from amplifier_workspace.upgrade import _check_for_update

    local_sha = "aaaa1111"
    remote_sha = "bbbb2222"
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = f"{remote_sha}\tHEAD\n"

    with patch("subprocess.run", return_value=mock_result):
        available, msg = _check_for_update({
            "source": "git",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "commit": local_sha,
            "version": "0.1.0",
        })

    assert available is True
    assert local_sha[:8] in msg
    assert remote_sha[:8] in msg


def test_check_for_update_git_remote_failure_assumes_update():
    from amplifier_workspace.upgrade import _check_for_update

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        available, msg = _check_for_update({
            "source": "git",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "commit": "abc123",
            "version": "0.1.0",
        })

    assert available is True
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_upgrade.py -v
```
Expected: `ModuleNotFoundError` — `upgrade.py` doesn't exist yet.

**Step 3: Create `src/amplifier_workspace/upgrade.py`**

```python
"""Self-update via PEP 610 install source detection.

Adapted from the muxplex upgrade pattern.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

_PACKAGE_NAME = "amplifier-workspace"
_GIT_URL = "https://github.com/microsoft/amplifier-workspace"

# ---------------------------------------------------------------------------
# Install source detection (PEP 610)
# ---------------------------------------------------------------------------


def _get_install_info() -> dict:
    """Detect how amplifier-workspace was installed using PEP 610 direct_url.json.

    Returns dict with keys:
      source:  'git' | 'editable' | 'pypi' | 'unknown'
      version: installed version string
      commit:  commit SHA (git installs only, else None)
      url:     VCS URL (git installs only, else None)
    """
    info: dict = {
        "source": "unknown",
        "version": "0.0.0",
        "commit": None,
        "url": None,
    }

    try:
        dist = distribution(_PACKAGE_NAME)
        info["version"] = dist.metadata["Version"]

        du_text = dist.read_text("direct_url.json")
        if du_text:
            du = json.loads(du_text)
            if "vcs_info" in du:
                info["source"] = "git"
                info["commit"] = du["vcs_info"].get("commit_id", "")
                info["url"] = du.get("url", "")
            elif "dir_info" in du and du["dir_info"].get("editable"):
                info["source"] = "editable"
            else:
                info["source"] = "unknown"
        else:
            # No direct_url.json → probably PyPI
            info["source"] = "pypi"

    except PackageNotFoundError:
        pass

    return info


# ---------------------------------------------------------------------------
# Update checking
# ---------------------------------------------------------------------------


def _check_for_update(info: dict) -> tuple[bool, str]:
    """Check if an update is available. Returns (update_available, message).

    - editable: always (False, "editable install — manage updates manually")
    - git: compare installed SHA against remote HEAD via git ls-remote
    - pypi: returns (True, note) as a safe default for now
    - unknown: always (True, "unknown install source — upgrading to be safe")
    """
    if info["source"] == "editable":
        return False, "editable install — manage updates manually"

    if info["source"] == "git":
        try:
            result = subprocess.run(
                ["git", "ls-remote", info["url"], "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return True, "could not check remote — upgrading to be safe"

            remote_sha = (
                result.stdout.strip().split()[0]
                if result.stdout.strip()
                else ""
            )
            local_sha = info["commit"] or ""

            if not remote_sha:
                return True, "could not read remote SHA — upgrading to be safe"

            if local_sha == remote_sha:
                return False, f"up to date (commit {local_sha[:8]})"
            return True, f"update available ({local_sha[:8]} → {remote_sha[:8]})"

        except Exception:
            return True, "check failed — upgrading to be safe"

    if info["source"] == "pypi":
        # Future: fetch from PyPI JSON API
        return True, "PyPI version check not yet implemented — upgrading to be safe"

    # Unknown source
    return True, "unknown install source — upgrading to be safe"
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_upgrade.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(upgrade): _get_install_info and _check_for_update via PEP 610"
```

---

## Task 5: `upgrade.py` — `run_upgrade()` (force/check-only flags + post-upgrade doctor)

**Files:**
- Modify: `src/amplifier_workspace/upgrade.py`
- Test: `tests/test_upgrade.py`

**Step 1: Write the failing tests**

Append to `tests/test_upgrade.py`:

```python
# ---- run_upgrade tests ----


def _make_git_info(sha: str = "abc1234") -> dict:
    return {
        "source": "git",
        "url": "https://github.com/microsoft/amplifier-workspace",
        "commit": sha,
        "version": "0.1.0",
    }


def test_run_upgrade_check_only_prints_status_no_install(capsys):
    from amplifier_workspace.upgrade import run_upgrade

    install_called: list[bool] = []

    with patch("amplifier_workspace.upgrade._get_install_info", return_value=_make_git_info()), \
         patch("amplifier_workspace.upgrade._check_for_update",
               return_value=(False, "up to date (abc1234)")), \
         patch("amplifier_workspace.upgrade._do_upgrade",
               side_effect=lambda info: install_called.append(True)):
        run_upgrade(check_only=True)

    out = capsys.readouterr().out
    assert "up to date" in out
    assert not install_called


def test_run_upgrade_skips_install_when_already_up_to_date(capsys):
    from amplifier_workspace.upgrade import run_upgrade

    install_called: list[bool] = []

    with patch("amplifier_workspace.upgrade._get_install_info", return_value=_make_git_info()), \
         patch("amplifier_workspace.upgrade._check_for_update",
               return_value=(False, "up to date")), \
         patch("amplifier_workspace.upgrade._do_upgrade",
               side_effect=lambda info: install_called.append(True)):
        run_upgrade()

    assert not install_called


def test_run_upgrade_installs_when_update_available():
    from amplifier_workspace.upgrade import run_upgrade

    install_called: list[bool] = []

    with patch("amplifier_workspace.upgrade._get_install_info", return_value=_make_git_info()), \
         patch("amplifier_workspace.upgrade._check_for_update",
               return_value=(True, "update available")), \
         patch("amplifier_workspace.upgrade._do_upgrade",
               side_effect=lambda info: install_called.append(True) or True), \
         patch("amplifier_workspace.upgrade._run_doctor_after_upgrade"):
        run_upgrade()

    assert install_called


def test_run_upgrade_force_skips_version_check():
    from amplifier_workspace.upgrade import run_upgrade

    install_called: list[bool] = []

    with patch("amplifier_workspace.upgrade._get_install_info", return_value=_make_git_info()), \
         patch("amplifier_workspace.upgrade._check_for_update",
               return_value=(False, "up to date")) as mock_check, \
         patch("amplifier_workspace.upgrade._do_upgrade",
               side_effect=lambda info: install_called.append(True) or True), \
         patch("amplifier_workspace.upgrade._run_doctor_after_upgrade"):
        run_upgrade(force=True)

    assert install_called
    mock_check.assert_not_called()


def test_do_upgrade_tries_uv_first():
    from amplifier_workspace.upgrade import _do_upgrade

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("shutil.which", return_value="/usr/local/bin/uv"), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        result = _do_upgrade(_make_git_info())

    assert result is True
    call_args = mock_run.call_args[0][0]
    assert "uv" in call_args[0]
    assert "--force" in call_args


def test_do_upgrade_falls_back_to_pip_when_no_uv():
    from amplifier_workspace.upgrade import _do_upgrade

    mock_result = MagicMock()
    mock_result.returncode = 0

    def mock_which(name: str) -> str | None:
        if name == "uv":
            return None
        if name in ("pip", "pip3"):
            return f"/usr/bin/{name}"
        return None

    with patch("shutil.which", side_effect=mock_which), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        result = _do_upgrade(_make_git_info())

    assert result is True
    call_args = mock_run.call_args[0][0]
    assert "pip" in call_args[0]


def test_do_upgrade_returns_false_when_no_installer():
    from amplifier_workspace.upgrade import _do_upgrade

    with patch("shutil.which", return_value=None):
        result = _do_upgrade(_make_git_info())

    assert result is False
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_upgrade.py::test_run_upgrade_check_only_prints_status_no_install -v
```
Expected: FAIL — `run_upgrade` not defined yet.

**Step 3: Append `_do_upgrade()`, `_run_doctor_after_upgrade()`, and `run_upgrade()` to `src/amplifier_workspace/upgrade.py`**

```python
# ---------------------------------------------------------------------------
# Upgrade execution
# ---------------------------------------------------------------------------


def _do_upgrade(info: dict) -> bool:
    """Reinstall the tool. Returns True on success, False on failure.

    Tries uv first (preferred), falls back to pip.
    """
    url = info.get("url") or _GIT_URL
    uv = shutil.which("uv")
    if uv:
        result = subprocess.run(
            [uv, "tool", "install", "--force", f"git+{url}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Installed successfully (via uv)")
            return True
        print(f"  uv install failed:\n{result.stderr}")
        return False

    pip = shutil.which("pip") or shutil.which("pip3")
    if pip:
        result = subprocess.run(
            [pip, "install", "--upgrade", f"git+{url}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Installed successfully (via pip)")
            return True
        print(f"  pip install failed:\n{result.stderr}")
        return False

    print("  ERROR: neither uv nor pip found — cannot upgrade")
    return False


def _run_doctor_after_upgrade() -> None:
    """Run doctor to verify the new install. Imported lazily to avoid cycles."""
    from amplifier_workspace.doctor import run_doctor  # noqa: PLC0415
    print("\n  Verifying new install...")
    run_doctor()


def run_upgrade(*, force: bool = False, check_only: bool = False) -> None:
    """Check for updates and optionally install.

    Args:
        force:      Skip version check; reinstall unconditionally.
        check_only: Only print update status; do not install.
    """
    print("\namplifier-workspace upgrade\n")

    info = _get_install_info()
    commit_suffix = f" (commit {info['commit'][:8]})" if info["commit"] else ""
    print(f"  Installed: v{info['version']}{commit_suffix} via {info['source']}")

    if check_only:
        _, message = _check_for_update(info)
        print(f"  Status: {message}")
        return

    if not force:
        update_available, message = _check_for_update(info)
        print(f"  Status: {message}")
        if not update_available:
            print("\n  Already up to date. Use --force to reinstall anyway.\n")
            return
    else:
        print("  Status: --force specified — skipping version check")

    print("  Installing latest version...")
    success = _do_upgrade(info)

    if success:
        _run_doctor_after_upgrade()
    else:
        print("\n  Upgrade failed. See errors above.\n")
        sys.exit(1)
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_upgrade.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(upgrade): run_upgrade with force/check-only flags and post-upgrade doctor"
```

---

## Task 6: `doctor.py` — `_print_check()` + always-run checks

**Files:**
- Create: `src/amplifier_workspace/doctor.py`
- Test: `tests/test_doctor.py`

**Step 1: Write the failing tests**

Replace `tests/test_doctor.py` with:

```python
"""Tests for doctor.py — health check output and logic."""
import sys
from unittest.mock import MagicMock, patch


def test_print_check_pass_contains_check_mark(capsys):
    from amplifier_workspace.doctor import _print_check
    _print_check("git", passed=True, detail="2.43.0")
    out = capsys.readouterr().out
    assert "✓" in out or "\033[32m" in out
    assert "git" in out
    assert "2.43.0" in out


def test_print_check_fail_contains_x_mark(capsys):
    from amplifier_workspace.doctor import _print_check
    _print_check("git", passed=False, detail="not found")
    out = capsys.readouterr().out
    assert "✗" in out or "\033[31m" in out
    assert "git" in out


def test_print_check_none_shows_skipped(capsys):
    from amplifier_workspace.doctor import _print_check
    _print_check("tmux", passed=None)
    out = capsys.readouterr().out
    assert "tmux" in out
    assert "skip" in out.lower() or "-" in out


def _patch_doctor_deps(config: dict, config_exists: bool = True):
    """Return a stack of patches for run_doctor tests."""
    return [
        patch("amplifier_workspace.doctor._get_install_info_for_doctor",
              return_value={"source": "git", "version": "0.1.0",
                            "commit": "abc12345", "url": "..."}),
        patch("amplifier_workspace.doctor._check_for_update_doctor",
              return_value=(False, "up to date")),
        patch("amplifier_workspace.config_manager.load_config", return_value=config),
        patch("amplifier_workspace.config_manager.CONFIG_PATH",
              **{"exists.return_value": config_exists,
                 "__str__": lambda s: "~/.config/amplifier-workspace/config.toml"}),
    ]


def test_run_doctor_prints_python_version(capsys):
    from amplifier_workspace.doctor import run_doctor
    with patch("amplifier_workspace.doctor._get_install_info_for_doctor",
               return_value={"source": "git", "version": "0.1.0",
                             "commit": "abc12345", "url": "..."}), \
         patch("amplifier_workspace.doctor._check_for_update_doctor",
               return_value=(False, "up to date")), \
         patch("shutil.which", return_value="/usr/bin/something"), \
         patch("amplifier_workspace.config_manager.load_config", return_value={}), \
         patch("amplifier_workspace.config_manager.CONFIG_PATH") as mock_cp:
        mock_cp.exists.return_value = True
        run_doctor()
    out = capsys.readouterr().out
    assert "Python" in out
    assert str(sys.version_info.major) in out


def test_run_doctor_passes_when_git_found(capsys):
    from amplifier_workspace.doctor import run_doctor
    with patch("amplifier_workspace.doctor._get_install_info_for_doctor",
               return_value={"source": "unknown", "version": "0.0.0",
                             "commit": None, "url": None}), \
         patch("amplifier_workspace.doctor._check_for_update_doctor",
               return_value=(False, "unknown")), \
         patch("shutil.which", return_value="/usr/bin/git"), \
         patch("amplifier_workspace.config_manager.load_config", return_value={}), \
         patch("amplifier_workspace.config_manager.CONFIG_PATH") as mock_cp:
        mock_cp.exists.return_value = False
        run_doctor()
    out = capsys.readouterr().out
    assert "git" in out.lower()


def test_run_doctor_fails_when_git_missing(capsys):
    from amplifier_workspace.doctor import run_doctor

    def mock_which(name: str) -> str | None:
        return None if name == "git" else f"/usr/bin/{name}"

    with patch("amplifier_workspace.doctor._get_install_info_for_doctor",
               return_value={"source": "unknown", "version": "0.0.0",
                             "commit": None, "url": None}), \
         patch("amplifier_workspace.doctor._check_for_update_doctor",
               return_value=(False, "unknown")), \
         patch("shutil.which", side_effect=mock_which), \
         patch("amplifier_workspace.config_manager.load_config", return_value={}), \
         patch("amplifier_workspace.config_manager.CONFIG_PATH") as mock_cp:
        mock_cp.exists.return_value = False
        exit_code = run_doctor()

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "git" in out.lower()


def test_run_doctor_returns_0_when_all_pass(capsys):
    from amplifier_workspace.doctor import run_doctor

    config = {
        "workspace": {
            "default_repos": ["https://example.com/repo.git"],
            "bundle": "amplifier-dev",
            "agents_template": "",
        },
        "tmux": {"enabled": False},
    }

    with patch("amplifier_workspace.doctor._get_install_info_for_doctor",
               return_value={"source": "git", "version": "0.1.0",
                             "commit": "abc12345", "url": "..."}), \
         patch("amplifier_workspace.doctor._check_for_update_doctor",
               return_value=(False, "up to date")), \
         patch("shutil.which", return_value="/usr/bin/something"), \
         patch("amplifier_workspace.config_manager.load_config", return_value=config), \
         patch("amplifier_workspace.config_manager.CONFIG_PATH") as mock_cp:
        mock_cp.exists.return_value = True
        exit_code = run_doctor()

    assert exit_code == 0
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_doctor.py -v
```
Expected: `ModuleNotFoundError` — `doctor.py` doesn't exist yet.

**Step 3: Create `src/amplifier_workspace/doctor.py`**

```python
"""Config-aware sequential health checks.

Exit code: 0 = all pass, 1 = one or more fail.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colour constants (no external deps)
# ---------------------------------------------------------------------------

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

_CHECK = f"{GREEN}✓{RESET}"
_FAIL = f"{RED}✗{RESET}"
_WARN = f"{YELLOW}⚠{RESET}"
_SKIP = "-"


# ---------------------------------------------------------------------------
# Output helper
# ---------------------------------------------------------------------------


def _print_check(label: str, passed: bool | None, detail: str = "") -> None:
    """Print a single check line.

    passed=True  →  "  ✓  label  detail"  (green check)
    passed=False →  "  ✗  label  detail"  (red x)
    passed=None  →  "  -  label (skipped)"
    """
    suffix = f"  {detail}" if detail else ""
    if passed is True:
        print(f"  {_CHECK}  {label}{suffix}")
    elif passed is False:
        print(f"  {_FAIL}  {label}{suffix}")
    else:
        print(f"  {_SKIP}  {label} (skipped)")


# ---------------------------------------------------------------------------
# Thin wrappers so tests can patch without touching upgrade module internals
# ---------------------------------------------------------------------------


def _get_install_info_for_doctor() -> dict:
    from amplifier_workspace.upgrade import _get_install_info  # noqa: PLC0415
    return _get_install_info()


def _check_for_update_doctor(info: dict) -> tuple[bool, str]:
    from amplifier_workspace.upgrade import _check_for_update  # noqa: PLC0415
    return _check_for_update(info)


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


def run_doctor() -> int:
    """Run all health checks. Returns 0 if all pass, 1 if any fail."""
    from amplifier_workspace.config_manager import CONFIG_PATH, load_config  # noqa: PLC0415

    failures = 0
    print("\namplifier-workspace doctor\n")

    # 1. Python version
    py_version = platform.python_version()
    py_ok = tuple(int(x) for x in py_version.split(".")[:2]) >= (3, 11)
    if not py_ok:
        failures += 1
    _print_check(
        f"Python {py_version}",
        passed=py_ok,
        detail="" if py_ok else "(need ≥3.11)",
    )

    # 2. amplifier-workspace version + install source
    info = _get_install_info_for_doctor()
    source_label = info["source"]
    if info["commit"]:
        source_label += f" @ {info['commit'][:8]}"
    _print_check(
        f"amplifier-workspace {info['version']} ({source_label})",
        passed=True,
    )

    # 3. Update check
    update_available, update_msg = _check_for_update_doctor(info)
    if update_available:
        print(f"  {_WARN}  {update_msg}")
        print("       Run: amplifier-workspace upgrade")
    else:
        _print_check(update_msg, passed=True)

    # 4. git in PATH
    git_path = shutil.which("git")
    if git_path:
        try:
            result = subprocess.run(
                ["git", "--version"], capture_output=True, text=True, timeout=5
            )
            git_detail = result.stdout.strip()
        except Exception:
            git_detail = "found"
        _print_check(f"git  {git_detail}", passed=True)
    else:
        failures += 1
        _print_check("git  not found", passed=False)

    # 5. amplifier in PATH
    amp_path = shutil.which("amplifier")
    if amp_path:
        _print_check("amplifier found in PATH", passed=True)
    else:
        failures += 1
        _print_check("amplifier not found in PATH", passed=False)

    # 6. Config file
    config_exists = CONFIG_PATH.exists()
    if config_exists:
        _print_check(f"Config: {CONFIG_PATH}", passed=True)
    else:
        failures += 1
        _print_check(
            "No config file",
            passed=False,
            detail="(run: amplifier-workspace setup)",
        )

    # Load config for remaining checks (empty dict if file missing)
    config = load_config() if config_exists else {}
    workspace = config.get("workspace", {})

    # 7. default_repos count
    repos = workspace.get("default_repos", [])
    if repos:
        _print_check(f"{len(repos)} default repo(s) configured", passed=True)
    else:
        _print_check("No default repos configured", passed=None)  # warning, not failure

    # 8. agents_template (if set: file must exist)
    agents_template = workspace.get("agents_template", "")
    if agents_template:
        tmpl_path = Path(agents_template)
        if tmpl_path.exists():
            _print_check(f"agents_template: {agents_template}", passed=True)
        else:
            failures += 1
            _print_check(f"agents_template not found: {agents_template}", passed=False)
    else:
        _print_check("AGENTS.md template: built-in", passed=True)

    # Tmux-conditional checks — implemented in Task 7
    tmux_cfg = config.get("tmux", {})
    tmux_enabled = tmux_cfg.get("enabled", False)
    if not tmux_enabled:
        _print_check("tmux", passed=None)  # skipped — not enabled

    # Summary
    print()
    if failures == 0:
        print("All checks passed.\n")
    else:
        noun = "issue" if failures == 1 else "issues"
        print(f"{failures} {noun} found. Run `amplifier-workspace setup` to reconfigure.\n")

    return 0 if failures == 0 else 1
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_doctor.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(doctor): _print_check helper and always-run health checks"
```

---

## Task 7: `doctor.py` — tmux-conditional checks + full summary

**Files:**
- Modify: `src/amplifier_workspace/doctor.py`
- Test: `tests/test_doctor.py`

**Step 1: Write the failing tests**

Append to `tests/test_doctor.py`:

```python
# ---- tmux-conditional check tests ----


def _doctor_with_tmux_config(config: dict, which_fn=None, capsys=None):
    """Helper: run doctor with given config, optional shutil.which override."""
    from amplifier_workspace.doctor import run_doctor

    which_mock = which_fn or (lambda name: f"/usr/bin/{name}")

    with patch("amplifier_workspace.doctor._get_install_info_for_doctor",
               return_value={"source": "git", "version": "0.1.0",
                             "commit": "abc12345", "url": "..."}), \
         patch("amplifier_workspace.doctor._check_for_update_doctor",
               return_value=(False, "up to date")), \
         patch("shutil.which", side_effect=which_mock), \
         patch("amplifier_workspace.config_manager.load_config", return_value=config), \
         patch("amplifier_workspace.config_manager.CONFIG_PATH") as mock_cp:
        mock_cp.exists.return_value = True
        exit_code = run_doctor()

    out = capsys.readouterr().out if capsys else ""
    return exit_code, out


def test_doctor_tmux_enabled_checks_tmux_binary(capsys):
    config = {
        "workspace": {"default_repos": [], "bundle": "amplifier-dev",
                      "agents_template": ""},
        "tmux": {"enabled": True, "windows": {}},
    }
    exit_code, out = _doctor_with_tmux_config(config, capsys=capsys)
    assert "tmux" in out.lower()


def test_doctor_tmux_enabled_missing_tool_fails(capsys):
    config = {
        "workspace": {"default_repos": [], "bundle": "amplifier-dev",
                      "agents_template": ""},
        "tmux": {"enabled": True, "windows": {"git": "lazygit", "files": "yazi"}},
    }

    def mock_which(name: str) -> str | None:
        return None if name == "lazygit" else f"/usr/bin/{name}"

    exit_code, out = _doctor_with_tmux_config(config, which_fn=mock_which, capsys=capsys)
    assert "lazygit" in out
    assert exit_code == 1


def test_doctor_tmux_disabled_shows_skipped(capsys):
    config = {
        "workspace": {"default_repos": [], "bundle": "amplifier-dev",
                      "agents_template": ""},
        "tmux": {"enabled": False},
    }
    _, out = _doctor_with_tmux_config(config, capsys=capsys)
    assert "skip" in out.lower()


def test_doctor_summary_all_pass_exits_0(capsys):
    config = {
        "workspace": {"default_repos": ["https://example.com/repo.git"],
                      "bundle": "amplifier-dev", "agents_template": ""},
        "tmux": {"enabled": False},
    }
    exit_code, out = _doctor_with_tmux_config(config, capsys=capsys)
    assert "All checks passed" in out
    assert exit_code == 0


def test_doctor_summary_with_failures(capsys):
    from amplifier_workspace.doctor import run_doctor

    def mock_which(name: str) -> str | None:
        return None if name in ("git", "amplifier") else f"/usr/bin/{name}"

    config = {
        "workspace": {"default_repos": [], "bundle": "amplifier-dev",
                      "agents_template": ""},
    }

    with patch("amplifier_workspace.doctor._get_install_info_for_doctor",
               return_value={"source": "unknown", "version": "0.0.0",
                             "commit": None, "url": None}), \
         patch("amplifier_workspace.doctor._check_for_update_doctor",
               return_value=(False, "unknown")), \
         patch("shutil.which", side_effect=mock_which), \
         patch("amplifier_workspace.config_manager.load_config", return_value=config), \
         patch("amplifier_workspace.config_manager.CONFIG_PATH") as mock_cp:
        mock_cp.exists.return_value = True
        exit_code = run_doctor()

    out = capsys.readouterr().out
    assert "issue" in out.lower()
    assert exit_code == 1
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_doctor.py::test_doctor_tmux_enabled_missing_tool_fails -v
```
Expected: FAIL — the tmux-conditional block currently just prints "skipped".

**Step 3: Replace the tmux-conditional section in `src/amplifier_workspace/doctor.py`**

Find this block (near the end of `run_doctor`):
```python
    # Tmux-conditional checks — implemented in Task 7
    tmux_cfg = config.get("tmux", {})
    tmux_enabled = tmux_cfg.get("enabled", False)
    if not tmux_enabled:
        _print_check("tmux", passed=None)  # skipped — not enabled
```

Replace it with:
```python
    # Tmux-conditional checks
    tmux_cfg = config.get("tmux", {})
    tmux_enabled = tmux_cfg.get("enabled", False)

    if not tmux_enabled:
        _print_check("tmux", passed=None)  # skipped — not enabled
    else:
        # 9. tmux binary
        tmux_path = shutil.which("tmux")
        if tmux_path:
            try:
                result = subprocess.run(
                    ["tmux", "-V"], capture_output=True, text=True, timeout=5
                )
                tmux_ver = result.stdout.strip()
            except Exception:
                tmux_ver = "found"
            _print_check(f"tmux  {tmux_ver}", passed=True)
        else:
            failures += 1
            hint = ""
            try:
                from amplifier_workspace.install import get_install_hint  # noqa: PLC0415
                hint = get_install_hint("tmux") or ""
            except Exception:
                pass
            detail = f"not found{f' ({hint})' if hint else ''}"
            _print_check(f"tmux  {detail}", passed=False)

        # 10. Each tool in tmux.windows
        windows: dict[str, str] = tmux_cfg.get("windows", {})
        for window_name, command in windows.items():
            if not command:
                continue
            base_cmd = command.split()[0]
            if shutil.which(base_cmd):
                _print_check(f"{base_cmd} found", passed=True)
            else:
                failures += 1
                hint = ""
                try:
                    from amplifier_workspace.install import get_install_hint  # noqa: PLC0415
                    hint = get_install_hint(base_cmd) or ""
                except Exception:
                    pass
                detail = hint if hint else f"install {base_cmd} manually"
                _print_check(
                    f"{base_cmd} not found",
                    passed=False,
                    detail=f"({detail} — or remove '{window_name}' from [tmux.windows])",
                )
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_doctor.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(doctor): tmux-conditional checks, window tool checks, summary line"
```

---

## Task 8: `wizard.py` — `_prompt()` + steps 1 and 2 (repos, bundle)

**Files:**
- Create: `src/amplifier_workspace/wizard.py`
- Test: `tests/test_wizard.py`

**Step 1: Write the failing tests**

Replace `tests/test_wizard.py` with:

```python
"""Tests for wizard.py — interactive first-run setup."""
from unittest.mock import patch


def test_prompt_returns_user_input():
    from amplifier_workspace.wizard import _prompt
    with patch("builtins.input", return_value="my value"):
        result = _prompt("Enter something", default="default")
    assert result == "my value"


def test_prompt_returns_default_on_empty_input():
    from amplifier_workspace.wizard import _prompt
    with patch("builtins.input", return_value=""):
        result = _prompt("Enter something", default="fallback")
    assert result == "fallback"


def test_prompt_propagates_keyboard_interrupt():
    from amplifier_workspace.wizard import _prompt
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        try:
            _prompt("Question", default="x")
            assert False, "Should have raised KeyboardInterrupt"
        except KeyboardInterrupt:
            pass  # correct — caller handles it


def test_wizard_accepts_default_repos_on_y():
    from amplifier_workspace.wizard import run_wizard
    from amplifier_workspace.config import DEFAULT_REPOS

    written: list[dict] = []

    def capture_write(data: dict) -> None:
        written.append(data)

    # Y=keep repos, blank=default bundle, 1=built-in template, blank=step 4 stub
    inputs = iter(["Y", "", "1", ""])
    with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
         patch("amplifier_workspace.wizard.write_config", side_effect=capture_write), \
         patch("amplifier_workspace.wizard.CONFIG_PATH") as mock_cp:
        mock_cp.parent.mkdir = lambda **kw: None
        run_wizard()

    assert written, "write_config was never called"
    repos = written[0].get("workspace", {}).get("default_repos", [])
    assert repos == DEFAULT_REPOS


def test_wizard_accepts_custom_repos_on_n():
    from amplifier_workspace.wizard import run_wizard

    written: list[dict] = []

    def capture_write(data: dict) -> None:
        written.append(data)

    custom = "https://github.com/my-org/my-repo.git"
    # n=reject defaults, custom URL, blank=bundle, 1=built-in, blank=step 4
    inputs = iter(["n", custom, "", "1", ""])
    with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
         patch("amplifier_workspace.wizard.write_config", side_effect=capture_write), \
         patch("amplifier_workspace.wizard.CONFIG_PATH") as mock_cp:
        mock_cp.parent.mkdir = lambda **kw: None
        run_wizard()

    assert written
    repos = written[0].get("workspace", {}).get("default_repos", [])
    assert custom in repos


def test_wizard_ctrl_c_writes_nothing():
    from amplifier_workspace.wizard import run_wizard

    written: list[dict] = []

    with patch("builtins.input", side_effect=KeyboardInterrupt), \
         patch("amplifier_workspace.wizard.write_config",
               side_effect=lambda data: written.append(data)):
        run_wizard()

    assert not written, "write_config should not be called after Ctrl+C"


def test_wizard_stores_custom_bundle():
    from amplifier_workspace.wizard import run_wizard

    written: list[dict] = []

    def capture_write(data: dict) -> None:
        written.append(data)

    inputs = iter(["Y", "my-custom-bundle", "1", ""])
    with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
         patch("amplifier_workspace.wizard.write_config", side_effect=capture_write), \
         patch("amplifier_workspace.wizard.CONFIG_PATH") as mock_cp:
        mock_cp.parent.mkdir = lambda **kw: None
        run_wizard()

    assert written
    bundle = written[0].get("workspace", {}).get("bundle", "")
    assert bundle == "my-custom-bundle"
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_wizard.py -v
```
Expected: `ModuleNotFoundError` — `wizard.py` doesn't exist yet.

**Step 3: Create `src/amplifier_workspace/wizard.py`**

```python
"""Interactive first-run setup wizard.

Collects all answers, then writes config atomically at the end.
Ctrl+C at any point exits cleanly — nothing is written.
"""
from __future__ import annotations

from amplifier_workspace.config import DEFAULT_BUNDLE, DEFAULT_REPOS
from amplifier_workspace.config_manager import CONFIG_PATH, write_config


def _prompt(question: str, default: str = "") -> str:
    """Display *question* with *default* in brackets, return stripped answer.

    Empty answer returns *default*.
    Propagates KeyboardInterrupt to the caller — do NOT catch it here.
    """
    bracket = f" [{default}]" if default else ""
    answer = input(f"{question}{bracket}: ").strip()
    return answer if answer else default


def run_wizard() -> None:
    """Run the interactive setup wizard and write config atomically.

    Steps:
      1. Default repos
      2. Amplifier bundle name
      3. AGENTS.md template (built-in or custom path)   [Task 9]
      4. Session manager stub (Phase 3)                  [Task 9]

    Ctrl+C exits cleanly; nothing is written.
    """
    print("\namplifier-workspace setup\n")

    try:
        # ------------------------------------------------------------------
        # Step 1 — Default repos
        # ------------------------------------------------------------------
        print("Default repos to clone into new workspaces:")
        for i, repo in enumerate(DEFAULT_REPOS, 1):
            print(f"  {i}. {repo}")
        print()

        keep = _prompt("Keep these defaults?", default="Y")
        if keep.lower() in ("y", "yes", ""):
            chosen_repos = list(DEFAULT_REPOS)
        else:
            raw = _prompt(
                "Enter comma-separated repo URLs (or a single URL)",
                default="",
            )
            chosen_repos = [r.strip() for r in raw.split(",") if r.strip()]

        # ------------------------------------------------------------------
        # Step 2 — Amplifier bundle
        # ------------------------------------------------------------------
        print()
        bundle = _prompt("Amplifier bundle name", default=DEFAULT_BUNDLE)

        # Steps 3 + 4 added in Task 9
        agents_template = ""
        tmux_enabled = False

        # ------------------------------------------------------------------
        # Write config atomically
        # ------------------------------------------------------------------
        _write_wizard_config(chosen_repos, bundle, agents_template, tmux_enabled)

    except KeyboardInterrupt:
        print("\n\nSetup cancelled. No changes written.\n")


def _write_wizard_config(
    repos: list[str],
    bundle: str,
    agents_template: str,
    tmux_enabled: bool,
) -> None:
    """Write the wizard-collected values to the config file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "workspace": {
            "default_repos": repos,
            "bundle": bundle,
            "agents_template": agents_template,
        },
        "tmux": {
            "enabled": tmux_enabled,
        },
    }
    write_config(data)
    print(f"\nConfig written to {CONFIG_PATH}\n")
    print("Run `amplifier-workspace doctor` to verify your setup.\n")
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_wizard.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(wizard): _prompt helper, step 1 (repos), step 2 (bundle)"
```

---

## Task 9: `wizard.py` — step 3 (AGENTS.md template), step 4 stub, final wiring

**Files:**
- Modify: `src/amplifier_workspace/wizard.py`
- Test: `tests/test_wizard.py`

**Step 1: Write the failing tests**

Append to `tests/test_wizard.py`:

```python
# ---- step 3 + step 4 stub tests ----


def test_wizard_step3_choice_1_stores_empty_template():
    """Choice [1] (built-in) stores agents_template = '' in config."""
    from amplifier_workspace.wizard import run_wizard

    written: list[dict] = []

    def capture_write(data: dict) -> None:
        written.append(data)

    inputs = iter(["Y", "", "1", ""])
    with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
         patch("amplifier_workspace.wizard.write_config", side_effect=capture_write), \
         patch("amplifier_workspace.wizard.CONFIG_PATH") as mock_cp:
        mock_cp.parent.mkdir = lambda **kw: None
        run_wizard()

    assert written
    template = written[0].get("workspace", {}).get("agents_template", "UNSET")
    assert template == ""  # empty string = use built-in


def test_wizard_step3_choice_2_stores_custom_path():
    from amplifier_workspace.wizard import run_wizard

    written: list[dict] = []

    def capture_write(data: dict) -> None:
        written.append(data)

    inputs = iter(["Y", "", "2", "/home/user/my-agents.md", ""])
    with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
         patch("amplifier_workspace.wizard.write_config", side_effect=capture_write), \
         patch("amplifier_workspace.wizard.CONFIG_PATH") as mock_cp:
        mock_cp.parent.mkdir = lambda **kw: None
        run_wizard()

    assert written
    template = written[0].get("workspace", {}).get("agents_template", "")
    assert template == "/home/user/my-agents.md"


def test_wizard_step4_stub_mentions_phase3_or_tmux(capsys):
    """Step 4 stub should mention tmux or phase 3 to orient the user."""
    from amplifier_workspace.wizard import run_wizard

    written: list[dict] = []

    inputs = iter(["Y", "", "1", ""])
    with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
         patch("amplifier_workspace.wizard.write_config",
               side_effect=lambda d: written.append(d)), \
         patch("amplifier_workspace.wizard.CONFIG_PATH") as mock_cp:
        mock_cp.parent.mkdir = lambda **kw: None
        run_wizard()

    out = capsys.readouterr().out
    assert "tmux" in out.lower() or "phase" in out.lower() or "next" in out.lower()
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_wizard.py::test_wizard_step3_choice_1_stores_empty_template -v
```
Expected: FAIL — step 3 isn't implemented yet (wizard exits after step 2).

**Step 3: Replace the `run_wizard` `try` block in `src/amplifier_workspace/wizard.py`**

Replace everything inside the `try:` block (from `# Step 1` down to `_write_wizard_config(...)`) with:

```python
        # ------------------------------------------------------------------
        # Step 1 — Default repos
        # ------------------------------------------------------------------
        print("Default repos to clone into new workspaces:")
        for i, repo in enumerate(DEFAULT_REPOS, 1):
            print(f"  {i}. {repo}")
        print()

        keep = _prompt("Keep these defaults?", default="Y")
        if keep.lower() in ("y", "yes", ""):
            chosen_repos = list(DEFAULT_REPOS)
        else:
            raw = _prompt(
                "Enter comma-separated repo URLs (or a single URL)",
                default="",
            )
            chosen_repos = [r.strip() for r in raw.split(",") if r.strip()]

        # ------------------------------------------------------------------
        # Step 2 — Amplifier bundle
        # ------------------------------------------------------------------
        print()
        bundle = _prompt("Amplifier bundle name", default=DEFAULT_BUNDLE)

        # ------------------------------------------------------------------
        # Step 3 — AGENTS.md template
        # ------------------------------------------------------------------
        print()
        print("AGENTS.md template:")
        print("  [1] Built-in (default)")
        print("  [2] Custom file path")
        print()
        choice = _prompt("Choice", default="1")
        if choice.strip() == "2":
            agents_template = _prompt("Path to custom AGENTS.md template", default="")
        else:
            agents_template = ""  # empty string = use built-in

        # ------------------------------------------------------------------
        # Step 4 — Session manager (stub in Phase 2; full implementation in Phase 3)
        # ------------------------------------------------------------------
        print()
        print("tmux session manager setup is available in Phase 3.")
        print("  Run `amplifier-workspace setup` again after upgrading to configure it.")
        tmux_enabled = False

        # ------------------------------------------------------------------
        # Write config atomically
        # ------------------------------------------------------------------
        _write_wizard_config(chosen_repos, bundle, agents_template, tmux_enabled)
```

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_wizard.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(wizard): step 3 (AGENTS.md template), step 4 Phase 3 stub, full flow wired"
```

---

## Task 10: `workspace.py` — first-run wizard trigger

**Files:**
- Modify: `src/amplifier_workspace/workspace.py`
- Test: `tests/test_workspace.py`

**Step 1: Write the failing tests**

Open `tests/test_workspace.py` and **append** (do not remove any existing tests):

```python
# ---- Phase 2: first-run wizard trigger tests ----


def test_workspace_triggers_wizard_when_no_config(tmp_path):
    """run_workspace calls run_wizard when CONFIG_PATH doesn't exist."""
    from amplifier_workspace.workspace import run_workspace

    wizard_called: list[bool] = []

    def fake_wizard() -> None:
        wizard_called.append(True)

    with patch("amplifier_workspace.workspace.CONFIG_PATH") as mock_cp, \
         patch("amplifier_workspace.workspace.load_config", return_value={}), \
         patch("amplifier_workspace.workspace.run_wizard", side_effect=fake_wizard):
        mock_cp.exists.return_value = False
        try:
            run_workspace(tmp_path / "my-workspace")
        except Exception:
            pass  # downstream errors are OK; we only care the wizard fired

    assert wizard_called, "run_wizard was not called on first run"


def test_workspace_skips_wizard_when_config_exists(tmp_path):
    """run_workspace does NOT call run_wizard when CONFIG_PATH exists."""
    from amplifier_workspace.workspace import run_workspace

    wizard_called: list[bool] = []

    def fake_wizard() -> None:
        wizard_called.append(True)

    config = {
        "workspace": {
            "default_repos": [],
            "bundle": "amplifier-dev",
            "agents_template": "",
        },
        "tmux": {"enabled": False},
    }

    with patch("amplifier_workspace.workspace.CONFIG_PATH") as mock_cp, \
         patch("amplifier_workspace.workspace.load_config", return_value=config), \
         patch("amplifier_workspace.workspace.run_wizard", side_effect=fake_wizard), \
         patch("amplifier_workspace.git.git_init"), \
         patch("amplifier_workspace.git.add_submodule"), \
         patch("amplifier_workspace.git.update_submodules"):
        mock_cp.exists.return_value = True
        try:
            run_workspace(tmp_path / "my-workspace")
        except Exception:
            pass

    assert not wizard_called, "run_wizard must not be called when config exists"
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_workspace.py::test_workspace_triggers_wizard_when_no_config -v
```
Expected: FAIL — `run_workspace` doesn't check for config existence yet.

**Step 3: Add the wizard trigger to `src/amplifier_workspace/workspace.py`**

At the **very top** of the `run_workspace` function body (after the function signature and docstring, before any existing logic), insert:

```python
    # Lazy imports to avoid circular dependencies at module load time
    from amplifier_workspace.config_manager import CONFIG_PATH, load_config  # noqa: PLC0415

    # First-run detection: if no config file exists, launch the wizard first
    if not CONFIG_PATH.exists():
        from amplifier_workspace.wizard import run_wizard  # noqa: PLC0415
        run_wizard()

    # (Re-)load config — wizard may have just written it, or it may still be absent
    config = load_config()
```

> **Important:** If `workspace.py` already imports `CONFIG_PATH` or `load_config` at the module
> level, move those imports inside `run_workspace` (lazy) to avoid circular imports, and remove
> the top-level import. The wizard imports config_manager, which must not circularly import workspace.

**Step 4: Run tests to verify they pass**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_workspace.py -v
```
Expected: All tests pass, including Phase 1 workspace tests.

**Step 5: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(workspace): trigger wizard on first run when no config file exists"
```

---

## Task 11: `cli.py` — `setup`, `doctor`, `upgrade`, `config`, `list` subcommands

**Files:**
- Modify: `src/amplifier_workspace/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Open `tests/test_cli.py` and **append**:

```python
# ---- Phase 2 subcommand tests ----

import importlib
from unittest.mock import patch


def _run_main_with_argv(argv: list[str], extra_patches: dict | None = None):
    """Run cli.main() with a given sys.argv, capturing SystemExit."""
    patches = extra_patches or {}
    ctx = [patch("sys.argv", argv)]
    for target, value in patches.items():
        ctx.append(patch(target, side_effect=value if callable(value) else None,
                         return_value=None if callable(value) else value))

    import contextlib
    with contextlib.ExitStack() as stack:
        for p in ctx:
            stack.enter_context(p)
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass


def test_cli_setup_calls_run_wizard():
    called: list[bool] = []

    with patch("sys.argv", ["amplifier-workspace", "setup"]), \
         patch("amplifier_workspace.wizard.run_wizard",
               side_effect=lambda: called.append(True)):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    assert called


def test_cli_doctor_calls_run_doctor():
    called: list[bool] = []

    with patch("sys.argv", ["amplifier-workspace", "doctor"]), \
         patch("amplifier_workspace.doctor.run_doctor",
               side_effect=lambda: called.append(True) or 0):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    assert called


def test_cli_upgrade_default_flags():
    received: list[dict] = []

    def fake_upgrade(**kwargs) -> None:
        received.append(kwargs)

    with patch("sys.argv", ["amplifier-workspace", "upgrade"]), \
         patch("amplifier_workspace.upgrade.run_upgrade", side_effect=fake_upgrade):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    assert received
    assert received[0].get("force") is False
    assert received[0].get("check_only") is False


def test_cli_upgrade_force_flag():
    received: list[dict] = []

    def fake_upgrade(**kwargs) -> None:
        received.append(kwargs)

    with patch("sys.argv", ["amplifier-workspace", "upgrade", "--force"]), \
         patch("amplifier_workspace.upgrade.run_upgrade", side_effect=fake_upgrade):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    assert received
    assert received[0].get("force") is True


def test_cli_upgrade_check_flag():
    received: list[dict] = []

    def fake_upgrade(**kwargs) -> None:
        received.append(kwargs)

    with patch("sys.argv", ["amplifier-workspace", "upgrade", "--check"]), \
         patch("amplifier_workspace.upgrade.run_upgrade", side_effect=fake_upgrade):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    assert received
    assert received[0].get("check_only") is True


def test_cli_config_list_outputs_config(capsys):
    with patch("sys.argv", ["amplifier-workspace", "config", "list"]), \
         patch("amplifier_workspace.config_manager.load_config",
               return_value={"workspace": {"bundle": "amplifier-dev"}}):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    out = capsys.readouterr().out
    assert "amplifier-dev" in out or "bundle" in out


def test_cli_list_subcommand_prints_placeholder(capsys):
    with patch("sys.argv", ["amplifier-workspace", "list"]):
        from amplifier_workspace import cli
        importlib.reload(cli)
        try:
            cli.main()
        except SystemExit:
            pass

    out = capsys.readouterr().out
    assert out.strip()  # something was printed
```

**Step 2: Run tests to verify they fail**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_cli.py::test_cli_setup_calls_run_wizard -v
```
Expected: FAIL — `setup` subcommand not registered yet.

**Step 3: Add module-level helpers to `src/amplifier_workspace/cli.py`**

Add these after the existing imports, before `main()`:

```python
import json as _json


# ---------------------------------------------------------------------------
# Phase 2 subcommand handlers (all lazy-import to avoid circular deps)
# ---------------------------------------------------------------------------


def _cmd_setup() -> None:
    from amplifier_workspace.wizard import run_wizard  # noqa: PLC0415
    run_wizard()


def _cmd_doctor() -> None:
    import sys as _sys  # noqa: PLC0415
    from amplifier_workspace.doctor import run_doctor  # noqa: PLC0415
    _sys.exit(run_doctor())


def _cmd_upgrade(force: bool, check_only: bool) -> None:
    from amplifier_workspace.upgrade import run_upgrade  # noqa: PLC0415
    run_upgrade(force=force, check_only=check_only)


def _cmd_config(action: str, key: str = "", value: str = "") -> None:
    from amplifier_workspace.config_manager import (  # noqa: PLC0415
        config_add,
        config_get,
        config_remove,
        config_reset,
        config_set,
        load_config,
    )

    def _print_dict(d: dict, prefix: str = "") -> None:
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                _print_dict(v, full_key)
            else:
                print(f"{full_key} = {_json.dumps(v)}")

    if action == "list":
        _print_dict(load_config())
    elif action == "get":
        print(config_get(key))
    elif action == "set":
        config_set(key, value)
    elif action == "add":
        config_add(key, value)
    elif action == "remove":
        config_remove(key, value)
    elif action == "reset":
        confirm = input("Reset config to defaults? [y/N] ").strip().lower()
        if confirm == "y":
            config_reset()
            print("Config reset to defaults.")
    else:
        print(f"Unknown config action: {action}")


def _cmd_list() -> None:
    print("Workspace list not yet tracked (available in Phase 3).\n")
```

**Step 4: Register the new subcommands in `main()`**

Inside `main()`, find the `sub = parser.add_subparsers(...)` line. Immediately after all existing `sub.add_parser(...)` calls (but before `args = parser.parse_args()`), add:

```python
    # Phase 2 subcommands
    sub.add_parser("setup", help="Run the interactive setup wizard.")
    sub.add_parser("doctor", help="Run config-aware health checks.")

    upgrade_parser = sub.add_parser("upgrade", help="Self-update amplifier-workspace.")
    upgrade_parser.add_argument(
        "--force", action="store_true",
        help="Skip version check; reinstall unconditionally.",
    )
    upgrade_parser.add_argument(
        "--check", action="store_true", dest="check_only",
        help="Report update status only; do not install.",
    )

    config_parser = sub.add_parser("config", help="Manage configuration.")
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_sub.add_parser("list", help="Show current config.")
    _p = config_sub.add_parser("get", help="Get a config value (dot-notation key).")
    _p.add_argument("key")
    _p = config_sub.add_parser("set", help="Set a config value.")
    _p.add_argument("key")
    _p.add_argument("value")
    _p = config_sub.add_parser("add", help="Append to a list value.")
    _p.add_argument("key")
    _p.add_argument("value")
    _p = config_sub.add_parser("remove", help="Remove from a list value.")
    _p.add_argument("key")
    _p.add_argument("value")
    config_sub.add_parser("reset", help="Reset config to defaults.")

    sub.add_parser("list", help="Show all known active workspaces.")
```

Inside the dispatch block (`if/elif` chain at the bottom of `main()`), add:

```python
    elif args.command == "setup":
        _cmd_setup()
    elif args.command == "doctor":
        _cmd_doctor()
    elif args.command == "upgrade":
        _cmd_upgrade(force=args.force, check_only=args.check_only)
    elif args.command == "config":
        action = getattr(args, "config_action", None) or "list"
        key = getattr(args, "key", "")
        value = getattr(args, "value", "")
        _cmd_config(action, key, value)
    elif args.command == "list":
        _cmd_list()
```

**Step 5: Run the Phase 2 CLI tests**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_cli.py -v
```
Expected: All Phase 2 CLI tests pass.

**Step 6: Run the full test suite — no regressions**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/ -v
```
Expected: All tests pass. Zero failures.

**Step 7: Smoke-test the CLI**
```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
pip install -e . --quiet
amplifier-workspace --help
amplifier-workspace setup --help
amplifier-workspace doctor --help
amplifier-workspace upgrade --help
amplifier-workspace config --help
amplifier-workspace list
```
Expected: All help text prints cleanly. `amplifier-workspace list` prints the placeholder message.

**Step 8: Commit**
```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/
git commit -m "feat(cli): add setup, doctor, upgrade, config, list subcommands"
```

---

## Phase 2 Complete

After these 12 tasks, `amplifier-workspace` delivers:

| Subcommand | What it does |
|---|---|
| `amplifier-workspace <path>` | Triggers wizard on first run (no config file), then creates/resumes workspace |
| `amplifier-workspace setup` | Re-runs the interactive wizard |
| `amplifier-workspace doctor` | Full health check with colored pass/fail, exit code 0/1 |
| `amplifier-workspace upgrade` | PEP 610 self-update via uv (pip fallback) |
| `amplifier-workspace upgrade --force` | Reinstall unconditionally |
| `amplifier-workspace upgrade --check` | Print update status, don't install |
| `amplifier-workspace config list/get/set/add/remove/reset` | Full config CRUD |
| `amplifier-workspace list` | Placeholder — "available in Phase 3" |

**New modules introduced:**

| Module | What it does |
|---|---|
| `install.py` | `KNOWN_TOOLS` registry, `detect_package_manager()`, `get_install_hint()`, `install_tool()`, `_install_lazygit_linux()` |
| `upgrade.py` | PEP 610 install detection, `git ls-remote` update check, uv/pip reinstall |
| `doctor.py` | Sequential health checks (always-run + tmux-conditional), colored output, exit codes |
| `wizard.py` | 4-step interactive setup (step 4 stubbed for Phase 3), atomic config write |

**Feeds into Phase 3:** The wizard's step 4 stub is replaced with the full tmux wizard flow; doctor's tmux checks grow to cover active sessions; `workspace.py` adds the `tmux.run_session()` path.
