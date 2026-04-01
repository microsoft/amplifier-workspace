# upgrade.py — _get_install_info() and _check_for_update() Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

> **WARNING — Spec Review Loop Exhausted:** The automated spec review loop ran 3 iterations
> before approval was reached. The final verdict was APPROVED, but the human reviewer should
> double-check the implementation against the spec for any subtle deviations that the automated
> loop may have been oscillating on. Pay particular attention to: (1) the 11th test
> (`test_pypi_source_returns_true`) which is implied by the spec's test count but not
> explicitly listed in the spec's 10 bullet points, and (2) the two defensive code additions
> (empty-stdout guard, fallback return) that are not in the spec but are necessary safety nets.

**Goal:** Create `upgrade.py` with PEP 610-based install detection and git-based update checking, fully tested with 11 unit tests.

**Architecture:** Uses `importlib.metadata` to read `direct_url.json` (PEP 610) from the installed package metadata. Classifies installations as git, editable, pypi, or unknown. For git installs, compares local commit SHA against remote HEAD via `git ls-remote`. All external I/O (metadata reads, subprocess calls) is mocked in tests.

**Tech Stack:** Python 3.11+ stdlib only (`importlib.metadata`, `json`, `subprocess`). Tests use `unittest.mock`.

**Dependencies:** Task 0 (baseline verification) must be complete. The empty `tests/test_upgrade.py` file must already exist.

---

### Task 1: Write failing tests for _get_install_info

**Files:**
- Replace: `amplifier-workspace/tests/test_upgrade.py`

**Step 1: Replace test_upgrade.py with _get_install_info tests**

Replace the entire contents of `amplifier-workspace/tests/test_upgrade.py` with:

