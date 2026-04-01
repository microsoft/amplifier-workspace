"""Install hints and package manager detection for workspace tools."""

import platform
import shutil

# Registry of known tools and their package names per package manager
KNOWN_TOOLS: dict[str, dict[str, str]] = {
    "tmux": {
        "brew": "tmux",
        "apt": "tmux",
        "dnf": "tmux",
        "winget": "Maborak.tmux",
    },
    "lazygit": {
        "brew": "lazygit",
        "winget": "JesseDuffield.lazygit",
        "github": "jesseduffield/lazygit",
    },
    "yazi": {
        "brew": "yazi",
        "winget": "sxyazi.yazi",
        "cargo": "yazi-fm",
        "github": "sxyazi/yazi",
    },
}


def detect_package_manager() -> str | None:
    """Return the active package manager name, or None if none detected.

    Priority order:
    - macOS: brew
    - Linux: apt first, then dnf
    - Windows: winget
    - Unknown platform: None
    """
    system = platform.system()
    if system == "Darwin":
        if shutil.which("brew"):
            return "brew"
        return None
    elif system == "Linux":
        if shutil.which("apt"):
            return "apt"
        if shutil.which("dnf"):
            return "dnf"
        return None
    elif system == "Windows":
        if shutil.which("winget"):
            return "winget"
        return None
    return None


def _has_sudo() -> bool:
    """Return True if sudo is available in PATH."""
    return shutil.which("sudo") is not None


def _get_arch() -> str:
    """Return system architecture string suitable for GitHub release downloads.

    Maps:
    - x86_64 / amd64 -> 'x86_64'
    - aarch64 / arm64 -> 'arm64'
    - anything else -> raw machine string
    """
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    return platform.machine()


def get_install_hint(command: str) -> str | None:
    """Return a human-readable install hint for command on the current platform.

    Returns None if:
    - command is not in KNOWN_TOOLS
    - no package manager is detected
    - the detected package manager has no entry for this command
    """
    if command not in KNOWN_TOOLS:
        return None

    pkg_manager = detect_package_manager()
    if pkg_manager is None:
        return None

    tool_info = KNOWN_TOOLS[command]
    if pkg_manager not in tool_info:
        return None

    pkg_name = tool_info[pkg_manager]

    if pkg_manager == "brew":
        return f"brew install {pkg_name}"
    elif pkg_manager == "apt":
        if _has_sudo():
            return f"sudo apt install {pkg_name}"
        return f"apt install {pkg_name}"
    elif pkg_manager == "dnf":
        if _has_sudo():
            return f"sudo dnf install {pkg_name}"
        return f"dnf install {pkg_name}"
    elif pkg_manager == "winget":
        return f"winget install {pkg_name}"

    return None
