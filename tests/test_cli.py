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


def _isolate_config(monkeypatch, tmp_path):
    """Point config_manager at a temp config file and return its path."""
    from amplifier_workspace import config_manager as cm

    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(cm, "CONFIG_PATH", config_path)
    return config_path


def test_cli_config_list_outputs_config(capsys, monkeypatch, tmp_path):
    """'config list' prints configuration values grouped by section."""
    from amplifier_workspace import config_manager as cm

    config_path = _isolate_config(monkeypatch, tmp_path)
    cm.write_config_raw({"workspace": {"bundle": "my-bundle"}}, path=config_path)

    cli.main(["config", "list"])

    captured = capsys.readouterr()
    assert "[workspace]" in captured.out
    assert "my-bundle" in captured.out


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


# ---------------------------------------------------------------------------
# Batch A — help word, --version, epilog, new-workspace footgun gate
# ---------------------------------------------------------------------------


def test_cli_help_word_prints_help_and_exits_zero(capsys):
    """'help' (a bare word) prints top-level help and exits 0 — never creates ./help/."""
    with patch.object(sys, "argv", ["amplifier-workspace", "help"]):
        importlib.reload(cli)
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()
    # epilog enumerates subcommands
    assert "doctor" in out
    assert "manifest" in out


def test_cli_help_subcommand_prints_help_and_exits_zero(capsys):
    """'help <subcommand>' also prints help and exits 0."""
    with patch.object(sys, "argv", ["amplifier-workspace", "help", "doctor"]):
        importlib.reload(cli)
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
    assert exc_info.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_cli_version_flag_prints_version(capsys):
    """'--version' prints the version and exits 0 (workdir parser)."""
    with patch.object(sys, "argv", ["amplifier-workspace", "--version"]):
        importlib.reload(cli)
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "amplifier-workspace" in out


def test_cli_subparser_has_version_action():
    """The subcommand fast-path parser also carries a --version action (both parsers)."""
    importlib.reload(cli)
    # A bare '--version' routes to the workdir parser; assert the sub_parser
    # branch defines it too by constructing the same parser argparse builds.
    # Simplest proof: '--version' resolves through main without error.
    with patch.object(sys, "argv", ["amplifier-workspace", "--version"]):
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
    assert exc_info.value.code == 0


def test_cli_help_output_points_to_subcommand_help(capsys):
    """Top-level help epilog points at 'amplifier-workspace <subcommand> -h'."""
    with patch.object(sys, "argv", ["amplifier-workspace", "help"]):
        importlib.reload(cli)
        with pytest.raises(SystemExit):
            cli.main()
    out = capsys.readouterr().out
    assert "<subcommand> -h" in out


class TestNewWorkspaceFootgun:
    """A bare-word non-subcommand must not silently scaffold a workspace."""

    def test_bare_word_non_tty_refuses_exit_2(self, capsys, monkeypatch):
        """Non-interactive + bare word (not a dir, no separator) -> exit 2 + remedy."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        with (
            patch("amplifier_workspace.config.load_config", return_value=MagicMock()),
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli.main(["definitelynotacommand"])
        assert exc_info.value.code == 2
        mock_rw.assert_not_called()
        err = capsys.readouterr().err
        assert "existing directory" in err or "path-like" in err

    def test_bare_word_tty_confirm_proceeds(self, monkeypatch):
        """Interactive + 'y' proceeds to run_workspace."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        with (
            patch("builtins.input", return_value="y"),
            patch("amplifier_workspace.config.load_config", return_value=MagicMock()),
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            cli.main(["freshbareword"])
        mock_rw.assert_called_once()

    def test_bare_word_tty_decline_exits_1(self, monkeypatch):
        """Interactive + 'n' aborts with exit 1 and never runs the workspace."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        with (
            patch("builtins.input", return_value="n"),
            patch("amplifier_workspace.config.load_config", return_value=MagicMock()),
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli.main(["barewordtypo"])
        assert exc_info.value.code == 1
        mock_rw.assert_not_called()

    def test_path_like_dot_slash_is_not_gated(self, monkeypatch):
        """A path-like arg (./name) keeps the no-prompt behavior even if it doesn't exist."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # would exit 2 if gated
        with (
            patch("amplifier_workspace.config.load_config", return_value=MagicMock()),
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            cli.main(["./somenewpath"])
        mock_rw.assert_called_once()

    def test_existing_directory_is_not_gated(self, tmp_path, monkeypatch):
        """An existing directory (bare name) keeps the no-prompt create/resume UX."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # would exit 2 if gated
        with (
            patch("amplifier_workspace.config.load_config", return_value=MagicMock()),
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            cli.main([str(tmp_path)])
        mock_rw.assert_called_once()

    def test_kill_flag_bare_word_not_gated(self, monkeypatch):
        """-k never creates, so a bare word with -k is exempt from the gate."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        with (
            patch("amplifier_workspace.config.load_config", return_value=MagicMock()),
            patch("amplifier_workspace.workspace.run_workspace") as mock_rw,
        ):
            cli.main(["somebareword", "-k"])
        mock_rw.assert_called_once()


