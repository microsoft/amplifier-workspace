"""Tests for install.py: KNOWN_TOOLS registry, detect_package_manager, get_install_hint."""

import io
import json
import shutil
import stat
import tarfile
from unittest.mock import MagicMock, patch

from amplifier_workspace.install import (
    KNOWN_TOOLS,
    _install_lazygit_linux,
    detect_package_manager,
    get_install_hint,
    install_tool,
)


class TestKnownToolsRegistry:
    def test_known_tools_has_tmux(self):
        assert "tmux" in KNOWN_TOOLS

    def test_known_tools_has_lazygit(self):
        assert "lazygit" in KNOWN_TOOLS

    def test_known_tools_has_yazi(self):
        assert "yazi" in KNOWN_TOOLS

    def test_tmux_has_brew_entry(self):
        assert "brew" in KNOWN_TOOLS["tmux"]

    def test_tmux_has_apt_entry(self):
        assert "apt" in KNOWN_TOOLS["tmux"]

    def test_tmux_has_dnf_entry(self):
        assert "dnf" in KNOWN_TOOLS["tmux"]

    def test_tmux_has_winget_entry(self):
        assert "winget" in KNOWN_TOOLS["tmux"]

    def test_lazygit_has_github_fallback_with_jesseduffield(self):
        assert "github" in KNOWN_TOOLS["lazygit"]
        assert "jesseduffield/lazygit" in KNOWN_TOOLS["lazygit"]["github"]


