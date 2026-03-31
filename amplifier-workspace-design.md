# amplifier-workspace Design

> **Repo:** `microsoft/amplifier-workspace`
> **Command:** `amplifier-workspace`
> **Status:** Design — validated, not yet implemented
> **Date:** 2026-03-31

---

## 1. Overview

`amplifier-workspace` is a CLI tool that creates and manages Amplifier development workspaces. It handles git repository setup, template scaffolding, configuration, and optionally tmux-based multi-window sessions — all behind a single command.

```
amplifier-workspace ~/dev/fix-auth
```

That one command either creates a new workspace (git init, clone submodules, write AGENTS.md and `.amplifier/settings.yaml`, optionally launch a tmux session with configured windows) or resumes an existing one (reattach to the tmux session, or just `cd` into the directory if tmux is disabled).

The tool is the spiritual successor to `bkrabach/amplifier-cli-tools` (the `amplifier-dev` command). It preserves all proven UX patterns from that tool while cleaning up the architecture and making the tmux session manager opt-in rather than mandatory.

**Install:**

```
uv tool install git+https://github.com/microsoft/amplifier-workspace
```

Zero runtime dependencies. Stdlib only.

---

## 2. Design Lineage

### Carried forward from `amplifier-cli-tools`

| Pattern | Why it works |
|---|---|
| Single-command create-or-resume | The crown jewel UX — one command does the right thing |
| Git init + submodules for workspace repos | Clean, reproducible, no custom sync machinery |
| AGENTS.md + `.amplifier/settings.yaml` templating | Workspaces are immediately usable by Amplifier |
| Cross-platform tool install (brew/apt/dnf/winget/GitHub releases) | Users don't have to figure out platform-specific install steps |
| rcfile-based tmux window startup | Robust; avoids the timing hacks of `send-keys` |
| Resume detection | Checks for existing Amplifier sessions before starting fresh |

### Borrowed from `muxplex`

| Pattern | Why it works |
|---|---|
| PEP 610 `direct_url.json` for install source detection | Upgrade behavior adapts to how the tool was installed |
| `git ls-remote` SHA comparison for update checking | Fast, no-install version check for git-installed tools |
| Config-aware doctor (sequential checklist, colored pass/fail) | Only checks what the user has configured |
| Stop → reinstall → restart upgrade cycle | Clean upgrade path |

### Intentionally omitted

| What | Why |
|---|---|
| WezTerm / yazi / lazygit **setup automation** as core responsibility | The tool manages workspaces and tmux sessions. It doesn't install other people's software as a core path — that's handled via the wizard opt-in flow. |
| Non-tmux launcher abstraction | YAGNI. The architecture is clean enough to add later, but there's no second launcher to abstract over today. |
| Workspace definition repos (Mode B) | Deferred to post-V1. |

---

## 3. Two-Tier Architecture

The tool has two tiers. Tier 1 is always available. Tier 2 is opt-in via the wizard or config.

### Tier 1 — Workspace Engine

Always installed. Zero dependencies. This is the complete tool for users who don't want tmux.

**What it does:**

- `amplifier-workspace <path>` — create or resume a workspace directory
- Git init + submodule clone for configured repos
- AGENTS.md and `.amplifier/settings.yaml` scaffolding from templates
- Direct `amplifier` launch (no tmux)
- Config system (TOML-based, `config` subcommands)
- Doctor (health checks)
- Upgrade (self-update)
- Wizard (interactive first-run setup)

**When a user runs `amplifier-workspace ~/dev/fix-auth` with Tier 1 only:**

1. Directory doesn't exist → create it, git init, add submodules, write templates
2. Directory exists → `cd` into it, launch `amplifier` directly
3. No config file → wizard runs automatically first

### Tier 2 — Session Manager

Enabled when `tmux.enabled = true` in config (set by the wizard or manually). Everything in Tier 1, plus:

- tmux session creation with configurable windows
- Session resume (reattach to existing tmux session)
- `-k` flag to kill a tmux session (keep directory)
- Full single-command UX with multi-window layout

