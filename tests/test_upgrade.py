"""Tests for upgrade.py: _get_install_info and _check_for_update via PEP 610."""

import json
from unittest.mock import MagicMock, patch

import pytest

from amplifier_workspace.upgrade import (
    UpgradeRefused,
    _check_for_update,
    _do_upgrade,
    _get_install_info,
    _reinstall_target,
    run_upgrade,
)


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

    def test_unknown_source_is_not_checkable(self):
        """_check_for_update never fabricates a signal for an unknown source.

        (Honesty fix: previously returned True 'upgrading to be safe'.)
        """
        info = {"source": "unknown", "version": "0.0.0", "commit": None, "url": None}
        update_available, message = _check_for_update(info)

        assert update_available is False
        assert "not checkable" in message.lower()

    def test_pypi_source_is_not_checkable(self):
        """_check_for_update never fabricates a signal for a pypi install.

        (Honesty fix: previously returned True 'upgrading to be safe'.)
        """
        info = {"source": "pypi", "version": "1.0.0", "commit": None, "url": None}
        update_available, message = _check_for_update(info)

        assert update_available is False
        assert "not checkable" in message.lower()

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


_SAMPLE_INFO = {
    "source": "git",
    "version": "1.0.0",
    "commit": "abcdef1234567890abcdef1234567890abcdef12",
    "url": "https://github.com/microsoft/amplifier-workspace",
}


class TestRunUpgrade:
    def test_check_only_prints_status_and_does_not_call_do_upgrade(self, capsys):
        """run_upgrade(check_only=True) prints install status but never calls _do_upgrade."""
        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                return_value=_SAMPLE_INFO,
            ),
            patch("amplifier_workspace.upgrade._do_upgrade") as mock_do_upgrade,
        ):
            run_upgrade(check_only=True)

        mock_do_upgrade.assert_not_called()
        captured = capsys.readouterr()
        # Should have printed version/commit/source info
        assert "1.0.0" in captured.out
        assert "git" in captured.out

    def test_skips_install_when_already_up_to_date(self, capsys):
        """run_upgrade skips _do_upgrade when _check_for_update returns False."""
        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                return_value=_SAMPLE_INFO,
            ),
            patch(
                "amplifier_workspace.upgrade._check_for_update",
                return_value=(False, "up to date (commit abcdef12)"),
            ),
            patch("amplifier_workspace.upgrade._do_upgrade") as mock_do_upgrade,
        ):
            run_upgrade()

        mock_do_upgrade.assert_not_called()
        captured = capsys.readouterr()
        assert "up to date" in captured.out.lower() or "already" in captured.out.lower()

    def test_installs_when_update_available(self):
        """run_upgrade calls _do_upgrade and _run_doctor_after_upgrade when update available."""
        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                return_value=_SAMPLE_INFO,
            ),
            patch(
                "amplifier_workspace.upgrade._check_for_update",
                return_value=(True, "update available (abcd1234 → efgh5678)"),
            ),
            patch(
                "amplifier_workspace.upgrade._do_upgrade", return_value=True
            ) as mock_do_upgrade,
            patch(
                "amplifier_workspace.upgrade._run_doctor_after_upgrade"
            ) as mock_doctor,
        ):
            run_upgrade()

        mock_do_upgrade.assert_called_once_with(_SAMPLE_INFO)
        mock_doctor.assert_called_once()

    def test_force_skips_version_check(self):
        """run_upgrade(force=True) skips _check_for_update and calls _run_doctor_after_upgrade."""
        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                return_value=_SAMPLE_INFO,
            ),
            patch("amplifier_workspace.upgrade._check_for_update") as mock_check,
            patch("amplifier_workspace.upgrade._do_upgrade", return_value=True),
            patch(
                "amplifier_workspace.upgrade._run_doctor_after_upgrade"
            ) as mock_doctor,
        ):
            run_upgrade(force=True)

        mock_check.assert_not_called()
        mock_doctor.assert_called_once()

    def test_exits_with_error_when_upgrade_fails(self):
        """run_upgrade calls sys.exit(1) when _do_upgrade returns False."""
        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                return_value=_SAMPLE_INFO,
            ),
            patch(
                "amplifier_workspace.upgrade._check_for_update",
                return_value=(True, "update available (abcd1234 → efgh5678)"),
            ),
            patch("amplifier_workspace.upgrade._do_upgrade", return_value=False),
            patch(
                "amplifier_workspace.upgrade._run_doctor_after_upgrade"
            ) as mock_doctor,
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_upgrade()

        assert exc_info.value.code == 1
        mock_doctor.assert_not_called()


