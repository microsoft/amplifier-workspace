"""Command-line entry point for amplifier-workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from amplifier_workspace.config import load_config

_SUBCOMMANDS = ("doctor", "upgrade", "setup", "config", "list")


def _confirm_destroy(workdir: Path) -> None:
    """Print *workdir* and prompt for confirmation before a destructive action.

    Exits with code 1 if the user does not confirm (or if stdin is closed).
    """
    print(f"This will DESTROY: {workdir}")
    try:
        answer = input("Are you sure? [y/N] ")
    except EOFError:
        sys.exit(1)
    if answer.strip().lower() != "y":
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand handler functions (lazy imports to avoid circular deps)
# ---------------------------------------------------------------------------


def _cmd_setup() -> None:
    """Run the interactive setup wizard."""
    from amplifier_workspace.wizard import run_wizard  # noqa: PLC0415

    run_wizard()


def _cmd_doctor() -> None:
    """Run health checks and exit with the check result code."""
    from amplifier_workspace.doctor import run_doctor  # noqa: PLC0415

    sys.exit(run_doctor())


def _cmd_upgrade(*, force: bool, check_only: bool) -> None:
    """Upgrade amplifier-workspace."""
    from amplifier_workspace.upgrade import run_upgrade  # noqa: PLC0415

    run_upgrade(force=force, check_only=check_only)


def _cmd_config(action: str | None, key: str | None, value: str | None) -> None:
    """Manage configuration via CRUD operations."""
    from amplifier_workspace.config import load_config as _load_config  # noqa: PLC0415
    from amplifier_workspace.config_manager import (  # noqa: PLC0415
        add_to_setting,
        get_nested_setting,
        remove_from_setting,
        set_nested_setting,
        write_config_raw,
    )

    if action == "list":
        cfg = _load_config()
        print(f"workspace.bundle={cfg.bundle}")
        print(f"workspace.default_repos={cfg.default_repos}")
        print(f"workspace.agents_template={cfg.agents_template}")
        print(f"tmux.enabled={cfg.tmux.enabled}")
        for name, cmd in cfg.tmux.windows.items():
            print(f"tmux.windows.{name}={cmd}")
    elif action == "get":
        if key is not None:
            print(get_nested_setting(key))
    elif action == "set":
        if key is not None:
            set_nested_setting(key, value)
    elif action == "add":
        if key is not None:
            print(add_to_setting(key, value))
    elif action == "remove":
        if key is not None:
            print(remove_from_setting(key, value))
    elif action == "reset":
        try:
            answer = input("Reset configuration to defaults? [y/N] ")
        except EOFError:
            sys.exit(1)
        if answer.strip().lower() == "y":
            write_config_raw({})
    else:
        print("Usage: amplifier-workspace config {list,get,set,add,remove,reset}")


def _cmd_list() -> None:
    """Print a placeholder message for the workspace list command."""
    print("Workspace tracking not yet available.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Entry point for the amplifier-workspace CLI."""
    try:
        # Fast-path: dispatch known subcommands before the workdir parser sees them.
        if len(sys.argv) >= 2 and sys.argv[1] in _SUBCOMMANDS:
            sub_parser = argparse.ArgumentParser(
                prog="amplifier-workspace",
                description="Bootstrap and launch an Amplifier workspace.",
            )
            subparsers = sub_parser.add_subparsers(dest="command")

            # setup — no extra args
            subparsers.add_parser("setup", help="Run interactive setup wizard.")

            # doctor — no extra args
            subparsers.add_parser("doctor", help="Run health checks.")

            # upgrade — --force and --check flags
            upgrade_p = subparsers.add_parser(
                "upgrade", help="Upgrade amplifier-workspace."
            )
            upgrade_p.add_argument(
                "--force",
                action="store_true",
                help="Skip version check and reinstall unconditionally.",
            )
            upgrade_p.add_argument(
                "--check",
                action="store_true",
                dest="check_only",
                help="Print current version status without installing.",
            )

            # config — sub-subparsers for each action
            config_p = subparsers.add_parser("config", help="Manage configuration.")
            config_subs = config_p.add_subparsers(dest="action")

            config_subs.add_parser("list", help="Print all config values.")

            get_p = config_subs.add_parser("get", help="Print a config value.")
            get_p.add_argument("key", help="Dot-notation key (e.g. workspace.bundle).")

            set_p = config_subs.add_parser("set", help="Set a config value.")
            set_p.add_argument("key", help="Dot-notation key.")
            set_p.add_argument("value", help="Value to set.")

            add_p = config_subs.add_parser("add", help="Add a value to a list setting.")
            add_p.add_argument("key", help="Dot-notation key.")
            add_p.add_argument("value", help="Value to add.")

            remove_p = config_subs.add_parser(
                "remove", help="Remove a value from a list setting."
            )
            remove_p.add_argument("key", help="Dot-notation key.")
            remove_p.add_argument("value", help="Value to remove.")

            config_subs.add_parser(
                "reset", help="Reset configuration to defaults (interactive)."
            )

            # list — no extra args
            subparsers.add_parser("list", help="List workspaces.")

            args = sub_parser.parse_args()

            if args.command == "setup":
                _cmd_setup()
            elif args.command == "doctor":
                _cmd_doctor()
            elif args.command == "upgrade":
                _cmd_upgrade(force=args.force, check_only=args.check_only)
            elif args.command == "config":
                _cmd_config(
                    args.action,
                    getattr(args, "key", None),
                    getattr(args, "value", None),
                )
            elif args.command == "list":
                _cmd_list()
            return

        _EPILOG = """\
commands:
  amplifier-workspace setup          Run the interactive setup wizard
  amplifier-workspace doctor         Check environment health
  amplifier-workspace upgrade        Self-update to latest version
  amplifier-workspace config         Manage configuration (list, get, set, add, remove, reset)
  amplifier-workspace list           List active workspaces
"""
        parser = argparse.ArgumentParser(
            prog="amplifier-workspace",
            description="Create and manage Amplifier development workspaces.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=_EPILOG,
        )
        parser.add_argument(
            "workdir",
            nargs="?",
            type=Path,
            default=None,
            help="Path to the workspace directory.",
        )
        parser.add_argument(
            "-d",
            "--destroy",
            action="store_true",
            help="Destroy the workspace directory and exit.",
        )
        parser.add_argument(
            "-f",
            "--fresh",
            action="store_true",
            help="Remove an existing workspace before recreating it.",
        )
        parser.add_argument(
            "-k",
            "--kill",
            action="store_true",
            help="Kill the tmux session for this workspace (directory is preserved).",
        )

        args = parser.parse_args(argv)

        if args.workdir is None:
            parser.print_help()
            sys.exit(0)

        workdir: Path = Path(args.workdir).expanduser().resolve()

        config = load_config()

        if args.destroy:
            _confirm_destroy(workdir)

        from amplifier_workspace.workspace import run_workspace

        run_workspace(
            workdir, config, kill=args.kill, destroy=args.destroy, fresh=args.fresh
        )

    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
