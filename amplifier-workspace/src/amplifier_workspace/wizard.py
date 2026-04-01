"""Interactive setup wizard for amplifier-workspace."""

from __future__ import annotations

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
        # Step 4 — Session manager stub
        # ------------------------------------------------------------------
        print("\ntmux session manager setup is available in Phase 3.")
        print("Run amplifier-workspace setup again after upgrading to configure it.")
        tmux_enabled: bool = False

        # ------------------------------------------------------------------
        # Write config
        # ------------------------------------------------------------------
        _write_wizard_config(repos, bundle, agents_template, tmux_enabled)

    except KeyboardInterrupt:
        print("\nSetup cancelled. No changes written.")


def _write_wizard_config(
    repos: list[str],
    bundle: str,
    agents_template: str,
    tmux_enabled: bool,
) -> None:
    """Build the config dict and write it to disk atomically."""
    data: dict = {
        "workspace": {
            "default_repos": repos,
            "bundle": bundle,
            "agents_template": agents_template,
        },
        "tmux": {
            "enabled": tmux_enabled,
        },
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_config(data)
    print(f"Configuration written to {CONFIG_PATH}")