class TestDoUpgrade:
    def test_tries_uv_first(self):
        """_do_upgrade uses uv when available, passing --force flag."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch(
                "amplifier_workspace.upgrade.shutil.which",
                side_effect=lambda cmd: "/usr/bin/uv" if cmd == "uv" else None,
            ),
            patch(
                "amplifier_workspace.upgrade.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
        ):
            result = _do_upgrade(_SAMPLE_INFO)

        assert result is True
        args = mock_run.call_args[0][0]
        assert "uv" in args[0]
        assert "--force" in args

    def test_falls_back_to_pip_when_no_uv(self):
        """_do_upgrade falls back to pip when uv is not found."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch(
                "amplifier_workspace.upgrade.shutil.which",
                side_effect=lambda cmd: "/usr/bin/pip" if cmd == "pip" else None,
            ),
            patch(
                "amplifier_workspace.upgrade.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
        ):
            result = _do_upgrade(_SAMPLE_INFO)

        assert result is True
        args = mock_run.call_args[0][0]
        assert "pip" in args[0]

    def test_returns_false_when_neither_uv_nor_pip_found(self, capsys):
        """_do_upgrade returns False and prints ERROR when no installer is available."""
        with patch(
            "amplifier_workspace.upgrade.shutil.which",
            return_value=None,
        ):
            result = _do_upgrade(_SAMPLE_INFO)

        assert result is False
        captured = capsys.readouterr()
        assert "error" in captured.out.lower() or "error" in captured.err.lower()


# ---------------------------------------------------------------------------
# Batch B.3 / Batch C — provenance-strict reinstall target + honesty
# ---------------------------------------------------------------------------


class TestGetInstallInfoRef:
    def test_captures_requested_revision_as_ref(self):
        """_get_install_info records the tracked branch/tag (requested_revision)."""
        direct_url = {
            "url": "https://github.com/microsoft/amplifier-workspace",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "abcdef1234567890abcdef1234567890abcdef12",
                "requested_revision": "feat/workspace-manifest",
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

        assert result["ref"] == "feat/workspace-manifest"

    def test_ref_is_none_when_not_recorded(self):
        """ref is None for a git install that tracks the default branch."""
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

        assert result["ref"] is None


class TestReinstallTarget:
    def test_git_with_ref(self):
        """git provenance with a tracked ref -> git+URL@ref."""
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": "abc",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "ref": "main",
        }
        assert (
            _reinstall_target(info)
            == "git+https://github.com/microsoft/amplifier-workspace@main"
        )

    def test_git_without_ref(self):
        """git provenance with no ref -> plain git+URL."""
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": "abc",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "ref": None,
        }
        assert (
            _reinstall_target(info)
            == "git+https://github.com/microsoft/amplifier-workspace"
        )

    def test_git_without_url_refuses(self):
        """git provenance missing a URL refuses rather than guessing."""
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": "abc",
            "url": None,
            "ref": None,
        }
        with pytest.raises(UpgradeRefused):
            _reinstall_target(info)

    def test_editable_refuses_with_local_dev_commands(self):
        """editable provenance refuses and names the local-dev reinstall commands."""
        info = {"source": "editable", "version": "0.1.0", "commit": None, "url": None}
        with pytest.raises(UpgradeRefused) as exc_info:
            _reinstall_target(info)
        msg = str(exc_info.value)
        assert "--from" in msg or "uv tool install -e" in msg

    def test_pypi_refuses(self):
        """pypi provenance refuses (never reinstalls a PyPI install from git)."""
        info = {"source": "pypi", "version": "1.0.0", "commit": None, "url": None}
        with pytest.raises(UpgradeRefused):
            _reinstall_target(info)

    def test_unknown_refuses(self):
        """unknown provenance refuses with a remedy."""
        info = {"source": "unknown", "version": "0.0.0", "commit": None, "url": None}
        with pytest.raises(UpgradeRefused):
            _reinstall_target(info)


