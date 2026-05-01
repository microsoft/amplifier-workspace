# amplifier-workspace

Create and manage development workspaces for the [Amplifier](https://github.com/microsoft/amplifier) ecosystem.

One command gets you a ready-to-work environment with your repos cloned, templates in place, and (optionally) a multi-window tmux session laid out:

```bash
amplifier-workspace ~/dev/fix-auth
```

That same command resumes an existing workspace if it already exists.

## Install

```bash
uv tool install git+https://github.com/microsoft/amplifier-workspace
```

Requires Python 3.11+. Zero runtime dependencies.

## First Run

The first time you run `amplifier-workspace`, an interactive setup wizard walks you through configuration:

```
$ amplifier-workspace ~/dev/my-task

Welcome to amplifier-workspace!

Step 1 of 4: Default repos
  1. https://github.com/microsoft/amplifier.git
  2. https://github.com/microsoft/amplifier-core.git
  3. https://github.com/microsoft/amplifier-foundation.git
Keep these defaults? [Y/n]:

Step 2 of 4: Amplifier bundle
Amplifier bundle name [amplifier-dev]:

Step 3 of 4: AGENTS.md template
  [1] Built-in (default)
  [2] Custom file path
Choice [1]:

Step 4 of 4: Session manager (optional)
Enable tmux session manager? [y/N]:
```

The wizard writes your config to `~/.config/amplifier-workspace/config.toml`. After that, every `amplifier-workspace` invocation just works.

## Usage

### Daily workflow

```bash
amplifier-workspace ~/dev/fix-auth       # create or resume workspace
amplifier-workspace -k ~/dev/fix-auth    # kill tmux session, keep files
amplifier-workspace -d ~/dev/fix-auth    # destroy everything (prompts)
amplifier-workspace -f ~/dev/fix-auth    # fresh start (destroy + recreate)
```

### Setup and health

```bash
amplifier-workspace setup                # re-run the setup wizard
amplifier-workspace doctor               # check tool health
amplifier-workspace upgrade              # self-update
amplifier-workspace upgrade --check      # check for updates without installing
```

### Configuration

```bash
amplifier-workspace config list
amplifier-workspace config get tmux.enabled
amplifier-workspace config set tmux.enabled true
amplifier-workspace config add workspace.default_repos https://github.com/myorg/myrepo.git
amplifier-workspace config remove workspace.default_repos https://github.com/myorg/myrepo.git
amplifier-workspace config reset         # reset to defaults
```

## What It Creates

When you run `amplifier-workspace ~/dev/fix-auth`, it creates:

```
~/dev/fix-auth/
├── .git/                        # local git repo (ephemeral, for task-level commits)
├── .amplifier/
│   └── settings.yaml            # activates your configured Amplifier bundle
├── AGENTS.md                    # workspace context for AI agents
├── amplifier/                   # git submodule
├── amplifier-core/              # git submodule
└── amplifier-foundation/        # git submodule
```

The workspace root is a local-only git repo -- use it for task-lifetime commits and reverts. The submodule directories are real GitHub repos -- commits and pushes there persist upstream.

## Two Tiers

### Tier 1: Workspace Only (default)

Creates the workspace and launches Amplifier directly. No tmux required.

### Tier 2: Session Manager (opt-in)

Enable during the wizard or with `amplifier-workspace config set tmux.enabled true`.

Adds tmux session management with configurable windows:

```toml
# ~/.config/amplifier-workspace/config.toml

[tmux]
enabled = true

[tmux.windows]
amplifier = ""       # main Amplifier session (with resume detection)
shell = ""           # two-pane shell
git = "lazygit"      # optional: remove line to disable
files = "yazi"       # optional: remove line to disable
```

When Tier 2 is enabled, the wizard offers to install optional tools (lazygit, yazi, etc.) for you with platform-appropriate commands. Each tool window is individually opt-in.

## Doctor

`amplifier-workspace doctor` checks your environment based on what you have configured:

```
$ amplifier-workspace doctor

amplifier-workspace doctor
========================================
  ✓  Python version  3.12.3
  ✓  amplifier-workspace  0.1.0 (git, up to date)
  ✓  git in PATH
  ✓  amplifier in PATH
  ✓  config file  ~/.config/amplifier-workspace/config.toml
  ✓  default_repos  3 repo(s)
  ✓  agents_template  built-in

  tmux (enabled)
  ✓  tmux 3.4
  ✓  4 windows configured
  ✓  lazygit found
  ✗  yazi not found
       install: brew install yazi
       or remove: amplifier-workspace config remove tmux.windows.files

1 issue(s) found
```

If tmux is disabled in your config, those checks are skipped entirely.

## Upgrade

`amplifier-workspace upgrade` detects how the tool was installed and updates accordingly:

- **git install** (the default `uv tool install git+https://...`): checks remote SHA, reinstalls if newer
- **editable** (`uv tool install -e .`): tells you to manage updates manually
- **`--force`**: skip version check, reinstall regardless
- **`--check`**: report if update available without installing

Always runs `doctor` after a successful upgrade.

## Development

```bash
git clone https://github.com/microsoft/amplifier-workspace.git
cd amplifier-workspace
uv tool install -e . --force    # editable install -- changes take effect immediately
python -m pytest tests/ -v      # run tests
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
