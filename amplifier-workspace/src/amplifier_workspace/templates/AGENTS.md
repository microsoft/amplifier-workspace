# Amplifier Development Workspace

This document describes the structure and conventions for your Amplifier development workspace.
It is generated during `amplifier-workspace init` and placed at the workspace root.

---

## Workspace Structure

```
workspace-root/
├── AGENTS.md                    ← This file (workspace guidance for agents)
├── SCRATCH.md                   ← Ephemeral scratchpad for session notes
├── .amplifier/
│   └── settings.yaml            ← Amplifier bundle/provider configuration
├── amplifier/                   ← git submodule: main amplifier repo
├── amplifier-core/              ← git submodule: amplifier-core repo
└── amplifier-foundation/        ← git submodule: amplifier-foundation repo
```

---

## Persistent vs Ephemeral Locations

| Location | Type | Purpose |
|---|---|---|
| `AGENTS.md` | **Persistent** | Workspace guidance — checked into version control |
| `.amplifier/settings.yaml` | **Persistent** | Amplifier configuration — checked into version control |
| `amplifier/` | **Persistent** | Submodule — tracks upstream repo |
| `amplifier-core/` | **Persistent** | Submodule — tracks upstream repo |
| `amplifier-foundation/` | **Persistent** | Submodule — tracks upstream repo |
| `SCRATCH.md` | **Ephemeral** | Session scratchpad — not committed, safe to overwrite |

---

## SCRATCH.md Pattern

`SCRATCH.md` is a free-form scratchpad for the current development session. Use it to:

- Track in-progress investigations
- Record working notes, hypotheses, or observations
- Store temporary command outputs or diffs
- List open questions or blockers

`SCRATCH.md` is **never committed**. It resets between sessions. Do not rely on it for
information that needs to persist — use proper files or commits instead.

---

## Workspace Lifecycle Commands

### Initialize a new workspace

```bash
amplifier-workspace init [--workspace-dir PATH]
```

Creates the workspace directory, initializes git submodules, writes `AGENTS.md` and
`.amplifier/settings.yaml`, and sets up the Amplifier bundle configuration.

### Check workspace health

```bash
amplifier-workspace health [--workspace-dir PATH]
```

Verifies that all submodules are present and at the expected commits, checks that
the Amplifier bundle is correctly configured, and reports any issues.

### Update all submodules

```bash
git submodule update --remote --merge
```

Pulls the latest changes for all configured submodules. Run this to sync with upstream.

### Update a single submodule

```bash
git submodule update --remote --merge amplifier-core
```

Updates only the named submodule to its latest upstream commit.

---

## Adding More Repos

To add a new repository as a submodule in your workspace:

```bash
cd workspace-root
git submodule add <repo-url> <directory-name>
git commit -m "chore: add <repo-name> submodule"
```

Then add it to your `default-config.toml` (or workspace config) so it is included
in future `init` runs:

```toml
[workspace]
default_repos = [
  "https://github.com/your-org/amplifier.git",
  "https://github.com/your-org/amplifier-core.git",
  "https://github.com/your-org/amplifier-foundation.git",
  "https://github.com/your-org/your-new-repo.git",
]
```

---

## Bundle Configuration

The Amplifier bundle controls which agents, tools, and context are available in your
workspace sessions. The bundle is configured in `.amplifier/settings.yaml`.

Default bundle for development workspaces: `amplifier-dev`

To switch bundles:

```bash
# Edit .amplifier/settings.yaml directly, or:
amplifier-workspace configure --bundle <bundle-name>
```

For more information on bundle authoring and configuration, refer to the
Amplifier Foundation documentation in `amplifier-foundation/`.

---

## Notes for Agents

When working in this workspace:

1. **Read this file first** to understand the workspace layout.
2. **Use `SCRATCH.md`** for ephemeral notes — do not litter the workspace with temporary files.
3. **Submodule directories** (`amplifier/`, `amplifier-core/`, `amplifier-foundation/`) contain
   the full source of each repository. Navigate into them normally.
4. **Do not commit directly** to submodule directories unless you intend to push upstream.
5. **Check `.amplifier/settings.yaml`** for the active bundle and provider configuration.
