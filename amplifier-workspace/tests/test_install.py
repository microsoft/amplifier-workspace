"""Tests for install.py: KNOWN_TOOLS registry, detect_package_manager, get_install_hint."""

from unittest.mock import patch

from amplifier_workspace.install import (
    KNOWN_TOOLS,
    detect_package_manager,
    get_install_hint,
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
