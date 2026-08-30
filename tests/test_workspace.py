"""Tests for workspace.py: create_agents_md, create_amplifier_settings, setup_workspace, run_workspace."""

import pytest
from pathlib import Path
from unittest.mock import patch

from amplifier_workspace.config import WorkspaceConfig, TmuxConfig
from amplifier_workspace import manifest as _manifest_mod
from amplifier_workspace.workspace import (
    _launch_with_tmux,
    create_agents_md,
    create_amplifier_settings,
    setup_workspace,
    run_workspace,
)


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


class TestSetupWorkspace:
    @patch("amplifier_workspace.workspace._git")
    def test_initializes_new_repo(self, mock_git, tmp_path: Path):
        """Calls init_repo with workdir when not already a git repo."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.init_repo.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace._git")
    def test_adds_all_default_repos_as_submodules(self, mock_git, tmp_path: Path):
        """Calls add_submodule once per default_repos entry."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        assert mock_git.add_submodule.call_count == len(config.default_repos)

    @patch("amplifier_workspace.workspace._git")
    def test_update_submodules_called_after_adding(self, mock_git, tmp_path: Path):
        """Calls update_submodules with workdir after adding submodules (replaces checkout)."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.update_submodules.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace._git")
    def test_creates_initial_commit(self, mock_git, tmp_path: Path):
        """Calls initial_commit with a message containing 'workspace'."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.initial_commit.assert_called_once()
        args = mock_git.initial_commit.call_args.args
        assert "workspace" in args[1].lower()

    @patch("amplifier_workspace.workspace._git")
    def test_skips_git_init_for_existing_repo(self, mock_git, tmp_path: Path):
        """Does not call init_repo, add_submodule, or checkout_submodules for existing repo."""
        mock_git.is_git_repo.return_value = True
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.init_repo.assert_not_called()
        mock_git.add_submodule.assert_not_called()
        mock_git.checkout_submodules.assert_not_called()

    @patch("amplifier_workspace.workspace._git")
    def test_creates_agents_md_for_existing_repo(self, mock_git, tmp_path: Path):
        """Always creates AGENTS.md even when repo already exists."""
        mock_git.is_git_repo.return_value = True
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        assert (tmp_path / "AGENTS.md").exists()

    @patch("amplifier_workspace.workspace._git")
    def test_skips_submodule_checkout_when_no_repos(self, mock_git, tmp_path: Path):
        """Does not call checkout_submodules when default_repos is empty."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig(default_repos=[])
        setup_workspace(tmp_path, config)
        mock_git.checkout_submodules.assert_not_called()

    @patch("amplifier_workspace.workspace.create_amplifier_settings")
    @patch("amplifier_workspace.workspace.create_agents_md")
    @patch("amplifier_workspace.workspace._git")
    def test_agents_md_and_settings_created_before_initial_commit(
        self, mock_git, mock_agents_md, mock_settings, tmp_path: Path
    ):
        """For a new repo, AGENTS.md and settings.yaml are created BEFORE initial_commit."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig(default_repos=[])

        call_order: list[str] = []
        mock_agents_md.side_effect = lambda *_: call_order.append("agents_md")
        mock_settings.side_effect = lambda *_: call_order.append("settings")
        mock_git.initial_commit.side_effect = lambda *_: call_order.append("initial_commit")

        setup_workspace(tmp_path, config)

        # agents_md and settings must both appear before initial_commit inside the new-repo block
        first_agents = call_order.index("agents_md")
        first_settings = call_order.index("settings")
        first_commit = call_order.index("initial_commit")
        assert first_agents < first_commit, "create_agents_md must be called before initial_commit"
        assert first_settings < first_commit, (
            "create_amplifier_settings must be called before initial_commit"
        )


