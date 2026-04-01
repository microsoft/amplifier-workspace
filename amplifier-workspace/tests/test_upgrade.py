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
