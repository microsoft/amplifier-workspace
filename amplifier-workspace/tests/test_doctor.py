"""Tests for doctor.py: _print_check helper and always-run health checks."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from amplifier_workspace.doctor import (
    _print_check,
    run_doctor,
)


_SAMPLE_INSTALL_INFO = {
    "source": "git",
    "version": "1.0.0",
    "commit": "abcdef1234567890abcdef1234567890abcdef12",
    "url": "https://github.com/microsoft/amplifier-workspace",
}


def _make_which(available: set[str]):
    """Return a shutil.which side_effect that returns a path only for known commands."""
    def which(cmd):
        return f"/usr/bin/{cmd}" if cmd in available else None
    return which


class TestPrintCheck:
    def test_pass_contains_check_mark(self, capsys):
        """_print_check with passed=True outputs the check mark symbol (✓) or green ANSI."""
        _print_check("Python version", True, "3.11.0")
        captured = capsys.readouterr()
        # Should contain ✓ or green ANSI escape
        assert "✓" in captured.out or "\033[32m" in captured.out or "\x1b[32m" in captured.out

    def test_fail_contains_x_mark(self, capsys):
        """_print_check with passed=False outputs the failure symbol (✗) or red ANSI."""
        _print_check("git in PATH", False, "not found")
        captured = capsys.readouterr()
        # Should contain ✗ or red ANSI escape
        assert "✗" in captured.out or "\033[31m" in captured.out or "\x1b[31m" in captured.out

    def test_none_shows_skipped(self, capsys):
        """_print_check with passed=None outputs 'skipped'."""
        _print_check("tmux session", None)
        captured = capsys.readouterr()
        assert "skipped" in captured.out.lower()

    def test_pass_includes_label(self, capsys):
        """_print_check with passed=True includes the label in output."""
        _print_check("Python version", True, "3.11.0")
        captured = capsys.readouterr()
        assert "Python version" in captured.out

    def test_fail_includes_label_and_detail(self, capsys):
        """_print_check with passed=False includes label and detail in output."""
        _print_check("git in PATH", False, "not found")
        captured = capsys.readouterr()
        assert "git in PATH" in captured.out
        assert "not found" in captured.out


class TestRunDoctor:
    """Tests for run_doctor() with all external calls patched."""

    def _default_patches(
        self,
        *,
        git_available: bool = True,
        amplifier_available: bool = True,
        config_exists: bool = True,
        agents_template: str = "",
    ):
        """Return a dict of patch contexts for run_doctor tests."""
        mock_config = MagicMock()
        mock_config.default_repos = ["https://github.com/example/repo.git"]
        mock_config.agents_template = agents_template
        mock_config.tmux.enabled = False

        available = set()
        if git_available:
            available.add("git")
        if amplifier_available:
            available.add("amplifier")

        mock_config_path = MagicMock(spec=Path)
        mock_config_path.exists.return_value = config_exists

        return {
            "install_info": _SAMPLE_INSTALL_INFO,
            "update_result": (False, "up to date"),
            "which_side_effect": _make_which(available),
            "mock_config": mock_config,
            "mock_config_path": mock_config_path,
        }

    def test_prints_python_version(self, capsys):
        """run_doctor prints Python version information."""
        params = self._default_patches()

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            run_doctor()

        captured = capsys.readouterr()
        # Should mention Python or version info
        assert "python" in captured.out.lower() or "3." in captured.out

    def test_passes_when_git_found(self, capsys):
        """run_doctor returns 0 (all pass) when git is found in PATH."""
        params = self._default_patches(git_available=True)

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            exit_code = run_doctor()

        assert exit_code == 0

    def test_fails_when_git_missing(self, capsys):
        """run_doctor returns 1 when git is not found in PATH."""
        params = self._default_patches(git_available=False)

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            exit_code = run_doctor()

        assert exit_code == 1

    def test_returns_zero_when_all_pass(self, capsys):
        """run_doctor returns 0 when all required checks pass."""
        params = self._default_patches(
            git_available=True,
            amplifier_available=True,
            config_exists=True,
        )

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            exit_code = run_doctor()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "all checks passed" in captured.out.lower()

    def test_fails_when_config_missing(self, capsys):
        """run_doctor returns 1 when config file does not exist."""
        params = self._default_patches(config_exists=False)

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            exit_code = run_doctor()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "setup" in captured.out.lower()

    def test_agents_template_fails_when_file_missing(self, capsys):
        """run_doctor returns 1 when agents_template is set but file doesn't exist."""
        params = self._default_patches(agents_template="/nonexistent/template.yaml")

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            exit_code = run_doctor()

        assert exit_code == 1

    def test_update_warning_does_not_cause_failure(self, capsys):
        """run_doctor returns 0 even when an update is available (warning only)."""
        params = self._default_patches()
        params["update_result"] = (True, "update available (abcd1234 → efgh5678)")

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            exit_code = run_doctor()

        assert exit_code == 0

    def test_tmux_check_shown_as_skipped_when_disabled(self, capsys):
        """run_doctor shows tmux check as skipped when tmux.enabled is False."""
        params = self._default_patches()

        with (
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            ),
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            ),
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            ),
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            ),
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            ),
        ):
            run_doctor()

        captured = capsys.readouterr()
        # tmux section should appear and show skipped
        assert "tmux" in captured.out.lower()
        assert "skipped" in captured.out.lower()