class TestRunWorkspace:
    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_normal_path_calls_setup_then_launch(
        self,
        mock_config_path,
        mock_load_config,
        mock_setup,
        mock_launch,
        tmp_path: Path,
    ):
        """Default run calls setup_workspace then _launch_amplifier."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        config = WorkspaceConfig()
        run_workspace(tmp_path, config)
        mock_setup.assert_called_once()
        mock_launch.assert_called_once()

    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_removes_directory_skips_setup(
        self,
        mock_config_path,
        mock_load_config,
        mock_rmtree,
        mock_setup,
        tmp_path: Path,
    ):
        """destroy=True calls shutil.rmtree and does NOT call setup_workspace."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        config = WorkspaceConfig()
        run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_called_once_with(tmp_path)
        mock_setup.assert_not_called()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_fresh_removes_then_recreates(
        self,
        mock_config_path,
        mock_load_config,
        mock_setup,
        mock_launch,
        tmp_path: Path,
    ):
        """fresh=True removes existing directory then calls setup and launch."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        (tmp_path / "existing_file.txt").write_text("content")
        config = WorkspaceConfig()
        run_workspace(tmp_path, config, fresh=True)
        mock_setup.assert_called_once()
        mock_launch.assert_called_once()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_noop_when_dir_missing(
        self,
        mock_config_path,
        mock_load_config,
        mock_setup,
        mock_launch,
        tmp_path: Path,
    ):
        """destroy=True on a missing directory does not raise and skips setup/launch."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        nonexistent = tmp_path / "nonexistent"
        config = WorkspaceConfig()
        run_workspace(nonexistent, config, destroy=True)
        mock_setup.assert_not_called()
        mock_launch.assert_not_called()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.wizard.run_wizard")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_workspace_triggers_wizard_when_no_config(
        self,
        mock_config_path,
        mock_load_config,
        mock_run_wizard,
        mock_setup,
        mock_launch,
        tmp_path: Path,
    ):
        """Runs the first-run wizard when CONFIG_PATH does not exist."""
        mock_config_path.exists.return_value = False
        mock_load_config.return_value = WorkspaceConfig()
        config = WorkspaceConfig()
        run_workspace(tmp_path, config)
        mock_run_wizard.assert_called_once()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace._git")
    @patch("amplifier_workspace.wizard.run_wizard")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_workspace_skips_wizard_when_config_exists(
        self,
        mock_config_path,
        mock_load_config,
        mock_run_wizard,
        mock_git,
        mock_launch,
        tmp_path: Path,
    ):
        """Does not run wizard when CONFIG_PATH already exists."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        run_workspace(tmp_path, config)
        mock_run_wizard.assert_not_called()


class TestRunWorkspaceKillFlag:
    @patch("amplifier_workspace.workspace.tmux.kill_session")
    @patch("amplifier_workspace.workspace.tmux.session_name_from_path")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_kill_calls_kill_session_when_tmux_enabled(
        self,
        mock_config_path,
        mock_load_config,
        mock_session_name,
        mock_kill_session,
        tmp_path: Path,
    ):
        """kill=True with tmux enabled calls tmux.kill_session with derived session name."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=True))
        mock_session_name.return_value = "my-workspace"
        config = WorkspaceConfig()
        run_workspace(tmp_path, config, kill=True)
        mock_session_name.assert_called_once_with(tmp_path)
        mock_kill_session.assert_called_once_with("my-workspace")

    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.workspace.tmux.kill_session")
    @patch("amplifier_workspace.workspace.tmux.session_name_from_path")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_kill_returns_without_modifying_directory(
        self,
        mock_config_path,
        mock_load_config,
        mock_session_name,
        mock_kill_session,
        mock_rmtree,
        mock_setup,
        tmp_path: Path,
    ):
        """kill=True returns immediately — no rmtree and no setup_workspace called."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=True))
        mock_session_name.return_value = "my-workspace"
        config = WorkspaceConfig()
        run_workspace(tmp_path, config, kill=True)
        mock_rmtree.assert_not_called()
        mock_setup.assert_not_called()

    @patch("amplifier_workspace.workspace.tmux.kill_session")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_kill_noop_when_tmux_disabled(
        self,
        mock_config_path,
        mock_load_config,
        mock_kill_session,
        tmp_path: Path,
    ):
        """kill=True with tmux disabled is a no-op — kill_session is never called."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=False))
        config = WorkspaceConfig()
        run_workspace(tmp_path, config, kill=True)
        mock_kill_session.assert_not_called()


