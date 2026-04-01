"""Tests for tmux.py: session_name_from_path, session_exists, kill_session, and rcfile helpers."""

import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

from amplifier_workspace.config import TmuxConfig
from amplifier_workspace.tmux import (
    SESSION_NAME_MAX,
    _main_rcfile_content,
    _shell_rcfile_content,
    _window_rcfile_content,
    _write_rcfiles,
    create_session,
    kill_session,
    session_exists,
    session_name_from_path,
)


class TestSessionNameFromPath:
    def test_simple_name(self):
        """A simple directory name becomes the session name unchanged."""
        result = session_name_from_path(Path("/home/user/myproject"))
        assert result == "myproject"

    def test_trailing_slash(self):
        """A path with a trailing slash still derives the basename correctly."""
        result = session_name_from_path(Path("/home/user/myproject/"))
        assert result == "myproject"

    def test_long_name_truncated_to_32(self):
        """A name longer than SESSION_NAME_MAX (32) is truncated to exactly 32 chars."""
        long_name = "a" * 50
        result = session_name_from_path(Path(f"/home/user/{long_name}"))
        assert len(result) == SESSION_NAME_MAX
        assert result == "a" * SESSION_NAME_MAX

    def test_spaces_replaced(self):
        """Spaces in directory name are replaced with dashes."""
        result = session_name_from_path(Path("/home/user/my project"))
        assert result == "my-project"

    def test_colons_replaced(self):
        """Colons in directory name are replaced with dashes."""
        result = session_name_from_path(Path("/home/user/my:project"))
        assert result == "my-project"

    def test_dots_replaced(self):
        """Dots in directory name are replaced with dashes."""
        result = session_name_from_path(Path("/home/user/my.project"))
        assert result == "my-project"

    def test_returns_string(self):
        """The return type is always str."""
        result = session_name_from_path(Path("/some/path"))
        assert isinstance(result, str)


class TestSessionExists:
    def test_returns_true_when_session_exists(self):
        """Returns True when tmux has-session returns returncode 0."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = session_exists("my-session")
        assert result is True
        mock_run.assert_called_once()

    def test_returns_false_when_session_missing(self):
        """Returns False when tmux has-session returns non-zero returncode."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = session_exists("nonexistent-session")
        assert result is False
        mock_run.assert_called_once()

    def test_passes_name_exactly(self):
        """The session name is passed exactly to the tmux command."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            session_exists("exact-name-123")
        call_args = mock_run.call_args
        cmd = call_args.args[0]  # first positional argument is the command list
        assert "exact-name-123" in cmd


class TestKillSession:
    def test_kills_existing_session(self):
        """Calls tmux kill-session when session_exists returns True."""
        with (
            patch("amplifier_workspace.tmux.session_exists", return_value=True),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            kill_session("my-session")
        mock_run.assert_called_once()

    def test_noop_when_session_missing(self):
        """Does not call subprocess.run when session_exists returns False."""
        with (
            patch("amplifier_workspace.tmux.session_exists", return_value=False),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            kill_session("nonexistent-session")
        mock_run.assert_not_called()

    def test_passes_name_to_kill_command(self):
        """The session name is passed to the tmux kill-session command."""
        with (
            patch("amplifier_workspace.tmux.session_exists", return_value=True),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            kill_session("my-named-session")
        call_args = mock_run.call_args
        cmd = call_args.args[0]  # first positional argument is the command list
        assert "my-named-session" in cmd
        assert "kill-session" in cmd


class TestMainRcfileContent:
    def test_sources_bashrc(self):
        """The main rcfile sources ~/.bashrc."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "source ~/.bashrc" in result

    def test_cds_to_workdir(self):
        """The main rcfile cds to the given workdir."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "cd /some/path" in result

    def test_has_sleep_05(self):
        """The main rcfile includes sleep 0.5 for terminal settling."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "sleep 0.5" in result

    def test_checks_amplifier_session_list(self):
        """The main rcfile checks for existing Amplifier sessions via 'amplifier session list'."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "amplifier session list" in result
        # The command must appear inside an 'if' conditional block, not as a standalone call
        lines = result.splitlines()
        assert any(
            line.startswith("if ") and "amplifier session list" in line
            for line in lines
        )

    def test_exec_amplifier_resume_when_sessions_found(self):
        """The main rcfile runs 'exec amplifier resume' when sessions are found."""
        result = _main_rcfile_content(Path("/some/path"))
        lines = result.splitlines()
        assert any(line.strip() == "exec amplifier resume" for line in lines)

    def test_exec_amplifier_when_no_sessions(self):
        """The main rcfile runs bare 'exec amplifier' in the else branch."""
        result = _main_rcfile_content(Path("/some/path"))
        lines = result.splitlines()
        assert any(line.strip() == "exec amplifier" for line in lines)

    def test_workdir_with_spaces_is_quoted(self):
        """Workdir paths containing spaces are safely quoted via shlex.quote."""
        result = _main_rcfile_content(Path("/path/with spaces/project"))
        # shlex.quote wraps in single quotes when the path contains spaces
        assert "'/path/with spaces/project'" in result


class TestShellRcfileContent:
    def test_sources_bashrc(self):
        """The shell rcfile sources ~/.bashrc."""
        result = _shell_rcfile_content(Path("/some/path"))
        assert "source ~/.bashrc" in result

    def test_cds_to_workdir(self):
        """The shell rcfile cds to the given workdir."""
        result = _shell_rcfile_content(Path("/some/path"))
        assert "cd /some/path" in result

    def test_no_exec_command(self):
        """The shell rcfile does not contain any exec command (drops to interactive bash)."""
        result = _shell_rcfile_content(Path("/some/path"))
        assert "exec " not in result


class TestWindowRcfileContent:
    def test_sources_bashrc(self):
        """The window rcfile sources ~/.bashrc."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "source ~/.bashrc" in result

    def test_cds_to_workdir(self):
        """The window rcfile cds to the given workdir."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "cd /some/path" in result

    def test_has_sleep_03(self):
        """The window rcfile includes sleep 0.3 for terminal settling."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "sleep 0.3" in result

    def test_execs_command(self):
        """The window rcfile execs the given command."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "exec lazygit" in result

    def test_command_with_args(self):
        """The window rcfile execs a command with arguments."""
        result = _window_rcfile_content(Path("/some/path"), "yazi /some/arg")
        assert "exec yazi /some/arg" in result


class TestWriteRcfiles:
    def test_creates_rcfile_dir(self, tmp_path):
        """_write_rcfiles creates the rcfile directory."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig()
        result = _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        assert rcfile_base.exists()
        assert result == rcfile_base

    def test_creates_amplifier_rc(self, tmp_path):
        """_write_rcfiles always creates amplifier.rc."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig()
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        assert (rcfile_base / "amplifier.rc").exists()

    def test_creates_shell_rc(self, tmp_path):
        """_write_rcfiles always creates shell.rc."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig()
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        assert (rcfile_base / "shell.rc").exists()

    def test_creates_tool_window_rcfile(self, tmp_path):
        """_write_rcfiles creates a {window_name}.rc for additional windows with commands."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig(
            windows={"amplifier": "", "shell": "", "lazygit": "lazygit"}
        )
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        assert (rcfile_base / "lazygit.rc").exists()

    def test_tool_rcfile_has_correct_command(self, tmp_path):
        """The tool window rcfile uses _window_rcfile_content with the correct command."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig(
            windows={"amplifier": "", "shell": "", "lazygit": "lazygit"}
        )
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        content = (rcfile_base / "lazygit.rc").read_text()
        assert "exec lazygit" in content

    def test_skips_windows_with_empty_command(self, tmp_path):
        """_write_rcfiles skips creating rcfiles for windows with empty commands."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig(windows={"amplifier": "", "shell": "", "nocommand": ""})
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        assert not (rcfile_base / "nocommand.rc").exists()

    def test_rcfiles_are_executable(self, tmp_path):
        """All written rcfiles have at least one execute bit set."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig(
            windows={"amplifier": "", "shell": "", "lazygit": "lazygit"}
        )
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        for rcfile in rcfile_base.iterdir():
            file_stat = rcfile.stat()
            assert file_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), (
                f"{rcfile.name} is not executable"
            )


