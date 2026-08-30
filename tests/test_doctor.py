"""Tests for doctor.py: _print_check helper and always-run health checks."""

import contextlib
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
        assert (
            "✓" in captured.out
            or "\033[32m" in captured.out
            or "\x1b[32m" in captured.out
        )

    def test_fail_contains_x_mark(self, capsys):
        """_print_check with passed=False outputs the failure symbol (✗) or red ANSI."""
        _print_check("git in PATH", False, "not found")
        captured = capsys.readouterr()
        # Should contain ✗ or red ANSI escape
        assert (
            "✗" in captured.out
            or "\033[31m" in captured.out
            or "\x1b[31m" in captured.out
        )

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

    def _apply_patches(self, params):
        """Return a contextlib.ExitStack with all standard doctor patches applied."""
        stack = contextlib.ExitStack()
        stack.enter_context(
            patch(
                "amplifier_workspace.doctor._get_install_info_for_doctor",
                return_value=params["install_info"],
            )
        )
        stack.enter_context(
            patch(
                "amplifier_workspace.doctor._check_for_update_doctor",
                return_value=params["update_result"],
            )
        )
        stack.enter_context(
            patch(
                "amplifier_workspace.doctor.shutil.which",
                side_effect=params["which_side_effect"],
            )
        )
        stack.enter_context(
            patch(
                "amplifier_workspace.doctor.load_config",
                return_value=params["mock_config"],
            )
        )
        stack.enter_context(
            patch(
                "amplifier_workspace.doctor.CONFIG_PATH",
                params["mock_config_path"],
            )
        )
        return stack

    def test_prints_python_version(self, capsys):
        """run_doctor prints Python version information."""
        params = self._default_patches()

        with self._apply_patches(params):
            run_doctor()

        captured = capsys.readouterr()
        # Should mention Python or version info
        assert "python" in captured.out.lower() or "3." in captured.out

    def test_passes_when_git_found(self, capsys):
        """run_doctor returns 0 (all pass) when git is found in PATH."""
        params = self._default_patches(git_available=True)

        with self._apply_patches(params):
            exit_code = run_doctor()

        assert exit_code == 0

    def test_fails_when_git_missing(self, capsys):
        """run_doctor returns 1 when git is not found in PATH."""
        params = self._default_patches(git_available=False)

        with self._apply_patches(params):
            exit_code = run_doctor()

        assert exit_code == 1

    def test_returns_zero_when_all_pass(self, capsys):
        """run_doctor returns 0 when all required checks pass."""
        params = self._default_patches(
            git_available=True,
            amplifier_available=True,
            config_exists=True,
        )

        with self._apply_patches(params):
            exit_code = run_doctor()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "all checks passed" in captured.out.lower()

    def test_fails_when_config_missing(self, capsys):
        """run_doctor returns 1 when config file does not exist."""
        params = self._default_patches(config_exists=False)

        with self._apply_patches(params):
            exit_code = run_doctor()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "setup" in captured.out.lower()

    def test_agents_template_fails_when_file_missing(self, capsys):
        """run_doctor returns 1 when agents_template is set but file doesn't exist."""
        params = self._default_patches(agents_template="/nonexistent/template.yaml")

        with self._apply_patches(params):
            exit_code = run_doctor()

        assert exit_code == 1

    def test_update_warning_does_not_cause_failure(self, capsys):
        """run_doctor returns 0 even when an update is available (warning only)."""
        params = self._default_patches()
        params["update_result"] = (True, "update available (abcd1234 → efgh5678)")

        with self._apply_patches(params):
            exit_code = run_doctor()

        assert exit_code == 0

    def test_tmux_check_shown_as_skipped_when_disabled(self, capsys):
        """run_doctor shows tmux check as skipped when tmux.enabled is False."""
        params = self._default_patches()

        with self._apply_patches(params):
            run_doctor()

        captured = capsys.readouterr()
        # tmux section should appear and show skipped
        assert "tmux" in captured.out.lower()
        assert "skipped" in captured.out.lower()


# ── Module-level helper for tmux-config-based tests ───────────────────────────


def _doctor_with_tmux_config(config, which_fn, capsys):
    """Run run_doctor with a given config mock and which function.

    Returns (exit_code, captured) tuple.
    """
    mock_config_path = MagicMock(spec=Path)
    mock_config_path.exists.return_value = True

    with (
        patch(
            "amplifier_workspace.doctor._get_install_info_for_doctor",
            return_value=_SAMPLE_INSTALL_INFO,
        ),
        patch(
            "amplifier_workspace.doctor._check_for_update_doctor",
            return_value=(False, "up to date"),
        ),
        patch(
            "amplifier_workspace.doctor.shutil.which",
            side_effect=which_fn,
        ),
        patch(
            "amplifier_workspace.doctor.load_config",
            return_value=config,
        ),
        patch(
            "amplifier_workspace.doctor.CONFIG_PATH",
            mock_config_path,
        ),
    ):
        exit_code = run_doctor()
        captured = capsys.readouterr()
    return exit_code, captured


