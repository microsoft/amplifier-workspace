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
amplifier-workspace doctor               # check tool + workspace health
amplifier-workspace doctor ~/dev/fix-auth  # health of a specific workspace
amplifier-workspace upgrade              # self-update the CLI tool itself
amplifier-workspace upgrade --check      # check for updates without installing
amplifier-workspace update ~/dev/fix-auth  # update a workspace's submodules (NOT the tool)
```

> `upgrade` self-updates the **amplifier-workspace CLI tool**. `update` refreshes a
> **workspace's submodules**. They are different verbs for different things.

### Help and version

```bash
amplifier-workspace help                 # top-level help (also: -h, --help)
amplifier-workspace --version            # print the installed version
```

A bare word that is neither a subcommand nor an existing directory (e.g. a
mistyped `amplifier-workspace hepl`) will **not** silently create a workspace:
you get a confirmation prompt, or — when run non-interactively — an error
telling you to pass an existing directory or a path-like name (`./name`).

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

## Workspace Manifest

Workspaces are ephemeral and self-contained, but sessions working inside one often spin up resources that live *outside* the workspace directory -- a DTU, a tmux session, a Gitea repo, a work-tracker project, a cloud resource. `-d`/`-f` deletes the directory; it has no way to reach those.

Each workspace tracks such resources in `WORKSPACE-MANIFEST.json` at its root. Agents are instructed (via `AGENTS.md`) to record a resource the moment they create it, and mark it `"reaped"` once torn down.

Before destroying a workspace, `amplifier-workspace` reads this manifest. If any resource is still `"active"` (or the manifest can't be parsed), destruction is refused until you type `orphan` to explicitly acknowledge it will be left running -- the tool never tears resources down itself, it just refuses to lose track of them silently.

```bash
amplifier-workspace manifest ~/dev/fix-auth               # list tracked resources
amplifier-workspace manifest ~/dev/fix-auth --add dtu dtu-a1b2c3d4 --note "integration test"
amplifier-workspace manifest ~/dev/fix-auth --reap dtu-a1b2c3d4
```

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
  ✓  amplifier-workspace  (git, up to date)
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

When you point `doctor` at a workspace (or run it from inside one), it adds
workspace-scoped checks: whether `WORKSPACE-MANIFEST.json` is present and
parses, how many resources are still active (these gate destroy), and whether
the workspace's `AGENTS.md` still matches the packaged template. Each warning
or failure is paired with a `Run: <fix>` remedy.

## Upgrade

`amplifier-workspace upgrade` self-updates the CLI tool. The reinstall target is
derived **strictly** from how the tool was actually installed (PEP 610
provenance), so it never silently reinstalls a different artifact than the one
you have:

- **git install** (the default `uv tool install git+https://...`): reinstalls from
  the exact recorded URL and tracked branch, checking the remote SHA first
- **editable** (`uv tool install -e .`): **refused** — an upgrade would clobber your
  local checkout; it prints the local-dev commands instead (see below)
- **PyPI / package-manager install**: **refused** — points you at your package
  manager (`uv tool upgrade` / `pip install --upgrade`)
- **unknown provenance**: **refused** with an explicit reinstall command
- **`--force`**: skip the version check, but still honor the provenance rules above
- **`--check`**: report install status without installing

After a successful reinstall it re-reads the metadata and reports the real
`before → after` version (and says so honestly if nothing moved), then runs
`doctor`.

`https://github.com/microsoft/amplifier-workspace` is the documented default for
a **fresh** install only; `upgrade` never substitutes it when your recorded
provenance says otherwise.

## Developing locally (testing your changes)

Neither `uv tool upgrade amplifier-workspace` nor `amplifier-workspace upgrade`
will pick up local edits or an unpushed feature branch — both re-fetch from the
recorded/published source. To run **your** code:

```bash
# From a local checkout (picks up local edits):
uv tool install --from /path/to/checkout --force amplifier-workspace
#   or, from inside the checkout:
uv tool install -e . --force

# From a pushed branch:
uv tool install --force git+https://github.com/microsoft/amplifier-workspace@<branch>
#   or a one-off run without installing:
uvx --from git+https://github.com/microsoft/amplifier-workspace@<branch> amplifier-workspace
```

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