```python
"""Tests for upgrade.py: _get_install_info and _check_for_update via PEP 610."""

import json
from unittest.mock import MagicMock, patch

from amplifier_workspace.upgrade import _check_for_update, _get_install_info


class TestGetInstallInfo:
    def test_returns_expected_keys(self):
        """_get_install_info always returns a dict with source, version, commit, url keys."""
        mock_dist = MagicMock()
        mock_dist.metadata = {"Version": "1.0.0"}
        mock_dist.read_text.return_value = None  # No direct_url.json

        with patch(
            "amplifier_workspace.upgrade.importlib.metadata.distribution",
            return_value=mock_dist,
        ):
            result = _get_install_info()

        assert "source" in result
        assert "version" in result
        assert "commit" in result
        assert "url" in result

    def test_detects_git_source_from_vcs_info(self):
        """Detects 'git' source when direct_url.json has vcs_info."""
        direct_url = {
            "url": "https://github.com/microsoft/amplifier-workspace",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "abcdef1234567890abcdef1234567890abcdef12",
            },
        }
        mock_dist = MagicMock()
        mock_dist.metadata = {"Version": "1.2.3"}
        mock_dist.read_text.return_value = json.dumps(direct_url)

        with patch(
            "amplifier_workspace.upgrade.importlib.metadata.distribution",
            return_value=mock_dist,
        ):
            result = _get_install_info()

        assert result["source"] == "git"
        assert result["commit"] == "abcdef1234567890abcdef1234567890abcdef12"
        assert result["url"] == "https://github.com/microsoft/amplifier-workspace"
        assert result["version"] == "1.2.3"

    def test_detects_editable_source_from_dir_info(self):
        """Detects 'editable' source when direct_url.json has dir_info.editable=true."""
        direct_url = {
            "url": "file:///home/user/amplifier-workspace",
            "dir_info": {"editable": True},
        }
        mock_dist = MagicMock()
        mock_dist.metadata = {"Version": "0.1.0"}
        mock_dist.read_text.return_value = json.dumps(direct_url)

        with patch(
            "amplifier_workspace.upgrade.importlib.metadata.distribution",
            return_value=mock_dist,
        ):
            result = _get_install_info()

        assert result["source"] == "editable"

    def test_returns_pypi_when_no_direct_url(self):
        """Returns source='pypi' when distribution has no direct_url.json."""
        mock_dist = MagicMock()
        mock_dist.metadata = {"Version": "1.0.0"}
        mock_dist.read_text.return_value = None

        with patch(
            "amplifier_workspace.upgrade.importlib.metadata.distribution",
            return_value=mock_dist,
        ):
            result = _get_install_info()

        assert result["source"] == "pypi"

    def test_returns_unknown_on_package_not_found(self):
        """Returns source='unknown', version='0.0.0' when package is not installed."""
        from importlib.metadata import PackageNotFoundError

        with patch(
            "amplifier_workspace.upgrade.importlib.metadata.distribution",
            side_effect=PackageNotFoundError("amplifier-workspace"),
        ):
            result = _get_install_info()

        assert result["source"] == "unknown"
        assert result["version"] == "0.0.0"


class TestCheckForUpdate:
    def test_editable_always_returns_false(self):
        """_check_for_update always returns (False, msg) for editable installs."""
        info = {"source": "editable", "version": "0.1.0", "commit": None, "url": None}
        update_available, message = _check_for_update(info)

        assert update_available is False
        assert "editable" in message.lower() or "manually" in message.lower()

    def test_unknown_source_always_returns_true(self):
        """_check_for_update returns (True, msg) for unknown install source."""
        info = {"source": "unknown", "version": "0.0.0", "commit": None, "url": None}
        update_available, message = _check_for_update(info)

        assert update_available is True

    def test_pypi_source_returns_true(self):
        """_check_for_update returns (True, msg) for pypi installs (not yet implemented)."""
        info = {"source": "pypi", "version": "1.0.0", "commit": None, "url": None}
        update_available, message = _check_for_update(info)

        assert update_available is True

    def test_git_up_to_date_returns_false(self):
        """_check_for_update returns (False, msg) when local and remote SHA match."""
        sha = "abcdef1234567890abcdef1234567890abcdef12"
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": sha,
            "url": "https://github.com/microsoft/amplifier-workspace",
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{sha}\tHEAD\n"

        with patch(
            "amplifier_workspace.upgrade.subprocess.run", return_value=mock_result
        ):
            update_available, message = _check_for_update(info)

        assert update_available is False
        assert "up to date" in message.lower()
        assert sha[:8] in message

    def test_git_update_available_returns_true(self):
        """_check_for_update returns (True, msg) when local and remote SHA differ."""
        local_sha = "aaaaaa1234567890aaaaaa1234567890aaaaaa12"
        remote_sha = "bbbbbb1234567890bbbbbb1234567890bbbbbb12"
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": local_sha,
            "url": "https://github.com/microsoft/amplifier-workspace",
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{remote_sha}\tHEAD\n"

        with patch(
            "amplifier_workspace.upgrade.subprocess.run", return_value=mock_result
        ):
            update_available, message = _check_for_update(info)

        assert update_available is True
        assert local_sha[:8] in message
        assert remote_sha[:8] in message

    def test_git_remote_failure_assumes_update_available(self):
        """_check_for_update returns (True, msg) when git ls-remote fails."""
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": "abcdef1234567890abcdef1234567890abcdef12",
            "url": "https://github.com/microsoft/amplifier-workspace",
        }

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch(
            "amplifier_workspace.upgrade.subprocess.run", return_value=mock_result
        ):
            update_available, message = _check_for_update(info)

        assert update_available is True
        assert "could not check" in message.lower() or "remote" in message.lower()
```

**Step 2: Run tests to confirm they fail (module does not exist yet)**

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_upgrade.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'amplifier_workspace.upgrade'` or `ImportError`.

---

### Task 2: Implement _get_install_info

**Files:**
- Create: `amplifier-workspace/src/amplifier_workspace/upgrade.py`

**Step 1: Create upgrade.py with _get_install_info and a stub _check_for_update**

Create `amplifier-workspace/src/amplifier_workspace/upgrade.py` with:

```python
"""Upgrade detection for amplifier-workspace via PEP 610 direct_url.json."""

import importlib.metadata
import json
import subprocess

_PACKAGE_NAME = "amplifier-workspace"
_GIT_URL = "https://github.com/microsoft/amplifier-workspace"


