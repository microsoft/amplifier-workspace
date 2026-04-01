"""Tests for workspace.py: create_agents_md and create_amplifier_settings."""

import pytest
from pathlib import Path

from amplifier_workspace.config import WorkspaceConfig
from amplifier_workspace.workspace import create_agents_md, create_amplifier_settings


class TestCreateAgentsMd:
    def test_creates_from_builtin_template(self, tmp_path: Path):
        """Creates AGENTS.md from builtin template when none exists."""
        config = WorkspaceConfig()
        create_agents_md(tmp_path, config)
        agents_md = tmp_path / "AGENTS.md"
        assert agents_md.exists()
        assert len(agents_md.read_text()) > 100

    def test_skips_if_already_exists(self, tmp_path: Path):
        """Does not overwrite existing AGENTS.md."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("original-content")
        config = WorkspaceConfig()
        create_agents_md(tmp_path, config)
        assert agents_md.read_text() == "original-content"

    def test_uses_custom_template_when_configured(self, tmp_path: Path):
        """Uses custom template file when agents_template path is set and exists."""
        custom_template = tmp_path / "custom-agents.md"
        custom_template.write_text("# Custom Template\n\nCustom content here.\n")
        config = WorkspaceConfig(agents_template=str(custom_template))
        workdir = tmp_path / "workspace"
        workdir.mkdir()
        create_agents_md(workdir, config)
        agents_md = workdir / "AGENTS.md"
        assert agents_md.exists()
        assert agents_md.read_text() == "# Custom Template\n\nCustom content here.\n"

    def test_falls_back_to_builtin_if_custom_path_missing(self, tmp_path: Path):
        """Falls back to builtin template if custom path does not exist, and warns."""
        config = WorkspaceConfig(agents_template="/nonexistent/path/AGENTS.md")
        with pytest.warns(UserWarning, match="agents_template path does not exist"):
            create_agents_md(tmp_path, config)
        agents_md = tmp_path / "AGENTS.md"
        assert agents_md.exists()
        assert len(agents_md.read_text()) > 100

    def test_builtin_template_mentions_amplifier(self, tmp_path: Path):
        """Builtin template content contains the word 'amplifier'."""
        config = WorkspaceConfig()
        create_agents_md(tmp_path, config)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "amplifier" in content.lower()


class TestCreateAmplifierSettings:
    def test_creates_amplifier_settings_yaml(self, tmp_path: Path):
        """Creates .amplifier/settings.yaml in the workspace directory."""
        config = WorkspaceConfig(bundle="my-bundle")
        create_amplifier_settings(tmp_path, config)
        settings = tmp_path / ".amplifier" / "settings.yaml"
        assert settings.exists()

    def test_settings_contains_bundle_name(self, tmp_path: Path):
        """settings.yaml includes the configured bundle name."""
        config = WorkspaceConfig(bundle="my-bundle")
        create_amplifier_settings(tmp_path, config)
        content = (tmp_path / ".amplifier" / "settings.yaml").read_text()
        assert "my-bundle" in content

    def test_creates_amplifier_directory(self, tmp_path: Path):
        """Creates .amplifier/ directory if it does not exist."""
        config = WorkspaceConfig(bundle="amplifier-dev")
        create_amplifier_settings(tmp_path, config)
        assert (tmp_path / ".amplifier").is_dir()

    def test_skips_if_settings_already_exists(self, tmp_path: Path):
        """Does not overwrite existing .amplifier/settings.yaml."""
        amplifier_dir = tmp_path / ".amplifier"
        amplifier_dir.mkdir()
        settings = amplifier_dir / "settings.yaml"
        settings.write_text("bundle:\n  active: original-bundle\n")
        config = WorkspaceConfig(bundle="new-bundle")
        create_amplifier_settings(tmp_path, config)
        assert "original-bundle" in settings.read_text()
