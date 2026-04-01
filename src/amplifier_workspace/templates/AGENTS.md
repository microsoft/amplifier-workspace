# Amplifier Development Workspace

This is a **temporary working repository** for cross-repo Amplifier development.

## Session Approach

This workspace was created for a **specific task** and will be **destroyed when complete**. The pattern:
1. Workspace spun up fresh for a task (already done)
2. Work happens here — committing and pushing to submodule repos
3. Workspace destroyed when done (nothing in the root directory persists)

Each task gets a clean slate. Don't store anything important in this root directory.

## Working Memory

@SCRATCH.md

Create `SCRATCH.md` in this directory as your working memory:
- **What it is**: A scratchpad for plans, important facts, decisions, and current state
- **Purpose**: Drives what to do next, not just a log of what was done
- **Loaded every turn**: The @-mention above injects it into every request
- **Keep it bounded**: Actively prune outdated info, remove completed items, consolidate
- **Keep it focused**: Only retain what's needed for remaining work — working memory, not an archive

## Workspace Structure

This git repo exists locally only (not pushed anywhere) and contains:

```
./                               # Temporary workspace (local git, throwaway)
├── AGENTS.md                    # This file — workspace context
├── SCRATCH.md                   # Working memory (create after intent established)
├── .amplifier/
│   └── settings.yaml            # Amplifier bundle configuration
├── amplifier/                   # submodule: microsoft/amplifier
├── amplifier-core/              # submodule: microsoft/amplifier-core
├── amplifier-foundation/        # submodule: microsoft/amplifier-foundation
└── [additional submodules]      # Added as needed during work
```

## Git Workflow

**This workspace repo:**
- Local only, never pushed anywhere
- Use however you see fit (commits, branches, whatever helps)
- Will be destroyed at session end

**Submodule repos:**
- These ARE real repos pushed to GitHub
- Commit and push your work to these
- Changes here persist beyond the session

**Adding new repos:** When you need content from another Amplifier repo, add it as a submodule:
```bash
git submodule add https://github.com/microsoft/amplifier-module-xyz.git
```

**Updating submodules:**
```bash
git submodule update --remote --merge              # all submodules
git submodule update --remote --merge amplifier-core  # single submodule
```

## Key Repos Reference

| Directory | Repo | Purpose |
|-----------|------|---------|
| @amplifier/ | [microsoft/amplifier](https://github.com/microsoft/amplifier) | Entry point, docs, getting started |
| @amplifier-core/ | [microsoft/amplifier-core](https://github.com/microsoft/amplifier-core) | Kernel — tiny, stable, boring |
| @amplifier-foundation/ | [microsoft/amplifier-foundation](https://github.com/microsoft/amplifier-foundation) | Bundles, behaviors, libraries |

## For More Context

- @amplifier/docs/MODULES.md — Full module ecosystem and repo locations
- @amplifier/docs/REPOSITORY_RULES.md — Repo boundaries and conventions

## Notes for Agents

1. **Read this file first** to understand the workspace layout.
2. **Use `SCRATCH.md`** for ephemeral notes — do not litter the workspace with temporary files.
3. **Submodule directories** contain the full source of each repository. Navigate into them normally.
4. **Edits belong in submodules**, not in `~/.amplifier/cache/` — edit the source directly.
5. **Do not commit directly** to submodule directories unless you intend to push upstream.
6. **Check `.amplifier/settings.yaml`** for the active bundle and provider configuration.