def _get_install_info() -> dict:
    """Detect how amplifier-workspace was installed using PEP 610 direct_url.json.

    Returns a dict with keys:
      - source: 'git' | 'editable' | 'pypi' | 'unknown'
      - version: str
      - commit: str | None
      - url: str | None
    """
    try:
        dist = importlib.metadata.distribution(_PACKAGE_NAME)
        version = dist.metadata["Version"]

        direct_url_text = dist.read_text("direct_url.json")

        if direct_url_text is None:
            # No direct_url.json means it was installed from PyPI
            return {"source": "pypi", "version": version, "commit": None, "url": None}

        direct_url = json.loads(direct_url_text)

        if "vcs_info" in direct_url:
            # Git-based install (pip install git+...)
            vcs_info = direct_url["vcs_info"]
            return {
                "source": "git",
                "version": version,
                "commit": vcs_info.get("commit_id"),
                "url": direct_url.get("url"),
            }

        dir_info = direct_url.get("dir_info", {})
        if dir_info.get("editable"):
            # Editable install (pip install -e .)
            return {
                "source": "editable",
                "version": version,
                "commit": None,
                "url": direct_url.get("url"),
            }

        # direct_url.json exists but no vcs_info or editable dir_info
        return {"source": "pypi", "version": version, "commit": None, "url": None}

    except importlib.metadata.PackageNotFoundError:
        return {"source": "unknown", "version": "0.0.0", "commit": None, "url": None}


def _check_for_update(info: dict) -> tuple[bool, str]:
    """Check if an update is available for amplifier-workspace.

    Returns (update_available, message) tuple.

    - editable: always (False, 'editable install — manage updates manually')
    - git: compare local SHA vs remote SHA via 'git ls-remote {url} HEAD'
    - pypi: (True, 'PyPI version check not yet implemented — upgrading to be safe')
    - unknown: (True, 'unknown install source — upgrading to be safe')
    """
    source = info["source"]

    if source == "editable":
        return (False, "editable install — manage updates manually")

    if source == "unknown":
        return (True, "unknown install source — upgrading to be safe")

    if source == "pypi":
        return (True, "PyPI version check not yet implemented — upgrading to be safe")

    if source == "git":
        url = info.get("url") or _GIT_URL
        local_commit = info.get("commit") or ""

        try:
            result = subprocess.run(
                ["git", "ls-remote", url, "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return (True, "could not check remote — upgrading to be safe")

            stdout = result.stdout.strip()
            if not stdout:
                return (True, "could not check remote — upgrading to be safe")

            # Output format: "<sha>\tHEAD"
            remote_sha = stdout.split()[0]

            if local_commit == remote_sha:
                return (False, f"up to date (commit {remote_sha[:8]})")
            else:
                return (
                    True,
                    f"update available ({local_commit[:8]} → {remote_sha[:8]})",
                )

        except Exception:
            return (True, "could not check remote — upgrading to be safe")

    # Fallback for any unrecognized source
    return (True, "unknown install source — upgrading to be safe")
```

**Step 2: Run all 11 tests to verify they pass**

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/test_upgrade.py -v
```

Expected: 11 passed.

**Step 3: Run the full test suite to confirm no regressions**

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
python -m pytest tests/ -v
```

Expected: All tests pass (currently 122 total including the 11 new ones).

**Step 4: Run code quality checks**

```bash
cd /home/bkrabach/dev/workspace-tools/amplifier-workspace
ruff format --check src/amplifier_workspace/upgrade.py tests/test_upgrade.py
ruff check src/amplifier_workspace/upgrade.py tests/test_upgrade.py
pyright src/amplifier_workspace/upgrade.py tests/test_upgrade.py
```

Expected: All clean — no formatting issues, no lint errors, no type errors.

**Step 5: Commit**

```bash
cd /home/bkrabach/dev/workspace-tools
git add amplifier-workspace/src/amplifier_workspace/upgrade.py amplifier-workspace/tests/test_upgrade.py
git commit -m "feat(upgrade): _get_install_info and _check_for_update via PEP 610"
```

---

## Verification Checklist

After completing all tasks, confirm:

- [ ] `tests/test_upgrade.py` contains exactly 11 test methods (5 in `TestGetInstallInfo`, 6 in `TestCheckForUpdate`)
- [ ] `src/amplifier_workspace/upgrade.py` has `_PACKAGE_NAME = 'amplifier-workspace'` and `_GIT_URL = 'https://github.com/microsoft/amplifier-workspace'`
- [ ] `_get_install_info()` handles git, editable, pypi, and unknown (PackageNotFoundError) cases
- [ ] `_check_for_update()` handles editable (False), unknown (True), pypi (True), and git (SHA comparison with `timeout=10`) cases
- [ ] All 11 tests pass
- [ ] Full test suite passes with no regressions
- [ ] ruff format, ruff lint, and pyright all clean