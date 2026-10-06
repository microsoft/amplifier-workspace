"""Tests for config.py dataclasses: WorkspaceConfig and TmuxConfig defaults."""

import importlib.resources
import tomllib
from pathlib import Path

import pytest

from amplifier_workspace.config import (
    DEFAULT_BUNDLE,
    TmuxConfig,
    WorkspaceConfig,
    load_config,
)


class TestWorkspaceConfigDefaults:
    def test_bundle_defaults_to_anchors_amp_dev(self):
        cfg = WorkspaceConfig()
        assert cfg.bundle == "anchors-amp-dev"

    def test_bundled_template_matches_default_bundle(self):
        template = (
            importlib.resources.files("amplifier_workspace")
            / "templates"
            / "default-config.toml"
        )
        data = tomllib.loads(template.read_text(encoding="utf-8"))
        assert data["workspace"]["bundle"] == DEFAULT_BUNDLE == "anchors-amp-dev"

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


class TestLoadConfig:
    def test_returns_defaults_when_file_missing(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.bundle == "anchors-amp-dev"
        assert len(cfg.default_repos) == 3
        assert cfg.tmux.enabled is False

    @pytest.mark.parametrize("content", ["", '[workspace]\nagents_template = ""\n'])
    def test_defaults_when_bundle_key_missing(self, tmp_path: Path, content: str):
        config_file = tmp_path / "config.toml"
        config_file.write_text(content)
        assert load_config(config_file).bundle == "anchors-amp-dev"

    @pytest.mark.parametrize("bundle", ["amplifier-dev", "my-custom-bundle"])
    def test_preserves_explicit_bundle_and_file_bytes(self, tmp_path: Path, bundle: str):
        config_file = tmp_path / "config.toml"
        original = (
            f'# Saved selection\r\n[workspace]\r\nbundle = "{bundle}"  # keep\r\n'
        ).encode()
        config_file.write_bytes(original)
        cfg = load_config(config_file)
        assert cfg.bundle == bundle
        assert len(cfg.default_repos) == 3
        assert config_file.read_bytes() == original

    def test_merges_repos_from_file(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[workspace]\ndefault_repos = ["https://github.com/example/repo.git"]\n'
        )
        cfg = load_config(config_file)
        assert cfg.default_repos == ["https://github.com/example/repo.git"]

    def test_merges_tmux_enabled(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[tmux]\nenabled = true\n")
        cfg = load_config(config_file)
        assert cfg.tmux.enabled is True

    def test_merges_tmux_windows(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[tmux.windows]\ncustom_window = 'vim .'\n")
        cfg = load_config(config_file)
        assert cfg.tmux.windows == {"custom_window": "vim ."}

    def test_expands_tilde_in_agents_template(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[workspace]\nagents_template = "~/my-template.md"\n')
        cfg = load_config(config_file)
        assert not cfg.agents_template.startswith("~")
        assert cfg.agents_template.endswith("my-template.md")

    def test_partial_tmux_config_keeps_defaults(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[tmux]\nenabled = true\n")
        cfg = load_config(config_file)
        assert cfg.tmux.enabled is True
        assert "amplifier" in cfg.tmux.windows