Each optional tool window (lazygit, yazi, etc.) is individually opt-in. The wizard walks through each one and offers to install the tool. Users configure which windows they want; the tool doesn't assume.

**When a user runs `amplifier-workspace ~/dev/fix-auth` with Tier 2 enabled:**

1. No tmux session exists → create workspace (if needed), start tmux session with configured windows, attach
2. tmux session exists → reattach
3. `-k` flag → kill the tmux session, leave the directory intact

---

## 4. Configuration

**File:** `~/.config/amplifier-workspace/config.toml`

Created by the wizard on first run, or manually. The wizard writes atomically — all values written at the end, not incrementally.

### Full annotated example

```toml
[workspace]
default_repos = [
    "https://github.com/microsoft/amplifier.git",
    "https://github.com/microsoft/amplifier-core.git",
    "https://github.com/microsoft/amplifier-foundation.git",
]
bundle = "amplifier-dev"
agents_template = ""         # empty string = use built-in template
                             # path string  = use custom template file

[tmux]
enabled = false              # false = Tier 1 only; wizard sets this

[tmux.windows]
# Each key is a window name. Each value is the command to run.
# Presence of a key = window enabled. Remove the line to disable.
amplifier = ""               # always present when tmux enabled
                             # special: launches amplifier with resume detection
shell = ""                   # always present when tmux enabled
                             # special: two-pane split
git = "lazygit"              # optional: remove line to disable
files = "yazi"               # optional: remove line to disable
```

### Design principles

- **Config contains only what the user decided.** No commented-out examples, no "here's what you could set" noise.
- **Tool install hints live in code**, not config. A `KNOWN_TOOLS` internal registry maps command names to per-platform install instructions. Config never stores install metadata.
- **Presence/absence is the toggle.** A window line in `[tmux.windows]` means that window is enabled. Removing the line disables it. No `enabled = true/false` per window.
- **Atomic writes.** The wizard collects all answers, then writes the config file once at the end.
- **`[tmux]` not `[session]`.** "Session" is overloaded in the Amplifier ecosystem. The config section names the actual thing: tmux.

---

## 5. CLI Reference

### Core workflow (daily use)

| Command | Behavior |
|---|---|
| `amplifier-workspace <path>` | Create workspace or resume existing. Tier 1: launch amplifier directly. Tier 2: create/reattach tmux session. |
| `amplifier-workspace -k <path>` | Kill the tmux session for this workspace. Directory is preserved. |
| `amplifier-workspace -d <path>` | Destroy: kill tmux session and delete directory. Prompts for confirmation. |
| `amplifier-workspace -f <path>` | Fresh: kill existing tmux session and recreate from scratch. |

### Setup and health

| Command | Behavior |
|---|---|
| `amplifier-workspace setup` | Run the interactive wizard. Also auto-triggers on first use when no config exists. |
| `amplifier-workspace doctor` | Config-aware health check. Sequential checklist with colored pass/fail output. |
| `amplifier-workspace upgrade` | Self-update. Detects install source, updates accordingly. Runs doctor after success. |
| `amplifier-workspace upgrade --force` | Skip version check, reinstall regardless. |
| `amplifier-workspace upgrade --check` | Report whether an update is available. Don't install. |

### Config management

| Command | Behavior |
|---|---|
| `amplifier-workspace config list` | Show current config. |
| `amplifier-workspace config get <key>` | Get a single value. Dot-separated keys (e.g. `tmux.enabled`). |
| `amplifier-workspace config set <key> <value>` | Set a single value. |
| `amplifier-workspace config add <key> <value>` | Append to a list value (e.g. `workspace.default_repos`). |
| `amplifier-workspace config remove <key> <value>` | Remove from a list value. |
| `amplifier-workspace config reset` | Reset config to defaults. Prompts for confirmation. |

### Workspace inspection