class TestRunWorkspaceDestroyWithTmux:
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.workspace.tmux.kill_session")
    @patch("amplifier_workspace.workspace.tmux.session_name_from_path")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_kills_tmux_session_before_rmtree(
        self,
        mock_config_path,
        mock_load_config,
        mock_session_name,
        mock_kill_session,
        mock_rmtree,
        tmp_path: Path,
    ):
        """destroy=True with tmux enabled kills the session before removing the directory."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=True))
        mock_session_name.return_value = "my-workspace"

        call_order: list[str] = []
        mock_kill_session.side_effect = lambda *_: call_order.append("kill_session")
        mock_rmtree.side_effect = lambda *_: call_order.append("rmtree")

        config = WorkspaceConfig()
        run_workspace(tmp_path, config, destroy=True)

        assert call_order == ["kill_session", "rmtree"]

    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.workspace.tmux.kill_session")
    @patch("amplifier_workspace.workspace.tmux.session_name_from_path")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_still_removes_directory(
        self,
        mock_config_path,
        mock_load_config,
        mock_session_name,
        mock_kill_session,
        mock_rmtree,
        tmp_path: Path,
    ):
        """destroy=True with tmux enabled still removes the workspace directory."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=True))
        mock_session_name.return_value = "my-workspace"

        config = WorkspaceConfig()
        run_workspace(tmp_path, config, destroy=True)

        mock_rmtree.assert_called_once_with(tmp_path)


class TestLaunchWithTmux:
    @patch("amplifier_workspace.workspace.tmux.attach_session")
    @patch("amplifier_workspace.workspace.tmux.create_session")
    @patch("amplifier_workspace.workspace.tmux.session_exists")
    @patch("amplifier_workspace.workspace.tmux.session_name_from_path")
    def test_creates_and_attaches_new_session(
        self,
        mock_name,
        mock_exists,
        mock_create,
        mock_attach,
        tmp_path: Path,
    ):
        """When session does not exist, create_session then attach_session are called."""
        mock_name.return_value = "my-workspace"
        mock_exists.return_value = False
        config = WorkspaceConfig()
        _launch_with_tmux(tmp_path, config)
        mock_create.assert_called_once_with(tmp_path, config.tmux)
        mock_attach.assert_called_once_with("my-workspace")

    @patch("amplifier_workspace.workspace.tmux.attach_session")
    @patch("amplifier_workspace.workspace.tmux.create_session")
    @patch("amplifier_workspace.workspace.tmux.session_exists")
    @patch("amplifier_workspace.workspace.tmux.session_name_from_path")
    def test_reattaches_existing_session_without_create(
        self,
        mock_name,
        mock_exists,
        mock_create,
        mock_attach,
        tmp_path: Path,
    ):
        """When session already exists, create_session is NOT called, attach_session IS called."""
        mock_name.return_value = "my-workspace"
        mock_exists.return_value = True
        config = WorkspaceConfig()
        _launch_with_tmux(tmp_path, config)
        mock_create.assert_not_called()
        mock_attach.assert_called_once_with("my-workspace")

    @patch("amplifier_workspace.workspace._launch_with_tmux")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_setup_runs_before_session_launch(
        self,
        mock_config_path,
        mock_load_config,
        mock_setup,
        mock_launch_tmux,
        tmp_path: Path,
    ):
        """setup_workspace is called before _launch_with_tmux when tmux is enabled."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=True))

        call_order: list[str] = []
        mock_setup.side_effect = lambda *_: call_order.append("setup")
        mock_launch_tmux.side_effect = lambda *_: call_order.append("launch_tmux")

        config = WorkspaceConfig()
        run_workspace(tmp_path, config)
        assert call_order == ["setup", "launch_tmux"]

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace._launch_with_tmux")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_tier1_fallback_when_tmux_disabled(
        self,
        mock_config_path,
        mock_load_config,
        mock_setup,
        mock_launch_tmux,
        mock_launch_amplifier,
        tmp_path: Path,
    ):
        """When tmux is disabled, _launch_amplifier (tier 1) is called instead of _launch_with_tmux."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig(tmux=TmuxConfig(enabled=False))
        config = WorkspaceConfig()
        run_workspace(tmp_path, config)
        mock_launch_amplifier.assert_called_once()
        mock_launch_tmux.assert_not_called()