class TestTmuxChecks:
    """Tests for tmux-conditional doctor checks (Task 7)."""

    def test_doctor_tmux_enabled_checks_tmux_binary(self, capsys):
        """When tmux.enabled=True, run_doctor checks the tmux binary."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {}

        which_fn = _make_which({"git", "amplifier", "tmux"})

        with patch(
            "amplifier_workspace.doctor.subprocess.run",
            return_value=MagicMock(stdout="tmux 3.3a\n"),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert "tmux" in captured.out.lower()
        assert "3.3a" in captured.out
        assert exit_code == 0

    def test_doctor_tmux_enabled_missing_tool_fails(self, capsys):
        """When tmux.windows has lazygit but it's missing, run_doctor fails."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {"lazygit": "lazygit"}

        # tmux itself is found; lazygit is NOT
        which_fn = _make_which({"git", "amplifier", "tmux"})

        with (
            patch(
                "amplifier_workspace.doctor.subprocess.run",
                return_value=MagicMock(stdout="tmux 3.3a\n"),
            ),
            patch("amplifier_workspace.doctor.get_install_hint", return_value=None),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert "lazygit" in captured.out
        assert exit_code == 1

    def test_doctor_tmux_disabled_shows_skipped(self, capsys):
        """When tmux.enabled=False, run_doctor shows tmux as skipped."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = False

        which_fn = _make_which({"git", "amplifier"})

        exit_code, captured = _doctor_with_tmux_config(mock_config, which_fn, capsys)

        assert "skip" in captured.out.lower()

    def test_doctor_summary_all_pass_exits_0(self, capsys):
        """Full passing config: 'All checks passed' and exit_code==0."""
        mock_config = MagicMock()
        mock_config.default_repos = ["https://github.com/example/repo.git"]
        mock_config.agents_template = ""
        mock_config.tmux.enabled = False

        which_fn = _make_which({"git", "amplifier"})

        exit_code, captured = _doctor_with_tmux_config(mock_config, which_fn, capsys)

        assert "all checks passed" in captured.out.lower()
        assert exit_code == 0

    def test_doctor_summary_with_failures(self, capsys):
        """When git and amplifier are missing, 'issue' in output and exit_code==1."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = False

        which_fn = _make_which(set())  # neither git nor amplifier

        exit_code, captured = _doctor_with_tmux_config(mock_config, which_fn, capsys)

        assert "issue" in captured.out.lower()
        assert exit_code == 1


class TestDoctorTmuxChecks:
    """Tests for tmux-aware doctor checks (task-12)."""

    def test_tmux_check_runs_when_enabled(self, capsys):
        """When tmux.enabled=True and tmux found, output contains 'tmux'."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {}

        which_fn = _make_which({"git", "amplifier", "tmux"})

        with patch(
            "amplifier_workspace.doctor.subprocess.run",
            return_value=MagicMock(stdout="tmux 3.3a\n"),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert "tmux" in captured.out.lower()
        assert exit_code == 0

    def test_tmux_skipped_when_disabled(self, capsys):
        """When tmux.enabled=False, output contains 'skipped' or 'not enabled'."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = False

        which_fn = _make_which({"git", "amplifier"})

        exit_code, captured = _doctor_with_tmux_config(mock_config, which_fn, capsys)

        assert (
            "skipped" in captured.out.lower() or "not enabled" in captured.out.lower()
        )

    def test_tmux_not_found_is_failure(self, capsys):
        """When tmux.enabled=True but tmux binary not found, return code != 0."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {}

        # tmux is NOT found
        which_fn = _make_which({"git", "amplifier"})

        with patch("amplifier_workspace.doctor.get_install_hint", return_value=None):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert exit_code != 0

    def test_tool_window_checked_when_configured(self, capsys):
        """When tmux.windows has lazygit, output contains 'lazygit'."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {"lazygit": "lazygit"}

        which_fn = _make_which({"git", "amplifier", "tmux", "lazygit"})

        with patch(
            "amplifier_workspace.doctor.subprocess.run",
            return_value=MagicMock(stdout="tmux 3.3a\n"),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert "lazygit" in captured.out
        assert exit_code == 0

    def test_missing_tool_window_is_failure(self, capsys):
        """When lazygit window configured but lazygit missing, return code != 0."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {"lazygit": "lazygit"}

        # tmux found, lazygit NOT found
        which_fn = _make_which({"git", "amplifier", "tmux"})

        with (
            patch(
                "amplifier_workspace.doctor.subprocess.run",
                return_value=MagicMock(stdout="tmux 3.3a\n"),
            ),
            patch("amplifier_workspace.doctor.get_install_hint", return_value=None),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert exit_code != 0

    def test_missing_tool_shows_install_hint(self, capsys):
        """When a window tool is missing, output contains 'config', 'remove', or 'install'."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {"lazygit": "lazygit"}

        # tmux found, lazygit NOT found
        which_fn = _make_which({"git", "amplifier", "tmux"})

        with (
            patch(
                "amplifier_workspace.doctor.subprocess.run",
                return_value=MagicMock(stdout="tmux 3.3a\n"),
            ),
            patch(
                "amplifier_workspace.doctor.get_install_hint",
                return_value="brew install lazygit",
            ),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        # Must contain at least one of: 'config', 'remove', 'install'
        assert any(kw in captured.out.lower() for kw in ("config", "remove", "install"))

    def test_windows_with_empty_command_not_checked(self, capsys):
        """Windows with empty command string do not cause failures."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {"empty_window": ""}

        which_fn = _make_which({"git", "amplifier", "tmux"})

        with patch(
            "amplifier_workspace.doctor.subprocess.run",
            return_value=MagicMock(stdout="tmux 3.3a\n"),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert exit_code == 0

    def test_get_version_helper_exists(self):
        """_get_version helper function must exist and be callable in doctor module."""
        import amplifier_workspace.doctor as doctor_mod

        assert hasattr(doctor_mod, "_get_version"), (
            "_get_version helper not found in doctor.py"
        )
        assert callable(doctor_mod._get_version), "_get_version must be callable"

    def test_window_count_reported(self, capsys):
        """When tmux is enabled with multiple windows, output includes a count."""
        mock_config = MagicMock()
        mock_config.default_repos = []
        mock_config.agents_template = ""
        mock_config.tmux.enabled = True
        mock_config.tmux.windows = {"lazygit": "lazygit", "yazi": "yazi"}

        which_fn = _make_which({"git", "amplifier", "tmux", "lazygit", "yazi"})

        with patch(
            "amplifier_workspace.doctor.subprocess.run",
            return_value=MagicMock(stdout="tmux 3.3a\n"),
        ):
            exit_code, captured = _doctor_with_tmux_config(
                mock_config, which_fn, capsys
            )

        assert exit_code == 0
        # Output must report window count (e.g. "2 window(s) configured")
        assert "2 window" in captured.out


# ---------------------------------------------------------------------------
# Batch B — workspace-scoped checks + update-availability honesty
# ---------------------------------------------------------------------------


def _run_doctor_for_workspace(
    workdir, capsys, *, agents_template="", install_info=None
):
    """Run run_doctor(workdir) with all tool/config externals patched.

    git + amplifier are 'found' and config exists so that the only interesting
    output is the workspace-scoped section. Returns (exit_code, captured).
    """
    mock_config = MagicMock()
    mock_config.default_repos = []
    mock_config.agents_template = agents_template
    mock_config.tmux.enabled = False

    mock_config_path = MagicMock(spec=Path)
    mock_config_path.exists.return_value = True

    info = install_info if install_info is not None else _SAMPLE_INSTALL_INFO

    with (
        patch(
            "amplifier_workspace.doctor._get_install_info_for_doctor",
            return_value=info,
        ),
        patch(
            "amplifier_workspace.doctor._check_for_update_doctor",
            return_value=(False, "up to date"),
        ),
        patch(
            "amplifier_workspace.doctor.shutil.which",
            side_effect=_make_which({"git", "amplifier"}),
        ),
        patch("amplifier_workspace.doctor.load_config", return_value=mock_config),
        patch("amplifier_workspace.doctor.CONFIG_PATH", mock_config_path),
    ):
        exit_code = run_doctor(workdir)
        captured = capsys.readouterr()
    return exit_code, captured


def _make_older_workspace(root: Path) -> Path:
    """A workspace with AGENTS.md + settings but NO manifest (pre-manifest scaffold)."""
    ws = root / "ws"
    (ws / ".amplifier").mkdir(parents=True)
    (ws / ".amplifier" / "settings.yaml").write_text("bundle:\n  active: x\n")
    (ws / "AGENTS.md").write_text("# local edits\n")
    return ws


class TestDoctorWorkspaceChecks:
    def test_manifest_absent_warns_not_found(self, tmp_path, capsys):
        """A workspace without WORKSPACE-MANIFEST.json warns (does not fail)."""
        ws = _make_older_workspace(tmp_path)
        exit_code, captured = _run_doctor_for_workspace(ws, capsys)
        assert "WORKSPACE-MANIFEST.json" in captured.out
        assert "not found" in captured.out
        assert exit_code == 0  # a missing manifest is a warning, not a failure

    def test_manifest_active_resources_listed(self, tmp_path, capsys):
        """Active resources are listed with a 'gate destroy' reminder."""
        from amplifier_workspace import manifest

        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "AGENTS.md").write_text("x\n")
        manifest.add_resource(ws, "dtu", "dtu-123", note="env")

        exit_code, captured = _run_doctor_for_workspace(ws, capsys)
        assert "1 active" in captured.out
        assert "dtu-123" in captured.out
        assert "gate destroy" in captured.out
        assert exit_code == 0

    def test_manifest_all_reaped_passes(self, tmp_path, capsys):
        """A manifest whose resources are all reaped reports 0 active and passes."""
        from amplifier_workspace import manifest

        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "AGENTS.md").write_text("x\n")
        manifest.add_resource(ws, "dtu", "dtu-123")
        manifest.reap_resource(ws, "dtu-123")

        exit_code, captured = _run_doctor_for_workspace(ws, capsys)
        assert "0 active" in captured.out
        assert exit_code == 0

    def test_corrupt_manifest_is_a_failure(self, tmp_path, capsys):
        """An unparseable manifest is a doctor failure (exit 1) with a remedy."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "AGENTS.md").write_text("x\n")
        (ws / "WORKSPACE-MANIFEST.json").write_text("{bad json")

        exit_code, captured = _run_doctor_for_workspace(ws, capsys)
        assert "unparseable" in captured.out.lower()
        assert exit_code == 1

    def test_template_drift_warns(self, tmp_path, capsys):
        """A workspace AGENTS.md that differs from the packaged template warns."""
        ws = _make_older_workspace(tmp_path)  # AGENTS.md = "# local edits\n"
        exit_code, captured = _run_doctor_for_workspace(ws, capsys)
        assert "AGENTS.md differs from the packaged template" in captured.out
        assert exit_code == 0

    def test_template_match_passes(self, tmp_path, capsys):
        """A workspace AGENTS.md identical to the packaged template passes cleanly."""
        from amplifier_workspace.doctor import _packaged_agents_md

        packaged = _packaged_agents_md()
        assert packaged is not None
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "AGENTS.md").write_bytes(packaged)

        exit_code, captured = _run_doctor_for_workspace(ws, capsys)
        assert "matches packaged" in captured.out
        assert exit_code == 0

    def test_custom_template_skips_drift_check(self, tmp_path, capsys):
        """When a custom agents_template is configured, drift is not flagged."""
        ws = _make_older_workspace(tmp_path)  # differs from packaged
        # Point at a real custom template so the pre-existing agents_template
        # validity check passes and we isolate the drift behavior.
        custom = tmp_path / "custom-template.md"
        custom.write_text("# custom\n")
        exit_code, captured = _run_doctor_for_workspace(
            ws, capsys, agents_template=str(custom)
        )
        assert "differs from the packaged template" not in captured.out
        assert exit_code == 0

    def test_non_workspace_dir_has_no_workspace_section(self, tmp_path, capsys):
        """A plain directory (not a workspace) gets no workspace-scoped section."""
        plain = tmp_path / "plain"
        plain.mkdir()
        exit_code, captured = _run_doctor_for_workspace(plain, capsys)
        assert "workspace:" not in captured.out
        assert exit_code == 0


class TestDoctorUpdateHonesty:
    @pytest.mark.parametrize(
        "source,needle",
        [
            ("editable", "editable"),
            ("pypi", "pip/PyPI"),
            ("unknown", "unknown install source"),
        ],
    )
    def test_non_git_sources_are_not_checkable(self, tmp_path, capsys, source, needle):
        """editable/pypi/unknown never claim 'update available' — they say 'not checkable'."""
        info = {"source": source, "version": "1.0.0", "commit": None, "url": None}
        plain = tmp_path / "plain"
        plain.mkdir()
        _, captured = _run_doctor_for_workspace(plain, capsys, install_info=info)
        assert "not checkable" in captured.out
        assert "update available" not in captured.out
        assert needle in captured.out