| Command | Behavior |
|---|---|
| `amplifier-workspace list` | Show all known active workspaces. |

---

## 6. Wizard

The wizard is the interactive setup flow. It runs automatically when no config file exists, and can be re-run at any time via `amplifier-workspace setup`.

**Behavior:**

- Ctrl+C exits cleanly at any point. No partial config is written.
- Config is written atomically at the end (all-or-nothing).
- Re-running overwrites the existing config.

### Step 1 — Default repos

```
Default repos to clone into new workspaces:
  1. https://github.com/microsoft/amplifier.git
  2. https://github.com/microsoft/amplifier-core.git
  3. https://github.com/microsoft/amplifier-foundation.git

Keep these defaults? [Y/n]
```

If no: prompt for a comma-separated list or interactive add/remove.

### Step 2 — Amplifier bundle

```
Amplifier bundle name [amplifier-dev]:
```

Press enter to accept the default.

### Step 3 — AGENTS.md template

```
AGENTS.md template:
  [1] Built-in (default)
  [2] Custom file path

Choice [1]:
```

### Step 4 — Session manager

```
Enable tmux session manager? (multi-window workspace sessions) [y/N]
```

If yes, the wizard checks for tmux:

```
Checking for tmux... ✓ found (v3.4)
```

Then walks through each optional tool window:

```
Configure lazygit window?
  lazygit not found.
  Install lazygit? [y/N]
```

If the user says yes, the wizard attempts a platform-appropriate install (see §9). On success:

```
  ✓ lazygit installed (v0.44.1)
  Window 'git' added.
```

On failure:

```
  ✗ Install failed. You can install manually:
    brew install lazygit
  Skip this window for now? [Y/n]
```

Skipping is always graceful. The wizard tells the user how to add the window later via config.

After all steps:

```
Config written to ~/.config/amplifier-workspace/config.toml

Run `amplifier-workspace doctor` to verify your setup.
```

---

## 7. Doctor

Config-aware sequential health check. Only checks what the user has configured.

**Output format:** colored pass/fail with a summary line.

### Checks (always run)

| Check | Pass | Fail |
|---|---|---|
| Python version | `✓ Python 3.12.3` | `✗ Python 3.8 (need ≥3.11)` |
| amplifier-workspace version | `✓ amplifier-workspace 0.1.0 (git)` | — |
| Update status | `✓ Up to date` | `⚠ Update available (abc1234 → def5678)` |
| git | `✓ git 2.43.0` | `✗ git not found` |
| amplifier | `✓ amplifier found in PATH` | `✗ amplifier not found` |
| Config file | `✓ Config: ~/.config/amplifier-workspace/config.toml` | `✗ No config file (run amplifier-workspace setup)` |
| Default repos | `✓ 3 default repos configured` | `⚠ No default repos configured` |
| AGENTS.md template | `✓ Using built-in template` | `✗ Template file not found: /path/to/custom.md` |

### Checks (only when `tmux.enabled = true`)

| Check | Pass | Fail |
|---|---|---|
| tmux version | `✓ tmux 3.4` | `✗ tmux not found` |
| Window list | `✓ 4 windows configured` | — |
| Each tool in `tmux.windows` | `✓ lazygit found` | `✗ lazygit not found (brew install lazygit — or remove 'git' from [tmux.windows])` |

Checks that don't apply are skipped with `- tmux: skipped (not enabled)`.

### Summary line

Always present at the end:

```
All checks passed.
```

or:

```
2 issues found. Run `amplifier-workspace setup` to reconfigure.
```

### Exit codes

- `0` — all checks passed
- `1` — one or more checks failed

---

## 8. Upgrade

Self-update mechanism adapted from the `muxplex` pattern.

### Install source detection

Uses PEP 610 `direct_url.json` to determine how the tool was installed:

| Source | Detection | Upgrade behavior |
|---|---|---|
| **git** (uv tool install git+...) | `direct_url.json` contains VCS URL | `git ls-remote` SHA comparison. If different: `uv tool install --force git+https://github.com/microsoft/amplifier-workspace` |
| **editable** (pip install -e .) | `direct_url.json` with `dir_info.editable = true` | Print "Editable install — manage updates manually." Exit clean. |
| **PyPI** (future) | `direct_url.json` absent or contains PyPI URL | Version comparison. If newer: `uv tool install --force amplifier-workspace` |
| **Unknown** | No `direct_url.json` or unrecognized format | Assume update needed. Reinstall to be safe. |

### Flags

- `amplifier-workspace upgrade` — check + install if update available
- `amplifier-workspace upgrade --check` — check only, print result, don't install
- `amplifier-workspace upgrade --force` — skip version check, reinstall unconditionally

### Post-upgrade

After a successful reinstall, doctor runs automatically to verify the new version.

---

## 9. Cross-Platform Tool Installation

Used by the wizard when a user opts in to a tool window and the tool isn't installed. Also used as the source for install hints shown by doctor.

### Platform detection and install commands

| Tool | macOS | Linux (apt) | Linux (dnf) | Linux (lazygit special) | Windows/WSL |
|---|---|---|---|---|---|
| tmux | `brew install tmux` | `sudo apt install tmux` | `sudo dnf install tmux` | — | `winget install tmux` |
| lazygit | `brew install lazygit` | — | — | GitHub releases API → tarball → `/usr/local/bin` (sudo) or `~/.local/bin` (no sudo) | `winget install lazygit` |
| yazi | `brew install yazi` | — | — | — (print instructions: cargo or GitHub releases) | `winget install yazi` |

### Behavior

- **Linux package manager priority:** try `apt` first, fall back to `dnf`.
- **Sudo-aware:** check for `sudo` availability before attempting privileged operations. Fall back to user-local install paths (`~/.local/bin`) when sudo isn't available.
- **lazygit on Linux:** special case. No reliable package in apt/dnf. Uses GitHub releases API to find the latest release, downloads the tarball, extracts, and installs the binary.
- **yazi on Linux:** no reliable automated path. Print manual instructions (cargo install or GitHub releases).
- **Failure is not fatal.** If install fails, print the command the user can run manually and offer to skip the window.

### `KNOWN_TOOLS` registry

Internal (in code, not in config). Maps tool command names to per-platform install metadata:

```python
KNOWN_TOOLS = {
    "tmux": {
        "brew": "tmux",
        "apt": "tmux",
        "dnf": "tmux",
        "winget": "tmux",
    },
    "lazygit": {
        "brew": "lazygit",
        "winget": "lazygit",
        "github": "jesseduffield/lazygit",  # GitHub releases fallback
    },
    "yazi": {
        "brew": "yazi",
        "winget": "yazi",
        "manual": "Install via cargo: cargo install yazi-fm yazi-cli",
    },
}
```

---

## 10. Repository Structure

