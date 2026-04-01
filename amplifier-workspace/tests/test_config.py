"""Tests for config.py dataclasses: WorkspaceConfig and TmuxConfig defaults."""

from amplifier_workspace.config import TmuxConfig, WorkspaceConfig


class TestWorkspaceConfigDefaults:
    def test_bundle_defaults_to_amplifier_dev(self):
        cfg = WorkspaceConfig()
        assert cfg.bundle == "amplifier-dev"

    def test_agents_template_defaults_to_empty_string(self):
        cfg = WorkspaceConfig()
        assert cfg.agents_template == ""

    def test_default_repos_includes_amplifier_git(self):
        cfg = WorkspaceConfig()
        assert any("amplifier.git" in repo for repo in cfg.default_repos)

    def test_default_repos_has_three_entries(self):
        cfg = WorkspaceConfig()
        assert len(cfg.default_repos) == 3

    def test_tmux_enabled_is_false(self):
        cfg = WorkspaceConfig()
        assert cfg.tmux.enabled is False

    def test_tmux_windows_is_dict(self):
        cfg = WorkspaceConfig()
        assert isinstance(cfg.tmux.windows, dict)


class TestTmuxConfig:
    def test_enabled_defaults_to_false(self):
        tmux = TmuxConfig()
        assert tmux.enabled is False

    def test_windows_defaults_to_dict_with_amplifier_and_shell_keys(self):
        tmux = TmuxConfig()
        assert "amplifier" in tmux.windows
        assert "shell" in tmux.windows

    def test_custom_windows_can_be_set(self):
        custom_windows = {"main": "vim .", "logs": "tail -f app.log"}
        tmux = TmuxConfig(windows=custom_windows)
        assert tmux.windows == custom_windows
