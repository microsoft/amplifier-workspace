"""Tests for tmux.py: session_name_from_path, session_exists, kill_session, and rcfile helpers."""

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from amplifier_workspace.config import TmuxConfig
from amplifier_workspace.tmux import (
    SESSION_NAME_MAX_FALLBACK,
    SessionNameEmptyError,
    SessionNameTooLongError,
    _main_rcfile_content,
    _shell_rcfile_content,
    _window_rcfile_content,
    _write_rcfiles,
    attach_session,
    create_session,
    kill_session,
    session_exists,
    session_name_from_path,
    session_name_max,
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

    def test_41_char_name_round_trips_uncut(self):
        """A 41-char basename survives whole -- the exact case the old 32 cap broke.

        Both names below are real directories in the reporting user's ~/dev, so
        the filesystem and tmux demonstrably accept them; only the hardcoded cap
        did not.
        """
        for long_name in (
            "context-intelligence-query-issues-team-ci",
            "amplifier-module-tool-document-builder-go",
        ):
            assert len(long_name) == 41
            result = session_name_from_path(Path(f"/home/user/{long_name}"))
            assert result == long_name, "41-char basename must not be truncated"

    def test_33_char_name_round_trips_uncut(self):
        """The reported symptom: '...-team-ci' at 33 chars lost its final 'i' at 32."""
        long_name = "home-assistant-smart-tool-team-ci"
        assert len(long_name) == 33
        result = session_name_from_path(Path(f"/home/user/{long_name}"))
        assert result == long_name
        assert not result.endswith("-"), "must not be cut mid-word leaving a dash"

    def test_name_up_to_filesystem_limit_is_kept_whole(self, tmp_path):
        """A name exactly at the filesystem's NAME_MAX is returned unchanged."""
        limit = session_name_max(tmp_path)
        long_name = "a" * limit
        result = session_name_from_path(tmp_path / long_name)
        assert result == long_name
        assert len(result.encode("utf-8")) == limit

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


class TestSessionNameMax:
    """The cap must be DERIVED from the filesystem, not a hardcoded literal."""

    def test_matches_filesystem_pathconf(self, tmp_path):
        """session_name_max reports the filesystem's own PC_NAME_MAX."""
        assert session_name_max(tmp_path) == os.pathconf(tmp_path, "PC_NAME_MAX")

    def test_derived_value_is_not_the_fallback_literal_by_luck(self, tmp_path):
        """The value comes from pathconf, not from the fallback constant.

        Patch pathconf to a value that is deliberately NOT the fallback and
        confirm the function follows the filesystem rather than the literal.
        """
        with patch("amplifier_workspace.tmux.os.pathconf", return_value=143):
            assert session_name_max(tmp_path) == 143
        assert 143 != SESSION_NAME_MAX_FALLBACK

    def test_probes_nearest_existing_ancestor(self, tmp_path):
        """A not-yet-created workspace path resolves to its nearest existing parent."""
        missing = tmp_path / "does-not-exist" / "nor-this"
        with patch(
            "amplifier_workspace.tmux.os.pathconf", return_value=143
        ) as mock_pathconf:
            assert session_name_max(missing) == 143
        assert mock_pathconf.call_args.args[0] == tmp_path

    def test_falls_back_when_pathconf_unavailable(self, tmp_path):
        """No os.pathconf (Windows) -> documented fallback, not a crash."""
        with patch(
            "amplifier_workspace.tmux.os.pathconf",
            side_effect=AttributeError("no pathconf"),
        ):
            assert session_name_max(tmp_path) == SESSION_NAME_MAX_FALLBACK

    def test_falls_back_when_pathconf_errors(self, tmp_path):
        """An OSError from pathconf falls back rather than propagating."""
        with patch("amplifier_workspace.tmux.os.pathconf", side_effect=OSError("nope")):
            assert session_name_max(tmp_path) == SESSION_NAME_MAX_FALLBACK

    def test_falls_back_when_limit_is_indeterminate(self, tmp_path):
        """pathconf returning -1 (indeterminate) falls back."""
        with patch("amplifier_workspace.tmux.os.pathconf", return_value=-1):
            assert session_name_max(tmp_path) == SESSION_NAME_MAX_FALLBACK

    def test_falls_back_with_no_path(self):
        """Called with no path there is nothing to probe -- use the fallback."""
        assert session_name_max() == SESSION_NAME_MAX_FALLBACK

    def test_fallback_is_255(self):
        """The documented fallback is the ext4/APFS/NTFS component limit."""
        assert SESSION_NAME_MAX_FALLBACK == 255


class TestSessionNameByteLimit:
    """NAME_MAX counts BYTES. A character-based check would be wrong."""

    # 3 bytes each in UTF-8. 85 chars = 255 bytes (fits ext4); 86 = 258 (does not).
    CJK = "\u4e2d"

    def test_multibyte_name_at_exact_byte_limit_is_accepted(self):
        """85 CJK chars == 255 bytes: right at the limit, kept whole."""
        name = self.CJK * 85
        assert len(name.encode("utf-8")) == 255
        result = session_name_from_path(Path(f"/home/user/{name}"), name_max=255)
        assert result == name

    def test_multibyte_name_over_byte_limit_is_rejected(self):
        """86 CJK chars == 258 bytes: over the limit even though 86 < 255 chars.

        This is the test that a character-based check would wrongly pass.
        """
        name = self.CJK * 86
        assert len(name) == 86, "character count alone would look fine (86 < 255)"
        assert len(name.encode("utf-8")) == 258, "but the byte count is over 255"
        with pytest.raises(SessionNameTooLongError):
            session_name_from_path(Path(f"/home/user/{name}"), name_max=255)

    def test_multibyte_name_matches_real_filesystem_behaviour(self, tmp_path):
        """The accept/reject boundary matches what the filesystem actually does."""
        limit = session_name_max(tmp_path)
        fits = self.CJK * (limit // 3)
        (tmp_path / fits).mkdir()  # the filesystem agrees this fits
        assert session_name_from_path(tmp_path / fits) == fits

        over = self.CJK * (limit // 3 + 1)
        with pytest.raises(OSError):
            (tmp_path / over).mkdir()  # the filesystem agrees this does not
        with pytest.raises(SessionNameTooLongError):
            session_name_from_path(tmp_path / over)

    def test_accepted_name_is_never_split_mid_character(self):
        """Whatever comes back is always decodable -- no partial codepoints.

        Nothing is truncated, so this holds by construction; the test pins the
        property so a future truncation cannot reintroduce a broken filename.
        """
        name = self.CJK * 85
        result = session_name_from_path(Path(f"/home/user/{name}"), name_max=255)
        assert result.encode("utf-8").decode("utf-8") == result

    def test_ascii_boundary_exact_and_over(self):
        """ASCII at the cap is accepted; one byte over is rejected."""
        assert session_name_from_path(Path("/home/user/" + "a" * 255), name_max=255)
        with pytest.raises(SessionNameTooLongError):
            session_name_from_path(Path("/home/user/" + "a" * 256), name_max=255)


class TestSessionNameOverLimitIsExplicit:
    """Over-limit fails loudly with an actionable message -- never a silent rename."""

    def test_raises_value_error_subclass(self):
        """SessionNameTooLongError is a ValueError, so existing handlers catch it."""
        assert issubclass(SessionNameTooLongError, ValueError)
        with pytest.raises(ValueError):
            session_name_from_path(Path("/home/user/" + "a" * 300), name_max=255)

    def test_message_names_the_size_the_limit_and_the_path(self):
        """The error tells the user what was too long, by how much, and where."""
        with pytest.raises(SessionNameTooLongError) as excinfo:
            session_name_from_path(Path("/home/user/" + "a" * 300), name_max=255)
        message = str(excinfo.value)
        assert "300 bytes" in message
        assert "255-byte" in message
        assert "NAME_MAX" in message
        assert "/home/user/" in message

    def test_does_not_return_a_truncated_name(self):
        """The old behaviour -- quietly returning a shorter name -- must not return."""
        long_path = Path("/home/user/" + "a" * 300)
        try:
            result = session_name_from_path(long_path, name_max=255)
        except SessionNameTooLongError:
            return  # correct: refused rather than renamed
        raise AssertionError(
            f"expected a loud refusal, got a silently different name: {result!r}"
        )


class TestSessionNameIsNeverEmpty:
    """A path must never yield '' -- tmux reads an empty name as another session.

    Measured on the reference host (2026-09-04, tmux 3.4, dedicated socket):
    `new-session -s ''` is rejected (rc=1), while `has-session -t ''` returns 0
    and `kill-session -t ''` returns 0 *and kills the most recently used
    session*.  So an empty name is not inert -- it silently retargets.
    """

    def test_filesystem_root_raises(self):
        """`/` has no basename at all; it must refuse, not return ''."""
        with pytest.raises(SessionNameEmptyError):
            session_name_from_path(Path("/"))

    def test_dot_only_basename_raises(self, tmp_path):
        """A real directory literally named '...' sanitizes to nothing."""
        pathological = tmp_path / "..."
        pathological.mkdir()  # ext4/APFS both accept this name
        with pytest.raises(SessionNameEmptyError):
            session_name_from_path(pathological)

    @pytest.mark.parametrize(
        "basename",
        ["...", " ", "-", "--", ":", ":::", ". .", "- -", ".."],
    )
    def test_never_returns_the_empty_string(self, basename):
        """Every all-separator basename either names a session or refuses."""
        path = Path("/home/user") / basename
        try:
            result = session_name_from_path(path)
        except SessionNameEmptyError:
            return  # correct: refused loudly
        assert result != "", f"{basename!r} produced an empty session name"

    def test_error_is_a_value_error_and_names_the_path(self):
        """Same contract as SessionNameTooLongError: a ValueError the CLI prints."""
        assert issubclass(SessionNameEmptyError, ValueError)
        with pytest.raises(SessionNameEmptyError) as excinfo:
            session_name_from_path(Path("/home/user/..."))
        assert "/home/user/..." in str(excinfo.value)

    def test_dot_resolves_to_the_real_directory_name(self, tmp_path, monkeypatch):
        """'.' is positional, not nameless -- resolve it instead of refusing."""
        workdir = tmp_path / "myproject"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        assert session_name_from_path(Path(".")) == "myproject"

    def test_dotdot_resolves_to_the_parent_directory_name(self, tmp_path, monkeypatch):
        """'..' likewise names a real directory once resolved."""
        parent = tmp_path / "outerproject"
        child = parent / "inner"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        assert session_name_from_path(Path("..")) == "outerproject"

    def test_resolution_does_not_rename_an_ordinary_path(self, tmp_path):
        """Resolution is a last resort; a normal basename is untouched by it."""
        assert session_name_from_path(tmp_path / "plain-name") == "plain-name"

    def test_create_session_refuses_before_touching_tmux(self, tmp_path):
        """The create path fails on the name, not on a CalledProcessError."""
        pathological = tmp_path / "..."
        pathological.mkdir()
        with patch("subprocess.run") as mock_run:
            with pytest.raises(SessionNameEmptyError):
                create_session(pathological, TmuxConfig())
        mock_run.assert_not_called()


class TestEmptySessionNameNeverReachesTmux:
    """The guard on every function that takes a name, not just the derivation.

    `-t ''` is not "no session": it resolves to the most recently used one, so
    an empty name reaching tmux operates on -- or kills -- a bystander.
    """

    def test_session_exists_refuses_empty_name(self):
        with patch("subprocess.run") as mock_run:
            with pytest.raises(SessionNameEmptyError):
                session_exists("")
        mock_run.assert_not_called()

    def test_kill_session_refuses_empty_name(self):
        """The destructive case: kill-session -t '' kills an unrelated session."""
        with patch("subprocess.run") as mock_run:
            with pytest.raises(SessionNameEmptyError):
                kill_session("")
        mock_run.assert_not_called()

    def test_attach_session_refuses_empty_name(self):
        with patch("subprocess.run") as mock_run, patch("os.execvp") as mock_execvp:
            with pytest.raises(SessionNameEmptyError):
                attach_session("")
        mock_run.assert_not_called()
        mock_execvp.assert_not_called()

    def test_message_explains_the_retargeting(self):
        with pytest.raises(SessionNameEmptyError) as excinfo:
            kill_session("")
        assert "most recently used session" in str(excinfo.value)


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

    def test_shell_window_is_single_pane(self, tmp_path):
        """Shell window is a single pane — no split-window call."""
        workdir = tmp_path / "myproject"
        config = TmuxConfig(windows={"amplifier": "", "shell": ""})
        with (
            patch("amplifier_workspace.tmux._write_rcfiles") as mock_rcfiles,
            patch("amplifier_workspace.tmux.subprocess.run") as mock_run,
        ):
            mock_rcfiles.return_value = Path("/tmp/rcfiles")
            create_session(workdir, config)
        calls = mock_run.call_args_list
        split_calls = [c for c in calls if "split-window" in c.args[0]]
        assert len(split_calls) == 0, (
            "Expected no split-window calls — shell window should be a single pane"
        )

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