# ---------------------------------------------------------------------------
# New tests for update_submodules in setup_workspace and update_workspace
# (TDD: written before implementation)
# ---------------------------------------------------------------------------

from amplifier_workspace.workspace import update_workspace


class TestSetupWorkspaceUpdateSubmodules:
    """setup_workspace must call update_submodules (not checkout_submodules) for new repos."""

    @patch("amplifier_workspace.workspace._git")
    def test_update_submodules_called_on_new_repo(self, mock_git, tmp_path: Path):
        """setup_workspace calls update_submodules when default repos exist."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        mock_git.update_submodules.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace._git")
    def test_update_submodules_not_called_when_no_repos(self, mock_git, tmp_path: Path):
        """setup_workspace skips update_submodules when default_repos is empty."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig(default_repos=[])
        setup_workspace(tmp_path, config)
        mock_git.update_submodules.assert_not_called()


class TestUpdateWorkspace:
    """update_workspace pulls all submodules to latest remote main."""

    @patch("amplifier_workspace.workspace._git")
    def test_calls_update_submodules(self, mock_git, tmp_path: Path):
        """update_workspace delegates to _git.update_submodules."""
        mock_git.is_git_repo.return_value = True
        update_workspace(tmp_path)
        mock_git.update_submodules.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace._git")
    def test_raises_if_not_a_git_repo(self, mock_git, tmp_path: Path):
        """update_workspace raises ValueError when workdir is not a git repo."""
        mock_git.is_git_repo.return_value = False
        with pytest.raises(ValueError, match="not a git repository"):
            update_workspace(tmp_path)


# ---------------------------------------------------------------------------
# WORKSPACE-MANIFEST.json scaffolding + destroy gate (both -d and -f)
# ---------------------------------------------------------------------------


class TestSetupWorkspaceCreatesManifest:
    """setup_workspace must scaffold WORKSPACE-MANIFEST.json idempotently."""

    @patch("amplifier_workspace.workspace._git")
    def test_creates_manifest_for_new_repo(self, mock_git, tmp_path: Path):
        """A fresh workspace gets an empty WORKSPACE-MANIFEST.json."""
        mock_git.is_git_repo.return_value = False
        config = WorkspaceConfig(default_repos=[])
        setup_workspace(tmp_path, config)
        assert (tmp_path / "WORKSPACE-MANIFEST.json").exists()

    @patch("amplifier_workspace.workspace._git")
    def test_creates_manifest_for_existing_repo(self, mock_git, tmp_path: Path):
        """An existing workspace (predating this feature) also gets a manifest."""
        mock_git.is_git_repo.return_value = True
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        assert (tmp_path / "WORKSPACE-MANIFEST.json").exists()

    @patch("amplifier_workspace.workspace._git")
    def test_does_not_clobber_existing_manifest(self, mock_git, tmp_path: Path):
        """setup_workspace never overwrites a manifest that already has entries."""
        mock_git.is_git_repo.return_value = True
        _manifest_mod.add_resource(tmp_path, "dtu", "dtu-1")
        config = WorkspaceConfig()
        setup_workspace(tmp_path, config)
        data = _manifest_mod.load_manifest(tmp_path)
        assert len(data["resources"]) == 1


