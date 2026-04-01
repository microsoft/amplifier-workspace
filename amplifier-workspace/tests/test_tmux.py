"""Tests for tmux.py: session_name_from_path and session_exists."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from amplifier_workspace.tmux import (
    SESSION_NAME_MAX,
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
        cmd = call_args[0][0]  # first positional argument is the command list
        assert "exact-name-123" in cmd