_EDITABLE_INFO = {
    "source": "editable",
    "version": "0.1.0",
    "commit": None,
    "url": "file:///home/user/amplifier-workspace",
    "ref": None,
}
_PYPI_INFO = {
    "source": "pypi",
    "version": "1.0.0",
    "commit": None,
    "url": None,
    "ref": None,
}
_UNKNOWN_INFO = {
    "source": "unknown",
    "version": "0.0.0",
    "commit": None,
    "url": None,
    "ref": None,
}


class TestRunUpgradeRefusals:
    @pytest.mark.parametrize("info", [_EDITABLE_INFO, _PYPI_INFO, _UNKNOWN_INFO])
    def test_refuses_non_git_provenance_before_installing(self, info, capsys):
        """run_upgrade refuses editable/pypi/unknown with exit 2 and never installs."""
        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                return_value=info,
            ),
            patch("amplifier_workspace.upgrade._do_upgrade") as mock_do_upgrade,
            patch(
                "amplifier_workspace.upgrade._run_doctor_after_upgrade"
            ) as mock_doctor,
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_upgrade()

        assert exc_info.value.code == 2
        mock_do_upgrade.assert_not_called()
        mock_doctor.assert_not_called()

    def test_editable_refusal_prints_local_dev_commands(self, capsys):
        """The editable refusal surfaces the exact local-dev reinstall commands."""
        with patch(
            "amplifier_workspace.upgrade._get_install_info",
            return_value=_EDITABLE_INFO,
        ):
            with pytest.raises(SystemExit):
                run_upgrade()

        out = capsys.readouterr().out
        assert "--from" in out or "uv tool install -e" in out


class TestRunUpgradeVerifiesMove:
    def test_reports_version_move_after_upgrade(self, capsys):
        """After a successful reinstall, run_upgrade reports before -> after honestly."""
        before = {
            "source": "git",
            "version": "1.0.0",
            "commit": "aaaaaaaaaaaa",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "ref": "main",
        }
        after = dict(before, version="1.1.0", commit="bbbbbbbbbbbb")

        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                side_effect=[before, after],
            ),
            patch(
                "amplifier_workspace.upgrade._check_for_update",
                return_value=(True, "update available (aaaaaaaa → bbbbbbbb)"),
            ),
            patch("amplifier_workspace.upgrade._do_upgrade", return_value=True),
            patch("amplifier_workspace.upgrade._run_doctor_after_upgrade"),
        ):
            run_upgrade()

        out = capsys.readouterr().out
        assert "upgraded" in out.lower()
        assert "1.0.0" in out and "1.1.0" in out

    def test_reports_unchanged_when_version_did_not_move(self, capsys):
        """If nothing moved, run_upgrade says so plainly rather than implying a bump."""
        info = {
            "source": "git",
            "version": "1.0.0",
            "commit": "aaaaaaaaaaaa",
            "url": "https://github.com/microsoft/amplifier-workspace",
            "ref": "main",
        }

        with (
            patch(
                "amplifier_workspace.upgrade._get_install_info",
                side_effect=[info, dict(info)],
            ),
            patch(
                "amplifier_workspace.upgrade._check_for_update",
                return_value=(True, "update available"),
            ),
            patch("amplifier_workspace.upgrade._do_upgrade", return_value=True),
            patch("amplifier_workspace.upgrade._run_doctor_after_upgrade"),
        ):
            run_upgrade()

        out = capsys.readouterr().out
        assert "unchanged" in out.lower()