class TestRunWorkspaceManifestGate:
    """Destroy/fresh must gate on active WORKSPACE-MANIFEST.json resources (-d AND -f)."""

    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_refuses_when_active_resource_and_declined(
        self, mock_config_path, mock_load_config, mock_rmtree, tmp_path: Path, monkeypatch
    ):
        """-d with an active resource and a declined confirmation aborts before rmtree."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        _manifest_mod.add_resource(tmp_path, "dtu", "dtu-1")
        monkeypatch.setattr("builtins.input", lambda *_: "no")

        config = WorkspaceConfig()
        with pytest.raises(SystemExit):
            run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_not_called()

    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_proceeds_when_active_resource_and_confirmed(
        self, mock_config_path, mock_load_config, mock_rmtree, tmp_path: Path, monkeypatch
    ):
        """-d with an active resource proceeds once 'orphan' is typed."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        _manifest_mod.add_resource(tmp_path, "dtu", "dtu-1")
        monkeypatch.setattr("builtins.input", lambda *_: "orphan")

        config = WorkspaceConfig()
        run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_fresh_refuses_when_active_resource_and_declined(
        self,
        mock_config_path,
        mock_load_config,
        mock_rmtree,
        mock_setup,
        mock_launch,
        tmp_path: Path,
        monkeypatch,
    ):
        """-f (which previously had NO confirmation at all) now also gates on active resources."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        _manifest_mod.add_resource(tmp_path, "tmux", "sess-1")
        monkeypatch.setattr("builtins.input", lambda *_: "")

        config = WorkspaceConfig()
        with pytest.raises(SystemExit):
            run_workspace(tmp_path, config, fresh=True)
        mock_rmtree.assert_not_called()
        mock_setup.assert_not_called()

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_fresh_proceeds_when_active_resource_and_confirmed(
        self,
        mock_config_path,
        mock_load_config,
        mock_rmtree,
        mock_setup,
        mock_launch,
        tmp_path: Path,
        monkeypatch,
    ):
        """-f proceeds once 'orphan' is typed."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        _manifest_mod.add_resource(tmp_path, "tmux", "sess-1")
        monkeypatch.setattr("builtins.input", lambda *_: "orphan")

        config = WorkspaceConfig()
        run_workspace(tmp_path, config, fresh=True)
        mock_rmtree.assert_called_once_with(tmp_path)

    @patch("amplifier_workspace.workspace._launch_amplifier")
    @patch("amplifier_workspace.workspace.setup_workspace")
    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_fresh_proceeds_without_prompt_when_all_reaped(
        self,
        mock_config_path,
        mock_load_config,
        mock_rmtree,
        mock_setup,
        mock_launch,
        tmp_path: Path,
        monkeypatch,
    ):
        """-f keeps its existing no-confirm behavior once every resource is reaped."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        _manifest_mod.add_resource(tmp_path, "tmux", "sess-1")
        _manifest_mod.reap_resource(tmp_path, "sess-1")

        prompted = {"called": False}
        monkeypatch.setattr(
            "builtins.input", lambda *_: prompted.update(called=True) or ""
        )

        config = WorkspaceConfig()
        run_workspace(tmp_path, config, fresh=True)
        mock_rmtree.assert_called_once_with(tmp_path)
        assert prompted["called"] is False

    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_proceeds_without_prompt_when_manifest_absent(
        self, mock_config_path, mock_load_config, mock_rmtree, tmp_path: Path, monkeypatch
    ):
        """-d keeps its existing (no additional prompt) behavior with no manifest present."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()

        prompted = {"called": False}
        monkeypatch.setattr(
            "builtins.input", lambda *_: prompted.update(called=True) or ""
        )

        config = WorkspaceConfig()
        run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_called_once_with(tmp_path)
        assert prompted["called"] is False

    @patch("amplifier_workspace.workspace.shutil.rmtree")
    @patch("amplifier_workspace.config.load_config")
    @patch("amplifier_workspace.config_manager.CONFIG_PATH")
    def test_destroy_requires_confirmation_on_corrupt_manifest(
        self, mock_config_path, mock_load_config, mock_rmtree, tmp_path: Path, monkeypatch
    ):
        """A corrupt WORKSPACE-MANIFEST.json requires the same 'orphan' confirmation."""
        mock_config_path.exists.return_value = True
        mock_load_config.return_value = WorkspaceConfig()
        (tmp_path / "WORKSPACE-MANIFEST.json").write_text("{not valid json")
        monkeypatch.setattr("builtins.input", lambda *_: "no")

        config = WorkspaceConfig()
        with pytest.raises(SystemExit):
            run_workspace(tmp_path, config, destroy=True)
        mock_rmtree.assert_not_called()
