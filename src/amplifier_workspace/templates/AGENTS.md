# Development Workspace

A **temporary working repository** for cross-repo development. Created fresh for a task; destroyed when complete.

## THE RULES

**Invariant:** Every repo in this workspace lives as a **subdirectory of cwd** with its own `.git` — either a submodule (remote exists) or a local-only git repo (pre-publish). The workspace root is **never** the root of any project's source tree.

| User says… | You do (exactly this) |
|---|---|
| "pull down X", "get X", "clone X", "add X" | `git submodule add <url>` in cwd |
| "start a new project X", "let's build X" (no repo yet) | `mkdir X && cd X && git init` — all new code goes inside this subdir |
| "publish X" / "push X to github" (local-only project) | From inside the subdir: `gh repo create --source=. --push` |

**Forbidden — no matter how convenient it seems:**

- ❌ `git clone <url>` or `gh repo clone <url>` for adding a repo to this workspace — use `git submodule add` instead
- ❌ Using an existing checkout elsewhere on the filesystem (e.g. `~/repos/X/`, `../X/`). The **"helpful reuse"** anti-pattern: edits land in the wrong checkout and versions drift.
- ❌ Scanning parent directories or `~/` looking for existing clones to reuse
- ❌ Creating **new-project source** (code/configs meant to become a published repo) at the workspace root. The **"workspace-as-project-root"** anti-pattern: when you later "publish this," the workspace scraps, submodule refs, and `SCRATCH.md` end up in your project's initial commit. Persistent new-project code goes in a subdir (see table above). *Ephemeral* files at the root are fine — see next section.
- ❌ Committing new-project code to the workspace git — it's throwaway. New-project code belongs in the subdir's own git.

**Why:** The workspace is destroyed at session end. Self-containment is what makes destruction safe. Edits outside cwd, or persistent project code mingled with workspace scraps, cause lost work or polluted initial commits.

## What the Workspace Root IS For

The root is the right place for **anything ephemeral that doesn't need to survive session end**:

- Throwaway scripts and experiments
- Temporary files for the user to inspect, hand off, or reuse in-session
- Cross-repo scratch work — exploration, comparisons, notes that don't belong to any single repo
- Planning docs, design drafts, announcement copy that serve their purpose this session and aren't meant for a repo
- Output of analysis or investigation runs

**Rule of thumb:** If it doesn't need to persist past workspace destruction, the root is fine. If it does, it goes in a subdir (submodule or local git) — no exceptions.

Feel free to use the root liberally for this category of work. The constraint is *persistence*, not *file creation*.

## Session Lifecycle

1. Workspace spun up fresh (already done)
2. Work happens in subdirs for anything that persists; root is free for ephemeral cross-repo work
3. Workspace destroyed when done. The root directory does not persist.

Don't store anything that needs **long-term persistance** in the root directory.

## Working Memory

@SCRATCH.md

Create `SCRATCH.md` at the workspace root as your working memory:
- Plans, important facts, decisions, current state
- Drives what to do **next** — not a log of what was done
- Loaded every turn via the @-mention above
- Keep bounded: prune outdated info, consolidate, focus on remaining work

## Layout

The workspace root holds `AGENTS.md`, `SCRATCH.md`, tool config directories, subdirectories (one per repo), and any ephemeral scratch files. Each subdirectory is its own git repo.

```
./
├── AGENTS.md              # this file
├── SCRATCH.md             # working memory
├── <submodule-repo>/      # existing repo added via `git submodule add`
├── <local-project>/       # new work, `git init` inside, publish later
└── <ephemeral stuff>      # scripts, notes, temp files — fine at root
```

## Publishing a Local-Only Project

When a project subdir is ready to ship:
1. From inside the subdir: `gh repo create --source=. --public --push` (or `--private`)
2. The subdir is now a remote-backed repo — work continues normally
3. In later sessions, the repo can be re-added as a proper submodule: `git submodule add <url>`

**Warning:** A local-only subdir is lost when the workspace is destroyed. Publish (or back up) before destroying.