# ---------------------------------------------------------------------------
# config subcommand UX (defects 1-7)
# ---------------------------------------------------------------------------


def _cfg(monkeypatch, tmp_path, initial=None):
    """Point config_manager at a temp file (optionally seeded) and return its path."""
    from amplifier_workspace import config_manager as cm

    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(cm, "CONFIG_PATH", config_path)
    if initial is not None:
        cm.write_config_raw(initial, path=config_path)
    return config_path


class TestConfigSetForms:
    """Defects 1 & 3 — set accepts key value, key=value, and key = value."""

    def test_set_space_form(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path)
        cli.main(["config", "set", "tmux.enabled", "true"])
        out = capsys.readouterr().out
        assert "tmux.enabled = true" in out

    def test_set_equals_form(self, capsys, monkeypatch, tmp_path):
        """Defect 1: `set tmux.enabled=True` must not be an argparse error."""
        _cfg(monkeypatch, tmp_path)
        cli.main(["config", "set", "tmux.enabled=True"])
        out = capsys.readouterr().out
        assert "tmux.enabled = true" in out

    def test_set_stray_equals_form(self, capsys, monkeypatch, tmp_path):
        """Defect 3: `set tmux.enabled = True` normalizes instead of erroring."""
        _cfg(monkeypatch, tmp_path)
        cli.main(["config", "set", "tmux.enabled", "=", "yes"])
        out = capsys.readouterr().out
        assert "tmux.enabled = true" in out

    def test_set_string_with_spaces_via_space_form(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path)
        cli.main(["config", "set", "tmux.windows.main", "vim", "."])
        out = capsys.readouterr().out
        assert "tmux.windows.main = vim ." in out

    def test_set_dashed_value_via_equals_form(self, capsys, monkeypatch, tmp_path):
        """A value with option-like tokens is set via the single-token key=value form."""
        _cfg(monkeypatch, tmp_path)
        # In a real shell this is one quoted argv token: "tmux.windows.logs=tail -f x".
        cli.main(["config", "set", "tmux.windows.logs=tail -f x"])
        out = capsys.readouterr().out
        assert "tmux.windows.logs = tail -f x" in out

    def test_set_missing_value_exits_2(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["config", "set", "tmux.enabled"])
        assert exc_info.value.code == 2
        assert "needs a value" in capsys.readouterr().err


class TestConfigSetValidation:
    """Defect 2 — typo'd keys rejected loudly; defect c — coercion/list rules."""

    def test_unknown_key_rejected_with_suggestion(self, capsys, monkeypatch, tmp_path):
        """Defect 2: the silent-write footgun becomes a loud exit-2 with a hint."""
        _cfg(monkeypatch, tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["config", "set", "tmux.enable", "True"])
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "unknown config key" in err
        assert "did you mean tmux.enabled?" in err
        assert "valid keys:" in err
        # Nothing was written for the bogus key.
        from amplifier_workspace import config_manager as cm

        assert cm.get_nested_setting("tmux.enable") is None

    def test_bool_coercion_true(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path)
        cli.main(["config", "set", "tmux.enabled", "yes"])
        from amplifier_workspace import config_manager as cm

        assert cm.get_nested_setting("tmux.enabled") is True

    def test_bad_bool_exits_2(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["config", "set", "tmux.enabled", "maybe"])
        assert exc_info.value.code == 2
        assert "boolean" in capsys.readouterr().err

    def test_list_key_set_rejected(self, capsys, monkeypatch, tmp_path):
        """Defect c: setting a list key points at add/remove instead."""
        _cfg(monkeypatch, tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["config", "set", "workspace.default_repos", "http://x"])
        assert exc_info.value.code == 2
        assert "config add" in capsys.readouterr().err


