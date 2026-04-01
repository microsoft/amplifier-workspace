"""Tests for tmux.py: session_name_from_path, session_exists, kill_session, and rcfile helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from amplifier_workspace.tmux import (
    SESSION_NAME_MAX,
    _main_rcfile_content,
    _shell_rcfile_content,
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
