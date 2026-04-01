"""Tests for CLI subcommands: setup, doctor, upgrade, config, list."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

import amplifier_workspace.cli as cli


# ---------------------------------------------------------------------------
# help output
# ---------------------------------------------------------------------------


def test_help_output_includes_all_subcommands(capsys):
    """Help output lists all subcommands so users can discover them."""
    with patch.object(sys, "argv", ["amplifier-workspace"]):
        importlib.reload(cli)
        with pytest.raises(SystemExit):
            cli.main()

    captured = capsys.readouterr()
    help_text = captured.out
    for subcommand in ("setup", "doctor", "upgrade", "config", "list"):
        assert subcommand in help_text, f"'{subcommand}' missing from help output"


def test_help_output_updated_description(capsys):
    """Help output uses the user-facing description, not internal bootstrap copy."""
    with patch.object(sys, "argv", ["amplifier-workspace"]):
        importlib.reload(cli)
        with pytest.raises(SystemExit):
            cli.main()

    captured = capsys.readouterr()
    assert "Create and manage Amplifier development workspaces." in captured.out


# ---------------------------------------------------------------------------
# setup subcommand
# ---------------------------------------------------------------------------


def test_cli_setup_calls_run_wizard():
    """'setup' subcommand calls run_wizard()."""
    with patch.object(sys, "argv", ["amplifier-workspace", "setup"]):
        with patch("amplifier_workspace.wizard.run_wizard") as mock_wiz:
            importlib.reload(cli)
            cli.main()
    mock_wiz.assert_called_once()


# ---------------------------------------------------------------------------
# doctor subcommand
# ---------------------------------------------------------------------------


def test_cli_doctor_calls_run_doctor():
    """'doctor' subcommand calls run_doctor() and exits with its return code."""
    with patch.object(sys, "argv", ["amplifier-workspace", "doctor"]):
        with patch("amplifier_workspace.doctor.run_doctor", return_value=0) as mock_doc:
            importlib.reload(cli)
            with pytest.raises(SystemExit):
                cli.main()
    mock_doc.assert_called_once()


# ---------------------------------------------------------------------------
# upgrade subcommand
# ---------------------------------------------------------------------------


def test_cli_upgrade_default_flags():
    """'upgrade' subcommand calls run_upgrade(force=False, check_only=False) by default."""
    with patch.object(sys, "argv", ["amplifier-workspace", "upgrade"]):
        with patch("amplifier_workspace.upgrade.run_upgrade") as mock_upg:
            importlib.reload(cli)
            cli.main()
    mock_upg.assert_called_once_with(force=False, check_only=False)


def test_cli_upgrade_force_flag():
    """'upgrade --force' calls run_upgrade(force=True, check_only=False)."""
    with patch.object(sys, "argv", ["amplifier-workspace", "upgrade", "--force"]):
        with patch("amplifier_workspace.upgrade.run_upgrade") as mock_upg:
            importlib.reload(cli)
            cli.main()
    mock_upg.assert_called_once_with(force=True, check_only=False)


def test_cli_upgrade_check_flag():
    """'upgrade --check' calls run_upgrade(force=False, check_only=True)."""
    with patch.object(sys, "argv", ["amplifier-workspace", "upgrade", "--check"]):
        with patch("amplifier_workspace.upgrade.run_upgrade") as mock_upg:
            importlib.reload(cli)
            cli.main()
    mock_upg.assert_called_once_with(force=False, check_only=True)


# ---------------------------------------------------------------------------
# config subcommand
# ---------------------------------------------------------------------------


def test_cli_config_list_outputs_config(capsys):
    """'config list' prints configuration values in dot-notation."""
    mock_config = MagicMock()
    mock_config.bundle = "my-bundle"
    mock_config.default_repos = ["https://github.com/test/repo.git"]
    mock_config.agents_template = ""
    mock_config.tmux.enabled = False
    mock_config.tmux.windows = {}

    with patch.object(sys, "argv", ["amplifier-workspace", "config", "list"]):
        with patch("amplifier_workspace.config.load_config", return_value=mock_config):
            importlib.reload(cli)
            cli.main()

    captured = capsys.readouterr()
    assert "my-bundle" in captured.out or "bundle" in captured.out


# ---------------------------------------------------------------------------
# list subcommand
# ---------------------------------------------------------------------------


def test_cli_list_subcommand_prints_placeholder(capsys):
    """'list' subcommand prints a non-empty placeholder message."""
    with patch.object(sys, "argv", ["amplifier-workspace", "list"]):
        importlib.reload(cli)
        cli.main()

    captured = capsys.readouterr()
    assert len(captured.out.strip()) > 0


# ---------------------------------------------------------------------------
# -k / --kill flag
# ---------------------------------------------------------------------------


class TestCliKillFlag:
    """Tests for the -k/--kill flag wiring through to run_workspace."""

    def test_kill_flag_passes_kill_true(self, tmp_path):
        """-k flag passes kill=True to run_workspace."""
        with (
            patch("amplifier_workspace.config.load_config") as mock_cfg,
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            mock_cfg.return_value = MagicMock()
            cli.main([str(tmp_path), "-k"])

        mock_rw.assert_called_once()
        _, kwargs = mock_rw.call_args
        assert kwargs.get("kill") is True

    def test_no_kill_flag_passes_kill_false(self, tmp_path):
        """Omitting -k passes kill=False to run_workspace."""
        with (
            patch("amplifier_workspace.config.load_config") as mock_cfg,
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            mock_cfg.return_value = MagicMock()
            cli.main([str(tmp_path)])

        mock_rw.assert_called_once()
        _, kwargs = mock_rw.call_args
        assert kwargs.get("kill") is False

    def test_kill_flag_passes_correct_workdir(self, tmp_path):
        """-k flag passes the resolved workdir as the first positional arg."""
        with (
            patch("amplifier_workspace.config.load_config") as mock_cfg,
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            mock_cfg.return_value = MagicMock()
            cli.main([str(tmp_path), "-k"])

        mock_rw.assert_called_once()
        call_args, _ = mock_rw.call_args
        assert call_args[0] == tmp_path.resolve()
