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


def _stub_subcommand(name: str) -> None:
    """Print a stub message for unimplemented subcommands and exit 0."""
    print(f"{name}: not yet implemented (coming in Phase 2)")
    sys.exit(0)


def main() -> None:
    """Entry point for the amplifier-workspace CLI."""
    # Fast-path: intercept known subcommands before argparse sees them.
    if len(sys.argv) >= 2 and sys.argv[1] in _SUBCOMMANDS:
        _stub_subcommand(sys.argv[1])

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
        help="Kill an existing Amplifier session (coming in Phase 2).",
    )

    try:
        args = parser.parse_args()

        if args.workdir is None:
            parser.print_help()
            sys.exit(0)

        workdir: Path = Path(args.workdir).expanduser().resolve()

        config = load_config()

        if args.destroy:
            _confirm_destroy(workdir)

        from amplifier_workspace.workspace import run_workspace

        run_workspace(workdir, config, destroy=args.destroy, fresh=args.fresh)

    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