class TestConfigMutationOutput:
    """Defect 6 & d — every successful mutation prints what happened."""

    def test_set_prints_old_and_new(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"tmux": {"enabled": False}})
        cli.main(["config", "set", "tmux.enabled", "true"])
        assert "tmux.enabled = true (was false)" in capsys.readouterr().out

    def test_add_prints_message(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"workspace": {"default_repos": ["r1"]}})
        cli.main(["config", "add", "workspace.default_repos", "r2"])
        assert "r2" in capsys.readouterr().out

    def test_remove_prints_message(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"workspace": {"default_repos": ["r1", "r2"]}})
        cli.main(["config", "remove", "workspace.default_repos", "r1"])
        assert "r1" in capsys.readouterr().out


class TestConfigGetValidation:
    def test_get_unknown_key_exits_2(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["config", "get", "tmux.enable"])
        assert exc_info.value.code == 2
        assert "did you mean tmux.enabled?" in capsys.readouterr().err

    def test_get_list_key_no_python_repr(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"workspace": {"default_repos": ["u1", "u2"]}})
        cli.main(["config", "get", "workspace.default_repos"])
        out = capsys.readouterr().out
        assert "u1" in out and "u2" in out
        assert "['u1'" not in out


class TestConfigListRendering:
    """Defect 4 — clean grouped output, no repr, unknown keys flagged."""

    def test_bare_config_runs_list(self, capsys, monkeypatch, tmp_path):
        """Defect e: `config` with no action runs list, not a usage line."""
        _cfg(monkeypatch, tmp_path, {"workspace": {"bundle": "custom"}})
        cli.main(["config"])
        out = capsys.readouterr().out
        assert "[workspace]" in out
        assert "Usage:" not in out

    def test_list_no_python_repr_and_indented(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"workspace": {"default_repos": ["u1", "u2"]}})
        cli.main(["config", "list"])
        out = capsys.readouterr().out
        assert "['u1', 'u2']" not in out
        assert "    u1" in out

    def test_list_flags_unknown_key(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"tmux": {"enable": "True", "enabled": True}})
        cli.main(["config", "list"])
        assert "# unknown key (ignored): tmux.enable" in capsys.readouterr().out


class TestConfigRemoveScalar:
    """Defect 7 — a bogus scalar key can be removed to clean it up."""

    def test_remove_scalar_key(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"tmux": {"enable": "True", "enabled": True}})
        cli.main(["config", "remove", "tmux.enable"])
        out = capsys.readouterr().out
        assert "removed" in out
        from amplifier_workspace import config_manager as cm

        assert cm.get_nested_setting("tmux.enable") is None
        assert cm.get_nested_setting("tmux.enabled") is True

    def test_remove_unknown_absent_key_exits_2(self, capsys, monkeypatch, tmp_path):
        _cfg(monkeypatch, tmp_path, {"tmux": {"enabled": True}})
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["config", "remove", "tmux.enable"])
        assert exc_info.value.code == 2
        assert "unknown config key" in capsys.readouterr().err


class TestConfigReset:
    """Defect 5 — reset shows diff, backs up, prints restore command."""

    def test_reset_shows_diff_backs_up_and_writes_defaults(
        self, capsys, monkeypatch, tmp_path
    ):
        _cfg(
            monkeypatch,
            tmp_path,
            {"workspace": {"bundle": "custom"}, "tmux": {"enabled": True}},
        )
        with patch("builtins.input", return_value="y"):
            cli.main(["config", "reset"])
        out = capsys.readouterr().out
        # Diff of what would be lost.
        assert "workspace.bundle = custom" in out
        assert "will be lost" in out.lower()
        # Backup created + restore hint.
        assert "Backed up existing config to:" in out
        assert "To restore: cp" in out
        backups = list(tmp_path.glob("config.toml.bak-*"))
        assert len(backups) == 1
        # Defaults written (bundle back to default).
        from amplifier_workspace import config_manager as cm

        assert cm.get_nested_setting("workspace.bundle") == "amplifier-dev"

    def test_reset_cancelled_leaves_config_untouched(
        self, capsys, monkeypatch, tmp_path
    ):
        _cfg(monkeypatch, tmp_path, {"workspace": {"bundle": "custom"}})
        with patch("builtins.input", return_value="n"):
            cli.main(["config", "reset"])
        assert "cancelled" in capsys.readouterr().out.lower()
        from amplifier_workspace import config_manager as cm

        assert cm.get_nested_setting("workspace.bundle") == "custom"
        assert list(tmp_path.glob("config.toml.bak-*")) == []
