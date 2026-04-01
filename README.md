# amplifier-workspace

A workspace scaffolding and session management tool for the [Amplifier](https://github.com/microsoft/amplifier) project.

## Overview

`amplifier-workspace` creates isolated workspaces with:

- **Git integration** — Automatic submodule setup, branch tracking, and initialization
- **Configuration management** — TOML-based settings with live reload, defaults, and CRUD operations
- **Tool health checks** — Platform-aware diagnostics for Python, git, amplifier, and (optionally) tmux
- **Interactive setup wizard** — First-run configuration with validation and atomic writes
- **Self-update capability** — PEP 610 detection and reinstall cycle for development environments
- **Tier 1 (always)** — Core workspace creation, templates, and direct Amplifier launch
- **Tier 2 (optional)** — tmux session management with configurable windows, resume detection, and rcfile-based startup

## Installation

Using `uv` (recommended):

```bash
uv tool install amplifier-workspace
```

Or with pip:

```bash
pip install amplifier-workspace
```

## Quick Start

```bash
# Create a new workspace
amplifier-workspace ~/dev/my-task

# Run the setup wizard (first-time setup)
amplifier-workspace ~/dev/my-task setup

# Check system health
amplifier-workspace ~/dev/my-task doctor

# List workspaces (Tier 2)
amplifier-workspace list

# Kill a tmux session (Tier 2, with -k flag)
amplifier-workspace ~/dev/my-task -k
```

## Architecture

- **Phase 1: Core Infrastructure** — Config system, git operations, workspace engine, Tier 1 CLI
- **Phase 2: Setup, Health & Self-Update** — Interactive wizard, diagnostic doctor, PEP 610 upgrade detection
- **Phase 3: Session Manager** — tmux integration, Tier 2 session lifecycle, extended CLI

**243 tests, zero external dependencies, stdlib-only for Python 3.11+.**

## Documentation

- **[Design Document](docs/DESIGN.md)** — Architecture, design principles, and rationale
- **Implementation Plans** — [Phase 1](docs/plans/2026-03-31-phase1-core-infrastructure.md), [Phase 2](docs/plans/2026-03-31-phase2-setup-health-upgrade.md), [Phase 3](docs/plans/2026-03-31-phase3-session-manager.md)

## Development

Clone and install in editable mode:

```bash
git clone https://github.com/microsoft/amplifier-workspace.git
cd amplifier-workspace
uv tool install -e .
```

Run tests:

```bash
python -m pytest tests/ -v
```

Check code quality:

```bash
ruff format src/ tests/
ruff check src/ tests/
pyright src/
```

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

## License

[MIT](LICENSE)