class TestCreateSession:
    def test_creates_session_with_amplifier_window(self, tmp_path):
        """Creates new session with -d, -s, and -n amplifier flags."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        new_session_call = next(c for c in calls if "new-session" in c.args[0])
        cmd = new_session_call.args[0]
        assert "-d" in cmd
        assert "-s" in cmd
        assert "-n" in cmd
        assert "amplifier" in cmd

    def test_session_name_derived_from_workdir(self, tmp_path):
        """Session name is derived from workdir via session_name_from_path."""
        workdir = tmp_path / "my-project"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        new_session_call = next(c for c in calls if "new-session" in c.args[0])
        cmd = new_session_call.args[0]
        # -s is followed by the session name derived from workdir basename
        s_index = cmd.index("-s")
        assert cmd[s_index + 1] == "my-project"

    def test_uses_amplifier_rcfile_for_main_window(self, tmp_path):
        """Amplifier window shell command contains amplifier.rc and --rcfile."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        new_session_call = next(c for c in calls if "new-session" in c.args[0])
        cmd = new_session_call.args[0]
        # The shell command is the last element (exec bash --rcfile '...')
        shell_cmd = cmd[-1]
        assert "amplifier.rc" in shell_cmd
        assert "--rcfile" in shell_cmd

    def test_selects_amplifier_window_at_end(self, tmp_path):
        """Last subprocess call is select-window -t <name>:amplifier."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        last_cmd = calls[-1].args[0]
        assert "select-window" in last_cmd
        # Target must include <name>:amplifier
        assert any("amplifier" in arg and ":" in arg for arg in last_cmd)

    def test_calls_write_rcfiles_with_correct_args(self, tmp_path):
        """Calls _write_rcfiles(workdir, config) to generate rcfiles first."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run"),
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        mock_rcfiles.assert_called_once_with(workdir, config)

    def test_creates_tool_windows_in_order(self, tmp_path):
        """Tool windows from config.windows are created via new-window with correct name and rcfile."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(
            windows={"amplifier": "", "lazygit": "lazygit", "shell": ""}
        )
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        # Find the new-window call for the lazygit tool window
        tool_calls = [
            c for c in calls if "new-window" in c.args[0] and "lazygit" in c.args[0]
        ]
        assert len(tool_calls) == 1, "Expected exactly one new-window call for lazygit"
        cmd = tool_calls[0].args[0]
        # Must have -n lazygit
        assert "-n" in cmd
        n_index = cmd.index("-n")
        assert cmd[n_index + 1] == "lazygit"
        # Shell command must reference lazygit.rc
        shell_cmd = cmd[-1]
        assert "lazygit.rc" in shell_cmd
        assert "--rcfile" in shell_cmd
