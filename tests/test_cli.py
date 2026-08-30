"""Tests for CLI subcommands: setup, doctor, upgrade, config, list."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

import amplifier_workspace.cli as cli


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


# ---------------------------------------------------------------------------
# update subcommand (TDD: written before implementation)
# ---------------------------------------------------------------------------


def test_cli_update_calls_update_workspace(tmp_path):
    """'update <workdir>' subcommand calls update_workspace with resolved path."""
    with patch.object(sys, "argv", ["amplifier-workspace", "update", str(tmp_path)]):
        with patch("amplifier_workspace.workspace.update_workspace") as mock_update:
            importlib.reload(cli)
            cli.main()
    mock_update.assert_called_once_with(tmp_path.resolve())


def test_cli_update_defaults_to_cwd(monkeypatch, tmp_path):
    """'update' with no workdir argument defaults to the current working directory."""
    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["amplifier-workspace", "update"]):
        with patch("amplifier_workspace.workspace.update_workspace") as mock_update:
            importlib.reload(cli)
            cli.main()
    mock_update.assert_called_once_with(tmp_path.resolve())


# ---------------------------------------------------------------------------
# manifest subcommand
# ---------------------------------------------------------------------------


def test_cli_manifest_lists_absent_manifest(tmp_path, capsys):
    """'manifest <workdir>' with no WORKSPACE-MANIFEST.json prints a friendly message
    and exits 0 (never raises)."""
    with patch.object(sys, "argv", ["amplifier-workspace", "manifest", str(tmp_path)]):
        importlib.reload(cli)
        cli.main()
    captured = capsys.readouterr()
    assert "No WORKSPACE-MANIFEST.json" in captured.out


def test_cli_manifest_defaults_to_cwd(monkeypatch, tmp_path, capsys):
    """'manifest' with no workdir argument defaults to the current working directory."""
    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["amplifier-workspace", "manifest"]):
        importlib.reload(cli)
        cli.main()
    captured = capsys.readouterr()
    assert "No WORKSPACE-MANIFEST.json" in captured.out


def test_cli_manifest_add_then_list(tmp_path, capsys):
    """'manifest --add' creates an entry; a subsequent listing shows it as active."""
    with patch.object(
        sys,
        "argv",
        ["amplifier-workspace", "manifest", str(tmp_path), "--add", "dtu", "dtu-1"],
    ):
        importlib.reload(cli)
        cli.main()

    with patch.object(sys, "argv", ["amplifier-workspace", "manifest", str(tmp_path)]):
        importlib.reload(cli)
        cli.main()

    captured = capsys.readouterr()
    assert "dtu-1" in captured.out
    assert "1 active" in captured.out


def test_cli_manifest_add_with_note_and_teardown(tmp_path, capsys):
    """'manifest --add ... --note ... --teardown ...' records both optional fields."""
    with patch.object(
        sys,
        "argv",
        [
            "amplifier-workspace",
            "manifest",
            str(tmp_path),
            "--add",
            "gitea-repo",
            "myorg/myrepo",
            "--note",
            "scratch",
            "--teardown",
            "delete via UI",
        ],
    ):
        importlib.reload(cli)
        cli.main()

    from amplifier_workspace import manifest

    data = manifest.load_manifest(tmp_path)
    entry = data["resources"][0]
    assert entry["note"] == "scratch"
    assert entry["teardown"] == "delete via UI"


def test_cli_manifest_reap(tmp_path, capsys):
    """'manifest --reap <id>' marks a previously added resource reaped."""
    from amplifier_workspace import manifest

    manifest.add_resource(tmp_path, "dtu", "dtu-1")

    with patch.object(
        sys,
        "argv",
        ["amplifier-workspace", "manifest", str(tmp_path), "--reap", "dtu-1"],
    ):
        importlib.reload(cli)
        cli.main()

    captured = capsys.readouterr()
    assert "reaped" in captured.out.lower()
    data = manifest.load_manifest(tmp_path)
    assert data["resources"][0]["status"] == "reaped"


def test_cli_manifest_reap_unknown_id_exits_nonzero(tmp_path):
    """'manifest --reap' on an unknown id surfaces as a CLI error (nonzero exit)."""
    from amplifier_workspace import manifest

    manifest.add_resource(tmp_path, "dtu", "dtu-1")

    with patch.object(
        sys,
        "argv",
        ["amplifier-workspace", "manifest", str(tmp_path), "--reap", "does-not-exist"],
    ):
        importlib.reload(cli)
        with pytest.raises(SystemExit):
            cli.main()