```
microsoft/amplifier-workspace/
├── README.md
├── pyproject.toml                  # hatchling build, zero runtime deps
│                                   # [project.scripts] entry point
├── uv.lock
├── src/amplifier_workspace/
│   ├── __init__.py
│   ├── __main__.py                 # python -m amplifier_workspace → cli.main()
│   ├── cli.py                      # argument parsing, routes to modules
│   ├── workspace.py                # create / destroy / resume logic
│   ├── git.py                      # git init, submodule add/update
│   ├── config.py                   # config data structures, load, merge
│   ├── config_manager.py           # TOML file read/write/CRUD operations
│   ├── wizard.py                   # interactive first-run setup
│   ├── doctor.py                   # health checks
│   ├── upgrade.py                  # self-update via PEP 610 detection
│   ├── tmux.py                     # session/window management (Tier 2)
│   ├── install.py                  # cross-platform tool installation
│   └── templates/
│       ├── AGENTS.md               # built-in workspace template
│       └── default-config.toml     # default values for wizard
├── tests/
└── docs/
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `cli.py` | Thin. Parses args, routes to the right module. No business logic. |
| `workspace.py` | Orchestrates workspace create/resume/destroy. Calls `git.py`, `tmux.py`, reads config. |
| `git.py` | Git init, submodule add, submodule update. Wraps `subprocess` calls to `git`. |
| `config.py` | Config dataclass/TypedDict definitions. Load from TOML, merge with defaults. |
| `config_manager.py` | File I/O for config. TOML parsing (stdlib `tomllib` for read, simple writer for write). CRUD for `config` subcommands. |
| `wizard.py` | Interactive prompts. Collects all answers, calls `config_manager` to write once at end. |
| `doctor.py` | Sequential health checks. Reads config to determine which checks to run. |
| `upgrade.py` | PEP 610 `direct_url.json` detection. `git ls-remote`. Calls `uv tool install`. |
| `tmux.py` | tmux session create/attach/kill. Rcfile-based window startup. Resume detection. |
| `install.py` | `KNOWN_TOOLS` registry. Platform detection. Package manager invocation. |

### Build

- **Build system:** hatchling
- **Runtime dependencies:** none (stdlib only)
- **Python version:** ≥ 3.11 (for `tomllib`)
- **Entry point:** `[project.scripts] amplifier-workspace = "amplifier_workspace.cli:main"`

---

## 11. Design Principles

### What was carried forward and why

The core UX of `amplifier-cli-tools` is excellent: one command, create-or-resume, everything just works. That's preserved exactly. The git submodules approach, AGENTS.md templating, rcfile-based tmux startup, and resume detection are all proven patterns that work reliably.

The cross-platform install logic from `amplifier-cli-tools/shell.py` is carried forward in full, including the lazygit-on-Linux GitHub releases special case. This is battle-tested code.

The upgrade machinery from `muxplex` (PEP 610 detection, `git ls-remote` comparison, stop-reinstall-restart cycle) is cleaner than what `amplifier-cli-tools` had and is adopted as-is.

### What was intentionally omitted and why

**WezTerm/yazi/lazygit setup automation as a core path.** The old tool treated installing third-party tools as a first-class responsibility. The new tool treats it as a wizard convenience. The tool's core job is workspace management, not being a package manager. If a user doesn't want lazygit, they just don't configure that window — no dead code runs, no checks fire.

**Non-tmux launcher abstraction.** There's only one launcher (tmux). Abstracting over a single implementation is complexity for no benefit. If a second launcher appears (e.g., WezTerm panes, Zellij), the abstraction can be introduced then. YAGNI.

**Workspace definition repos.** The idea of `amplifier-workspace up --from git+https://...` (pull a workspace spec from a repo) is interesting but not needed for V1. Current users define their workspace via config. Deferred.

### Key naming decisions

- **`[tmux]` not `[session]`** — "session" is heavily overloaded in the Amplifier ecosystem (Amplifier sessions, chat sessions, MCP sessions). The config section names the actual technology.
- **`amplifier-workspace` not `aw` or `amp-ws`** — explicit, discoverable, tab-completable. Users who want shorter can alias it.
- **`-k` / `-d` / `-f` flags on the path command** — not separate `kill` / `destroy` / `fresh` subcommands. These are modifiers on the core workflow, not separate workflows.

---

## 12. Future / Deferred Work

These are known ideas explicitly deferred from V1.

| Item | Description | Why deferred |
|---|---|---|
| Workspace definition repos | `amplifier-workspace up --from git+https://...` — pull workspace spec from a repo | No user demand yet. Config-based setup covers current needs. |
| muxplex pairing | Optional companion for web-based session dashboard | Separate tool, separate concern. Can integrate later via config. |
| Non-tmux launcher abstraction | Support for WezTerm panes, Zellij, or other terminal multiplexers | Only one launcher exists today. Abstraction without a second implementation is overhead. |
| PyPI publishing | `pip install amplifier-workspace` | Git install via `uv tool install` is sufficient for the current user base. PyPI can be added when there's broader adoption. |
