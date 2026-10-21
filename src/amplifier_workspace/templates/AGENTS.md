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

## Each Subdir Is a Repo With Its Own Rules

The rules above govern the **root**. Each subdir is a separate repo with its **own** conventions, and inside that subdir those conventions override your workspace defaults — you are a guest there.

When you start work in a subdir — and again when the work shifts phase (design → code → debug → verify → PR) — discover and honor that repo's convention files: `AGENTS.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md`, and contextual files like `PRINCIPLES.md` / `SMOKE_TESTS.md` / `KNOWN_ISSUES.md`. Read them before you change the furniture; re-read them as the work changes shape; populate the PR template from real evidence, not paraphrase. And **before you call the work done, capture the lessons it surfaced back into the file that owns them** — honoring each repo's awareness boundaries: only write a lesson into a repo that is allowed to know what it encodes.

Don't reconstruct that guidance from memory. Load the `per-repo-conventions` skill, or read `foundation:docs/PER_REPO_CONVENTIONS.md`, for the full discovery pattern, re-read cadence, verification gradient, and lesson-capture routing.

## Verification and Missing Tools

1. **Match the requested evidence.** Static inspection and unit tests support verification; they do not replace a requested live-model or deployed-workload test. Run the actual workflow and inspect its result. A prompted acknowledgment alone does not prove tool dispatch: check the genuine tool call and result when claiming tool use.
2. **Isolate execution when the host path is unsafe.** Do not run the host `amplifier` with a scratch `AMPLIFIER_HOME`: first-run module installation can change its shared tool environment. Use a DTU for runtime verification instead. Prefer the Docker Compose Smart Tool, `digital-twin-universe`, for new compatible environments; keep existing resources on their original backend. Its profiles and state are not interchangeable with Incus `amplifier-digital-twin`.
3. **Discover before installing.** Check the selected executable's version, read its installed `--help`, and use `digital-twin-universe check` for Docker readiness. This is deterministic; `install` is model-backed Docker setup, not a readiness probe. For a missing tool, use the owning project's installation instructions: [DTU Smart Tool](https://github.com/microsoft/amplifier-smart-tool-digital-twin-universe#installation) and [optional legacy Amplifier Tester](https://github.com/microsoft/amplifier-bundle-amplifier-tester#installation).
4. **Complete ordinary authorized setup.** A missing executable or agent is a setup task, not a reason to downgrade the test or hand routine steps back to the user. Install only the needed capability within the task's authority. Package installation, Docker readiness, workload credentials, and session-loaded agents are separate checks; the Smart CLI works without installing every bundle. Stop at actual permission, credential, license, or safety refusals; do not bypass them or silently upgrade shared tools.
5. **Verify and clean up.** Inspect inner command exit status and semantic output, not just the outer wrapper's exit code. If a result is uncertain, inspect it before retrying. Forward only needed credentials by reference, never in logs or evidence. Retain required evidence, account for temporary resources below, and confirm owned cleanup.

## Session Lifecycle

1. Workspace spun up fresh (already done)
2. Work happens in subdirs for anything that persists; root is free for ephemeral cross-repo work
3. Workspace destroyed when done. The root directory does not persist.

Don't store anything that needs **long-term persistance** in the root directory.

## Tracking External Resources

`WORKSPACE-MANIFEST.json` is a **cleanup ledger, not an inventory** of everything created during a task. Record only temporary resources whose cleanup belongs to this workspace and that deleting its directory will not remove. The test is **intended lifetime, not resource type or location**.

- **Track:** temporary DTUs/containers, extra test tmux sessions, scratch Gitea instances/repos, temporary cloud test resources, and task-only files or caches outside the workspace. Record them when created so they are not abandoned running or consuming disk.
- **Do not add durable deliverables** intended to survive the workspace, such as a shared Foundry account, a deployed application, or long-lived project infrastructure. Do not add pre-existing shared services merely because this task uses them. Keep their operational details in the owning project's durable records, not this disposable ledger.
- If the intended lifetime is unclear, clarify it before treating a resource as disposable. Creating something from an ephemeral workspace does not make it temporary.

Add each cleanup liability at the workspace root (create the file if absent); an empty `resources` list is correct when nothing needs cleanup:

```json
{"version": 1, "resources": [{"kind": "dtu", "id": "dtu-a1b2c3d4", "note": "integration test env", "created_at": "2026-01-01T00:00:00Z", "teardown": "amplifier-digital-twin destroy dtu-a1b2c3d4", "status": "active"}]}
```

When this workspace actually tears a tracked resource down, set its `status` to `"reaped"` and add a `reaped_at` timestamp. If it is independently confirmed absent without this workspace tearing it down, use `"observed_absent"` and `observed_absent_at`. Preserve genuine cleanup entries and their history. Before declaring work done, reconcile these entries: any still `"active"` is unfinished cleanup, and destruction requires explicit acknowledgment before leaving it behind. The workspace tool never executes teardown hints itself.

**Correcting a scope mistake:** if a durable resource was added by mistake, verify it is intended to survive, preserve any needed details in the owning project's durable records, and remove only that mistaken entry. Do not mark a live resource `"reaped"` or `"observed_absent"`, invent a retention status, or delete the manifest to bypass other cleanup obligations.

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
