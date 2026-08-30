"""Command-line entry point for amplifier-workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from amplifier_workspace.config import load_config

_SUBCOMMANDS = ("doctor", "upgrade", "setup", "config", "list", "update", "manifest")


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
    print("Workspace list not yet tracked (available in Phase 3).")


def _cmd_update(workdir: Path) -> None:
    """Pull all submodules in *workdir* to their latest remote main."""
    from amplifier_workspace.workspace import update_workspace  # noqa: PLC0415

    update_workspace(workdir)


def _cmd_manifest(
    workdir: Path,
    *,
    add: list[str] | None,
    note: str | None,
    teardown: str | None,
    reap: str | None,
) -> None:
    """List the workspace resource manifest, or add/reap an entry.

    With no flags, prints a listing (active resources first) and always
    succeeds -- listing never raises.  ``--add``/``--reap`` are for
    scripted use; the primary writers are agents editing
    WORKSPACE-MANIFEST.json directly.
    """
    from amplifier_workspace import manifest  # noqa: PLC0415

    if add is not None:
        kind, resource_id = add
        manifest.add_resource(workdir, kind, resource_id, note=note, teardown=teardown)
        print(f"added: [{kind}] {resource_id}")
        return
    if reap is not None:
        manifest.reap_resource(workdir, reap)
        print(f"reaped: {reap}")
        return
    print(manifest.format_manifest_listing(workdir))


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

            # update — optional workdir (defaults to cwd)
            update_p = subparsers.add_parser(
                "update",
                help="Pull all submodules to their latest remote main.",
            )
            update_p.add_argument(
                "workdir",
                nargs="?",
                type=Path,
                default=None,
                help=(
                    "Path to the workspace directory. "
                    "Defaults to the current working directory."
                ),
            )

            # manifest — list, or (optionally) add/reap a resource entry
            manifest_p = subparsers.add_parser(
                "manifest",
                help="List (or edit) the workspace resource manifest.",
            )
            manifest_p.add_argument(
                "workdir",
                nargs="?",
                type=Path,
                default=None,
                help=(
                    "Path to the workspace directory. "
                    "Defaults to the current working directory."
                ),
            )
            manifest_p.add_argument(
                "--add",
                nargs=2,
                metavar=("KIND", "ID"),
                default=None,
                help="Add a resource entry: --add <kind> <id>.",
            )
            manifest_p.add_argument(
                "--note",
                default=None,
                help="Optional note to attach when using --add.",
            )
            manifest_p.add_argument(
                "--teardown",
                default=None,
                help="Optional teardown-command hint to attach when using --add.",
            )
            manifest_p.add_argument(
                "--reap",
                metavar="ID",
                default=None,
                help="Mark the resource with this id as reaped.",
            )

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
            elif args.command == "update":
                workdir = (
                    Path(args.workdir).expanduser().resolve()
                    if args.workdir is not None
                    else Path.cwd()
                )
                _cmd_update(workdir)
            elif args.command == "manifest":
                workdir = (
                    Path(args.workdir).expanduser().resolve()
                    if args.workdir is not None
                    else Path.cwd()
                )
                _cmd_manifest(
                    workdir,
                    add=args.add,
                    note=args.note,
                    teardown=args.teardown,
                    reap=args.reap,
                )
            return

        parser = argparse.ArgumentParser(
            prog="amplifier-workspace",
            description="Bootstrap and launch an Amplifier workspace.",
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
