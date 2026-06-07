"""Tests for tmux.py: session_name_from_path, session_exists, kill_session, and rcfile helpers."""

import os
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
    attach_session,
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
        """The main rcfile sources ~/.bashrc with stderr suppressed."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "source ~/.bashrc 2>/dev/null" in result

    def test_cds_to_workdir(self):
        """The main rcfile cds to the given workdir."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "cd /some/path" in result

    def test_has_sleep_05(self):
        """The main rcfile includes sleep 0.5 for terminal settling."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "sleep 0.5" in result

    def test_checks_amplifier_session_list(self):
        """The main rcfile captures 'amplifier session list' output to a variable."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "amplifier session list" in result
        # Output is captured to a variable, not piped directly into 'if'
        lines = result.splitlines()
        assert any(
            "session_output=" in line and "amplifier session list" in line
            for line in lines
        )

    def test_amplifier_resume_when_sessions_found(self):
        """The main rcfile runs 'amplifier resume' (no exec) when a Session ID is found."""
        result = _main_rcfile_content(Path("/some/path"))
        lines = result.splitlines()
        assert any(line.strip() == "amplifier resume" for line in lines)

    def test_amplifier_when_no_sessions(self):
        """The main rcfile runs bare 'amplifier' (no exec) in the no-sessions / fallback branches."""
        result = _main_rcfile_content(Path("/some/path"))
        lines = result.splitlines()
        assert any(line.strip() == "amplifier" for line in lines)

    def test_no_exec_in_amplifier_commands(self):
        """The main rcfile does NOT use 'exec amplifier' — bash must stay alive after amplifier exits."""
        result = _main_rcfile_content(Path("/some/path"))
        assert "exec amplifier" not in result

    def test_no_exec_bash_at_end(self):
        """The main rcfile does NOT end with 'exec bash' — matches the proven working pattern.

        The amplifier-cli-tools reference implementation does not use 'exec bash' at the
        end of the rcfile.  The window stays open because bash is still alive (no exec
        before amplifier), and when the rcfile finishes, bash drops to an interactive prompt.
        """
        result = _main_rcfile_content(Path("/some/path"))
        assert not result.rstrip("\n").endswith("exec bash"), (
            "rcfile must NOT end with 'exec bash' — it breaks the window-stays-open behavior"
        )

    def test_workdir_with_spaces_is_quoted(self):
        """Workdir paths containing spaces are safely quoted via shlex.quote."""
        result = _main_rcfile_content(Path("/path/with spaces/project"))
        # shlex.quote wraps in single quotes when the path contains spaces
        assert "'/path/with spaces/project'" in result


