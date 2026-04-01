"""Interactive setup wizard for amplifier-workspace."""

from __future__ import annotations

import shutil

from .config import DEFAULT_BUNDLE, DEFAULT_REPOS
from .config_manager import CONFIG_PATH, write_config


def _prompt(question: str, default: str = "") -> str:
    """Display *question* (with *default* in brackets) and return the answer.

    Returns the stripped user input, or *default* if the user pressed Enter
    without typing anything.  KeyboardInterrupt is NOT caught and will
    propagate to the caller.
    """
    if default:
        display = f"{question} [{default}]: "
    else:
        display = f"{question}: "
    answer = input(display)
    stripped = answer.strip()
    return stripped if stripped else default


def _prompt_bool(question: str, default: bool = False) -> bool:
    """Prompt for a yes/no answer, returning a bool.

    Uses 'y'/'n' as the default hint.  Returns True only if the user
    answers 'y' or 'yes' (case-insensitive).
    """
    default_str = "y" if default else "n"
    answer = _prompt(question, default=default_str)
    return answer.lower() in ("y", "yes")


def _step4_session_manager(answers: dict) -> None:
    """Step 4: Interactive session manager (tmux) opt-in.

    Populates *answers* with:
      - ``tmux_enabled`` (bool)
      - ``tmux_windows`` (dict[str, str]) — only present when tmux_enabled is True
    """
    print("\nStep 4 — Session manager (tmux):")

    if not _prompt_bool("Enable session manager?", default=False):
        answers["tmux_enabled"] = False
        return

    # --- Check for tmux ---
    if not shutil.which("tmux"):
        if not _prompt_bool("tmux not found. Attempt to install?", default=False):
            answers["tmux_enabled"] = False
            return
        # Install attempted but we don't run an actual installer here;
        # if the user confirmed we still mark disabled since we can't verify.
        answers["tmux_enabled"] = False
        return

    # tmux is available
    answers["tmux_enabled"] = True
    answers["tmux_windows"] = {"amplifier": "", "shell": ""}

    # --- Optional tool windows ---
    optional_tools = [
        ("lazygit", "git", "lazygit"),
        ("yazi", "files", "yazi"),
    ]
    for tool_name, window_key, start_cmd in optional_tools:
        if not shutil.which(tool_name):
            # Offer to install; if declined, skip this tool
            _prompt_bool(f"{tool_name} not found. Attempt to install?", default=False)
            continue
        # Tool is available — ask whether to add a window
        if _prompt_bool(f"Add {tool_name} window?", default=True):
            answers["tmux_windows"][window_key] = start_cmd


def run_wizard() -> None:
    """Run the interactive first-time setup wizard.

    Collects repository URLs and a bundle name from the user, then writes the
    configuration atomically.  Any KeyboardInterrupt (Ctrl+C) cancels the
    wizard without writing any changes.
    """
    try:
        # ------------------------------------------------------------------
        # Step 1 — Default repos
        # ------------------------------------------------------------------
        print("\nDefault repositories:")
        for i, repo in enumerate(DEFAULT_REPOS, start=1):
            print(f"  {i}. {repo}")
        print()

        keep = _prompt("Keep these defaults?", default="Y")
        if keep.lower() in ("y", "yes", ""):
            repos = list(DEFAULT_REPOS)
        else:
            raw = _prompt("Enter comma-separated repository URLs")
            repos = [url.strip() for url in raw.split(",") if url.strip()]

        # ------------------------------------------------------------------
        # Step 2 — Amplifier bundle
        # ------------------------------------------------------------------
        bundle = _prompt("Amplifier bundle name", default=DEFAULT_BUNDLE)

        # ------------------------------------------------------------------
        # Step 3 — AGENTS.md template
        # ------------------------------------------------------------------
        print("\nAGENTS.md template:")
        print("  [1] Built-in (default)")
        print("  [2] Custom file path")
        template_choice = _prompt("Choice", default="1")
        if template_choice == "2":
            agents_template: str = _prompt("Path to custom AGENTS.md template")
        else:
            agents_template = ""

        # ------------------------------------------------------------------
        # Step 4 — Session manager
        # ------------------------------------------------------------------
        answers: dict = {}
        _step4_session_manager(answers)
        tmux_enabled: bool = answers.get("tmux_enabled", False)
        tmux_windows: dict | None = answers.get("tmux_windows")

        # ------------------------------------------------------------------
        # Write config
        # ------------------------------------------------------------------
        _write_wizard_config(repos, bundle, agents_template, tmux_enabled, tmux_windows)

    except KeyboardInterrupt:
        print("\nSetup cancelled. No changes written.")


def _write_wizard_config(
    repos: list[str],
    bundle: str,
    agents_template: str,
    tmux_enabled: bool,
    tmux_windows: dict | None = None,
) -> None:
    """Build the config dict and write it to disk atomically."""
    tmux_section: dict = {"enabled": tmux_enabled}
    if tmux_windows is not None:
        tmux_section["windows"] = tmux_windows

    data: dict = {
        "workspace": {
            "default_repos": repos,
            "bundle": bundle,
            "agents_template": agents_template,
        },
        "tmux": tmux_section,
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_config(data)
    print(f"Configuration written to {CONFIG_PATH}")