class TestDetectPackageManager:
    def test_macos_with_brew_returns_brew(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", return_value="/usr/local/bin/brew"):
                result = detect_package_manager()
        assert result == "brew"

    def test_macos_without_brew_returns_none(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", return_value=None):
                result = detect_package_manager()
        assert result is None

    def test_linux_with_apt_returns_apt(self):
        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", return_value="/usr/bin/apt"):
                result = detect_package_manager()
        assert result == "apt"

    def test_linux_without_apt_but_with_dnf_returns_dnf(self):
        def which_side_effect(cmd):
            if cmd == "apt":
                return None
            if cmd == "dnf":
                return "/usr/bin/dnf"
            return None

        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", side_effect=which_side_effect):
                result = detect_package_manager()
        assert result == "dnf"

    def test_windows_with_winget_returns_winget(self):
        with patch("platform.system", return_value="Windows"):
            with patch("shutil.which", return_value="C:\\Windows\\winget.exe"):
                result = detect_package_manager()
        assert result == "winget"

    def test_unknown_platform_returns_none(self):
        with patch("platform.system", return_value="FreeBSD"):
            result = detect_package_manager()
        assert result is None


class TestGetInstallHint:
    def test_tmux_on_brew_returns_brew_install_tmux(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", return_value="/usr/local/bin/brew"):
                result = get_install_hint("tmux")
        assert result == "brew install tmux"

    def test_tmux_on_apt_returns_hint_containing_tmux(self):
        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", return_value="/usr/bin/apt"):
                result = get_install_hint("tmux")
        assert result is not None
        assert "tmux" in result

    def test_unknown_tool_returns_none(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", return_value="/usr/local/bin/brew"):
                result = get_install_hint("nonexistent_tool_xyz")
        assert result is None

    def test_no_package_manager_returns_none(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("shutil.which", return_value=None):
                result = get_install_hint("tmux")
        assert result is None


class TestInstallTool:
    def test_install_tool_uses_brew_on_macos(self):
        """install_tool builds ['brew', 'install', ...] when package manager is brew."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch(
            "amplifier_workspace.install.platform.system", return_value="Darwin"
        ):
            with patch(
                "amplifier_workspace.install.detect_package_manager",
                return_value="brew",
            ):
                with patch(
                    "amplifier_workspace.install.subprocess.run",
                    return_value=mock_result,
                ) as mock_run:
                    success, _ = install_tool("tmux")
        assert success
        call_args = mock_run.call_args.args[0]
        assert "brew" in call_args

    def test_apt_uses_sudo_when_available(self):
        """install_tool builds ['sudo', 'apt', 'install', ...] when sudo is present."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("amplifier_workspace.install.platform.system", return_value="Linux"):
            with patch(
                "amplifier_workspace.install.detect_package_manager", return_value="apt"
            ):
                with patch("amplifier_workspace.install._has_sudo", return_value=True):
                    with patch(
                        "amplifier_workspace.install.subprocess.run",
                        return_value=mock_result,
                    ) as mock_run:
                        success, _ = install_tool("tmux")
        assert success
        call_args = mock_run.call_args.args[0]
        assert "sudo" in call_args
        assert "apt" in call_args

    def test_apt_fails_without_sudo(self):
        """install_tool returns (False, ...) for apt when sudo is not available."""
        with patch("amplifier_workspace.install.platform.system", return_value="Linux"):
            with patch(
                "amplifier_workspace.install.detect_package_manager", return_value="apt"
            ):
                with patch("amplifier_workspace.install._has_sudo", return_value=False):
                    success, message = install_tool("tmux")
        assert not success
        assert "apt" in message.lower() or "sudo" in message.lower()

    def test_no_package_manager_returns_false_with_message(self):
        """install_tool returns (False, msg) when no package manager is found."""
        with patch(
            "amplifier_workspace.install.platform.system", return_value="Darwin"
        ):
            with patch(
                "amplifier_workspace.install.detect_package_manager", return_value=None
            ):
                success, message = install_tool("tmux")
        assert not success
        assert "package manager" in message.lower()

    def test_subprocess_failure_returns_false(self):
        """install_tool returns (False, ...) when subprocess exits with non-zero code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch(
            "amplifier_workspace.install.platform.system", return_value="Darwin"
        ):
            with patch(
                "amplifier_workspace.install.detect_package_manager",
                return_value="brew",
            ):
                with patch(
                    "amplifier_workspace.install.subprocess.run",
                    return_value=mock_result,
                ):
                    success, _ = install_tool("tmux")
        assert not success

    def test_yazi_on_linux_returns_manual_instructions(self):
        """install_tool returns manual install instructions for yazi on Linux."""
        with patch("amplifier_workspace.install.platform.system", return_value="Linux"):
            success, message = install_tool("yazi")
        assert not success
        msg_lower = message.lower()
        assert "yazi" in msg_lower or "cargo" in msg_lower or "manual" in msg_lower

    def test_lazygit_on_linux_routes_to_install_lazygit_linux(self):
        """install_tool delegates to _install_lazygit_linux() for lazygit on Linux."""
        with patch("amplifier_workspace.install.platform.system", return_value="Linux"):
            with patch(
                "amplifier_workspace.install._install_lazygit_linux",
                return_value=(True, "installed"),
            ) as mock_fn:
                result = install_tool("lazygit")
        mock_fn.assert_called_once()
        assert result == (True, "installed")


class TestInstallLazygitLinux:
    def test_install_lazygit_linux_installs_to_local_bin(self, tmp_path):
        """Creates real .tar.gz with fake lazygit binary, installs to ~/.local/bin."""
        fake_binary_content = b"#!/bin/sh\necho lazygit\n"
        tarball_path = tmp_path / "lazygit.tar.gz"
        with tarfile.open(str(tarball_path), "w:gz") as tf:
            info = tarfile.TarInfo(name="lazygit")
            info.size = len(fake_binary_content)
            info.mode = stat.S_IRWXU
            tf.addfile(info, io.BytesIO(fake_binary_content))

        fake_home = tmp_path / "home"
        fake_home.mkdir()

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "v0.40.0"}).encode()
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = MagicMock(return_value=False)

        def fake_urlretrieve(url, dest):
            shutil.copy(str(tarball_path), dest)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve):
                with patch("amplifier_workspace.install._has_sudo", return_value=False):
                    with patch(
                        "amplifier_workspace.install._get_arch", return_value="x86_64"
                    ):
                        with patch(
                            "amplifier_workspace.install.Path.home",
                            return_value=fake_home,
                        ):
                            success, _message = _install_lazygit_linux()

        assert success
        assert (fake_home / ".local" / "bin" / "lazygit").exists()

    def test_install_lazygit_linux_handles_api_error(self):
        """Returns (False, msg) when urlopen raises an exception."""
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with patch("amplifier_workspace.install._get_arch", return_value="x86_64"):
                success, message = _install_lazygit_linux()

        assert not success
        msg_lower = message.lower()
        assert "network error" in msg_lower or "failed" in msg_lower

    def test_install_lazygit_linux_rejects_unknown_arch(self):
        """Returns (False, msg) for unsupported architectures like mips."""
        with patch("amplifier_workspace.install._get_arch", return_value="mips"):
            success, message = _install_lazygit_linux()

        assert not success
        msg_lower = message.lower()
        assert "arch" in msg_lower or "unsupported" in msg_lower