class TestShellRcfileContent:
    def test_sources_bashrc(self):
        """The shell rcfile sources ~/.bashrc with stderr suppressed."""
        result = _shell_rcfile_content(Path("/some/path"))
        assert "source ~/.bashrc 2>/dev/null" in result

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
        """The window rcfile sources ~/.bashrc with stderr suppressed."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "source ~/.bashrc 2>/dev/null" in result

    def test_cds_to_workdir(self):
        """The window rcfile cds to the given workdir."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "cd /some/path" in result

    def test_no_sleep(self):
        """The window rcfile does not include a sleep — matches working amplifier-cli-tools pattern."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "sleep" not in result

    def test_runs_command_without_exec(self):
        """The window rcfile runs the command without 'exec' — bash stays alive after the tool exits."""
        result = _window_rcfile_content(Path("/some/path"), "lazygit")
        assert "lazygit" in result
        assert "exec lazygit" not in result

    def test_command_with_args(self):
        """The window rcfile runs a command with arguments (no exec)."""
        result = _window_rcfile_content(Path("/some/path"), "yazi /some/arg")
        assert "yazi /some/arg" in result
        assert "exec yazi" not in result


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
        """The tool window rcfile uses _window_rcfile_content with the correct command (no exec)."""
        rcfile_base = tmp_path / "rcfiles"
        config = TmuxConfig(
            windows={"amplifier": "", "shell": "", "lazygit": "lazygit"}
        )
        _write_rcfiles(Path("/some/path"), config, rcfile_base=rcfile_base)
        content = (rcfile_base / "lazygit.rc").read_text()
        assert "lazygit" in content
        assert "exec lazygit" not in content

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


class TestCreateSessionWindows:
    def test_shell_window_created_before_tool_windows(self, tmp_path):
        """Shell new-window call appears before tool window new-window calls (amplifier→shell→tools)."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "git": "lazygit", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        # Find the positional index of the shell new-window call
        shell_call_pos = next(
            i
            for i, c in enumerate(calls)
            if "new-window" in c.args[0] and "shell" in c.args[0]
        )
        # Find the positional index of the git tool new-window call
        git_call_pos = next(
            i
            for i, c in enumerate(calls)
            if "new-window" in c.args[0] and "git" in c.args[0]
        )
        assert shell_call_pos < git_call_pos, (
            "Shell new-window should be called before tool window new-window"
        )

    def test_shell_window_gets_horizontal_split(self, tmp_path):
        """Shell window gets exactly one horizontal split via split-window -h."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        split_calls = [
            c for c in calls if "split-window" in c.args[0] and "-h" in c.args[0]
        ]
        assert len(split_calls) == 1, "Expected exactly one split-window -h call"

    def test_no_split_when_no_shell_window(self, tmp_path):
        """No split-window call when config has no shell window."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        split_calls = [c for c in calls if "split-window" in c.args[0]]
        assert len(split_calls) == 0, (
            "Expected no split-window calls when no shell window is configured"
        )

    def test_windows_with_empty_command_skipped(self, tmp_path):
        """Windows with empty command string are not created via new-window."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "nocommand": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        nocommand_calls = [
            c for c in calls if "new-window" in c.args[0] and "nocommand" in c.args[0]
        ]
        assert len(nocommand_calls) == 0, (
            "Window with empty command should not be created via new-window"
        )

    def test_tool_window_uses_named_rcfile(self, tmp_path):
        """Tool window new-window command references the window's named rcfile (e.g. git.rc)."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "git": "lazygit", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        git_calls = [
            c for c in calls if "new-window" in c.args[0] and "git" in c.args[0]
        ]
        assert len(git_calls) == 1, "Expected exactly one new-window call for git"
        cmd = git_calls[0].args[0]
        shell_cmd = cmd[-1]
        assert "git.rc" in shell_cmd, "Tool window should use git.rc as its rcfile"
        assert "--rcfile" in shell_cmd, "Tool window should use --rcfile flag"


class TestAttachSession:
    def test_attach_outside_tmux_uses_attach_session(self):
        """When TMUX env var is not set, calls execvp with 'attach-session' command."""
        env_without_tmux = {k: v for k, v in os.environ.items() if k != "TMUX"}
        with (
            patch("amplifier_workspace.tmux.os.execvp") as mock_execvp,
            patch.dict(os.environ, env_without_tmux, clear=True),
        ):
            attach_session("my-session")
        mock_execvp.assert_called_once()
        args = mock_execvp.call_args.args
        assert args[0] == "tmux"
        assert "attach-session" in args[1]

    def test_switch_client_inside_tmux(self):
        """When TMUX env var is set, calls execvp with 'switch-client' command."""
        with (
            patch("amplifier_workspace.tmux.os.execvp") as mock_execvp,
            patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,1234,0"}),
        ):
            attach_session("my-session")
        mock_execvp.assert_called_once()
        args = mock_execvp.call_args.args
        assert args[0] == "tmux"
        assert "switch-client" in args[1]

    def test_passes_session_name_correctly(self):
        """Session name is passed as the -t argument in both outside and inside tmux scenarios."""
        # Outside tmux
        env_without_tmux = {k: v for k, v in os.environ.items() if k != "TMUX"}
        with (
            patch("amplifier_workspace.tmux.os.execvp") as mock_execvp,
            patch.dict(os.environ, env_without_tmux, clear=True),
        ):
            attach_session("target-session")
        args_outside = mock_execvp.call_args.args
        cmd_outside = args_outside[1]
        t_index = cmd_outside.index("-t")
        assert cmd_outside[t_index + 1] == "target-session"

        # Inside tmux
        with (
            patch("amplifier_workspace.tmux.os.execvp") as mock_execvp,
            patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,1234,0"}),
        ):
            attach_session("target-session")
        args_inside = mock_execvp.call_args.args
        cmd_inside = args_inside[1]
        t_index = cmd_inside.index("-t")
        assert cmd_inside[t_index + 1] == "target-session"


