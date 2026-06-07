"""Configuration dataclasses and loader for amplifier-workspace."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_PATH = Path.home() / ".config" / "amplifier-workspace" / "config.toml"

_DEFAULT_REPOS: list[str] = [
    "https://github.com/microsoft/amplifier.git",
    "https://github.com/microsoft/amplifier-core.git",
    "https://github.com/microsoft/amplifier-foundation.git",
]

# Public constants for use by wizard and other callers
DEFAULT_REPOS: list[str] = list(_DEFAULT_REPOS)
DEFAULT_BUNDLE: str = "amplifier-dev"

_DEFAULT_WINDOWS: dict[str, str] = {
    "amplifier": "",
    "shell": "",
}


@dataclass
class TmuxConfig:
    enabled: bool = False
    windows: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_WINDOWS))
    # Session-scoped mouse mode: enables scroll-wheel history and drag-select.
    # Applied via `tmux set-option -t <session>` so it never touches the user's
    # ~/.tmux.conf or any other running session. Requires tmux >= 2.1.
    mouse: bool = True
    # Session-scoped `set-clipboard on`: makes tmux's default MouseDragEnd
    # copy-and-cancel emit the selection to the terminal via OSC-52, fixing the
    # stuck copy-mode highlight and copying to the system clipboard on
    # OSC-52-capable terminals (iTerm2, kitty, wezterm, Ghostty, etc.).
    set_clipboard: bool = True
    # OPT-IN ONLY. Bind copy-mode MouseDragEnd to pipe the selection to an OS
    # clipboard tool (pbcopy/wl-copy/xclip/xsel) for terminals that lack OSC-52
    # (e.g. Apple Terminal.app). WARNING: tmux key bindings are server-global, so
    # this binding leaks into the user's other tmux sessions. Off by default.
    clipboard_binding: bool = False


@dataclass
class WorkspaceConfig:
    default_repos: list[str] = field(default_factory=lambda: list(_DEFAULT_REPOS))
    bundle: str = "amplifier-dev"
    agents_template: str = ""
    tmux: TmuxConfig = field(default_factory=TmuxConfig)


def _load_bundled_defaults() -> dict:
    """Load default-config.toml bundled with the package. Returns {} on failure.

    Reserved for future layered config loading (bundled-defaults → user-config →
    dataclass-defaults). Not yet wired into load_config().
    """
    try:
        pkg = (
            importlib.resources.files("amplifier_workspace")
            / "templates"
            / "default-config.toml"
        )
        data = pkg.read_bytes()
        return tomllib.loads(data.decode())
    except Exception:  # any resource/parse failure is non-fatal
        return {}


def _expand_path(path_str: str) -> str:
    """Expand ~ in path string. Returns empty string unchanged."""
    if not path_str:
        return path_str
    return str(Path(path_str).expanduser())


def load_config(config_path: Path | None = None) -> WorkspaceConfig:
    """Load WorkspaceConfig from a TOML file, falling back to defaults."""
    path = config_path if config_path is not None else CONFIG_PATH

    if not path.exists():
        return WorkspaceConfig()

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    workspace_section = data.get("workspace", {})
    tmux_section = data.get("tmux", {})
    tmux_windows = tmux_section.get("windows", dict(_DEFAULT_WINDOWS))

    agents_template = _expand_path(workspace_section.get("agents_template", ""))

    tmux_cfg = TmuxConfig(
        enabled=tmux_section.get("enabled", False),
        windows=tmux_windows,
        mouse=tmux_section.get("mouse", True),
        set_clipboard=tmux_section.get("set_clipboard", True),
        clipboard_binding=tmux_section.get("clipboard_binding", False),
    )

    return WorkspaceConfig(
        default_repos=workspace_section.get("default_repos", list(_DEFAULT_REPOS)),
        bundle=workspace_section.get("bundle", "amplifier-dev"),
        agents_template=agents_template,
        tmux=tmux_cfg,
    )