def _set_option_cmds(mock_run):
    """Return the command lists for every `tmux set-option` call recorded."""
    return [
        c.args[0]
        for c in mock_run.call_args_list
        if len(c.args) and "set-option" in c.args[0]
    ]


class TestSessionScopedOptions:
    """Tests for session-scoped mouse + clipboard options (Task: tmux scroll/copy)."""

    def test_mouse_and_set_clipboard_applied_when_enabled(self, tmp_path):
        """create_session issues session-scoped `mouse on` and `set-clipboard on`."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""}, mouse=True, set_clipboard=True)
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        set_cmds = _set_option_cmds(mock_run)
        # mouse on, session-scoped to this session's name
        assert any(
            "mouse" in cmd and "on" in cmd and "-t" in cmd and "myproject" in cmd
            for cmd in set_cmds
        ), f"expected `set-option -t myproject mouse on`, got {set_cmds}"
        # set-clipboard on, session-scoped
        assert any(
            "set-clipboard" in cmd and "on" in cmd and "myproject" in cmd
            for cmd in set_cmds
        ), f"expected `set-option -t myproject set-clipboard on`, got {set_cmds}"

    def test_no_options_applied_when_flags_false(self, tmp_path):
        """When both flags are False, no `set-option` calls are issued."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""}, mouse=False, set_clipboard=False)
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        assert _set_option_cmds(mock_run) == []

    def test_mouse_only(self, tmp_path):
        """mouse=True, set_clipboard=False issues only the mouse option."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""}, mouse=True, set_clipboard=False)
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        set_cmds = _set_option_cmds(mock_run)
        assert any("mouse" in cmd for cmd in set_cmds)
        assert not any("set-clipboard" in cmd for cmd in set_cmds)

    def test_old_tmux_skips_mouse_but_keeps_clipboard(self, tmp_path):
        """On tmux < 2.1, `mouse on` is skipped but `set-clipboard on` still applies."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""}, mouse=True, set_clipboard=True)
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(2, 0)),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        set_cmds = _set_option_cmds(mock_run)
        assert not any("mouse" in cmd for cmd in set_cmds), (
            "mouse should be skipped on tmux < 2.1"
        )
        assert any("set-clipboard" in cmd for cmd in set_cmds)

    def test_unknown_tmux_version_still_applies_mouse(self, tmp_path):
        """When the tmux version can't be determined, mouse is applied (best effort)."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""}, mouse=True, set_clipboard=False)
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=None),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        assert any("mouse" in cmd for cmd in _set_option_cmds(mock_run))

    def test_set_option_failure_does_not_abort_session(self, tmp_path):
        """A failing set-option must not abort create_session — windows still complete."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""}, mouse=True, set_clipboard=True)

        def run_side_effect(cmd, *args, **kwargs):
            if "set-option" in cmd:
                raise OSError("simulated set-option failure")
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch(
                "amplifier_workspace.tmux.subprocess.run",
                side_effect=run_side_effect,
            ) as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            # Must not raise despite the set-option failure
            create_session(workdir, config)

        # The final select-window call must still have happened
        last_cmd = mock_run.call_args_list[-1].args[0]
        assert "select-window" in last_cmd

    def test_no_clipboard_binding_by_default(self, tmp_path):
        """clipboard_binding defaults off — no global `bind-key` calls are issued."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        bind_cmds = [
            c.args[0]
            for c in mock_run.call_args_list
            if len(c.args) and "bind-key" in c.args[0]
        ]
        assert bind_cmds == []

    def test_clipboard_binding_opt_in_issues_global_bindings(self, tmp_path):
        """With clipboard_binding=True and a resolvable tool, bind-key calls are issued."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(
            windows={"amplifier": ""},
            mouse=False,
            set_clipboard=False,
            clipboard_binding=True,
        )
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch(
                "amplifier_workspace.tmux._resolve_clipboard_command",
                return_value="pbcopy",
            ),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        bind_cmds = [
            c.args[0]
            for c in mock_run.call_args_list
            if len(c.args) and "bind-key" in c.args[0]
        ]
        assert bind_cmds, (
            "expected at least one bind-key call when clipboard_binding=True"
        )
        assert any("copy-mode-vi" in cmd for cmd in bind_cmds)
        assert all("pbcopy" in cmd for cmd in bind_cmds)

    def test_clipboard_binding_missing_tool_is_noop(self, tmp_path):
        """clipboard_binding=True but no clipboard tool found → no bind-key, no crash."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(
            windows={"amplifier": ""},
            clipboard_binding=True,
        )
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux._tmux_version", return_value=(3, 3)),
            patch(
                "amplifier_workspace.tmux._resolve_clipboard_command",
                return_value=None,
            ),
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)

        bind_cmds = [
            c.args[0]
            for c in mock_run.call_args_list
            if len(c.args) and "bind-key" in c.args[0]
        ]
        assert bind_cmds == []


class TestTmuxVersion:
    """Tests for the _tmux_version parser."""

    def test_parses_standard_version(self):
        from amplifier_workspace.tmux import _tmux_version

        with patch(
            "amplifier_workspace.tmux.subprocess.run",
            return_value=MagicMock(stdout="tmux 3.3a\n"),
        ):
            assert _tmux_version() == (3, 3)

    def test_parses_next_version(self):
        from amplifier_workspace.tmux import _tmux_version

        with patch(
            "amplifier_workspace.tmux.subprocess.run",
            return_value=MagicMock(stdout="tmux next-3.4\n"),
        ):
            assert _tmux_version() == (3, 4)

    def test_returns_none_on_failure(self):
        from amplifier_workspace.tmux import _tmux_version

        with patch(
            "amplifier_workspace.tmux.subprocess.run",
            side_effect=OSError("tmux missing"),
        ):
            assert _tmux_version() is None

    def test_returns_none_on_unparseable_output(self):
        from amplifier_workspace.tmux import _tmux_version

        with patch(
            "amplifier_workspace.tmux.subprocess.run",
            return_value=MagicMock(stdout="tmux unknown\n"),
        ):
            assert _tmux_version() is None


class TestResolveClipboardCommand:
    """Tests for cross-platform clipboard command resolution."""

    def test_prefers_pbcopy(self):
        from amplifier_workspace.tmux import _resolve_clipboard_command

        with patch(
            "amplifier_workspace.tmux.shutil.which",
            side_effect=lambda c: f"/usr/bin/{c}" if c == "pbcopy" else None,
        ):
            assert _resolve_clipboard_command() == "pbcopy"

    def test_falls_back_to_xclip(self):
        from amplifier_workspace.tmux import _resolve_clipboard_command

        available = {"xclip"}
        with patch(
            "amplifier_workspace.tmux.shutil.which",
            side_effect=lambda c: f"/usr/bin/{c}" if c in available else None,
        ):
            assert _resolve_clipboard_command() == "xclip -selection clipboard"

    def test_returns_none_when_nothing_available(self):
        from amplifier_workspace.tmux import _resolve_clipboard_command

        with patch("amplifier_workspace.tmux.shutil.which", return_value=None):
            assert _resolve_clipboard_command() is None
