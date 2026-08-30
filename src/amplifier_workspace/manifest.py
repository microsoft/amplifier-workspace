"""Workspace resource manifest: an honesty ledger for externally spun-up resources.

Workspaces created by ``amplifier-workspace`` are ephemeral and self-contained --
``-d``/``-f`` simply ``rmtree``s the directory.  But sessions working *inside* a
workspace routinely spin up resources that live entirely outside it: a DTU or
container, a tmux session, a Gitea instance or repo, a work-tracker project, a
cloud resource.  ``rmtree`` cannot see any of these, so they get silently
orphaned when the workspace is destroyed.

``WORKSPACE-MANIFEST.json`` (at the workspace root) is a per-workspace ledger
of such resources.  Agents working in the workspace are expected to record a
resource the moment they create it (see ``templates/AGENTS.md``) and mark it
``"reaped"`` once torn down.  Before any destroy (``-d`` or ``-f``), this
module gates the ``rmtree``: if any entry is still unreaped -- or the
manifest cannot be parsed at all -- destruction is refused until the operator
explicitly acknowledges the orphaning by typing "orphan".

This module is pure bookkeeping and a gate.  It never tears a resource down
itself -- mechanism, not policy.  The manifest is tossed along with the rest
of the workspace on a confirmed destroy; its job is only to make destruction
honest.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_FILENAME = "WORKSPACE-MANIFEST.json"
MANIFEST_VERSION = 1

_VALID_STATUSES = ("active", "reaped")
_CONFIRM_WORD = "orphan"


class ManifestError(Exception):
    """WORKSPACE-MANIFEST.json exists but could not be read or parsed."""


# ---------------------------------------------------------------------------
# Resource model
# ---------------------------------------------------------------------------


@dataclass
class ManifestResource:
    """A single externally-managed resource tracked by the manifest."""

    kind: str
    id: str
    created_at: str
    note: str | None = None
    teardown: str | None = None
    status: str = "active"
    reaped_at: str | None = None

    def to_dict(self) -> dict:
        """Serialize in the canonical key order used in WORKSPACE-MANIFEST.json."""
        return {
            "kind": self.kind,
            "id": self.id,
            "note": self.note,
            "created_at": self.created_at,
            "teardown": self.teardown,
            "status": self.status,
            "reaped_at": self.reaped_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ManifestResource:
        """Build a ManifestResource from a (possibly hand-edited) JSON dict.

        Tolerant of missing optional fields.  An unrecognised or missing
        "status" is treated as "active" -- fail closed, so a hand-edited
        entry can never silently slip past the destroy gate by omission.
        """
        status = data.get("status", "active")
        if status not in _VALID_STATUSES:
            status = "active"
        return cls(
            kind=str(data.get("kind", "unknown")),
            id=str(data.get("id", "unknown")),
            created_at=str(data.get("created_at", "")),
            note=data.get("note"),
            teardown=data.get("teardown"),
            status=status,
            reaped_at=data.get("reaped_at"),
        )


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (e.g. 2026-01-01T00:00:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# File scaffolding
# ---------------------------------------------------------------------------


def manifest_path(workdir: Path) -> Path:
    """Return the path to WORKSPACE-MANIFEST.json inside *workdir*."""
    return workdir / MANIFEST_FILENAME


def create_workspace_manifest(workdir: Path) -> None:
    """Write WORKSPACE-MANIFEST.json to *workdir* unless it already exists.

    Idempotent, mirroring ``create_agents_md``/``create_amplifier_settings``
    in ``workspace.py``.  Starts with an empty "resources" list -- there is
    nothing to track until a resource is recorded via ``add_resource`` (or
    by an agent editing the file directly).
    """
    target = manifest_path(workdir)
    if target.exists():
        return
    _write_manifest(workdir, {"version": MANIFEST_VERSION, "resources": []})


def _write_manifest(workdir: Path, data: dict) -> None:
    """Pretty-print *data* to WORKSPACE-MANIFEST.json in *workdir*.

    Human-editable: two-space indent, trailing newline.
    """
    manifest_path(workdir).write_text(json.dumps(data, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Reading and parsing
# ---------------------------------------------------------------------------


def load_manifest(workdir: Path) -> dict | None:
    """Load and parse WORKSPACE-MANIFEST.json from *workdir*.

    Returns None if the file does not exist.  Raises ManifestError if the
    file exists but is not valid JSON, or its top level does not match the
    expected shape (a JSON object with a "resources" list).
    """
    path = manifest_path(workdir)
    if not path.exists():
        return None
    try:
        text = path.read_text()
    except OSError as exc:
        raise ManifestError(f"could not read {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"could not parse {path} as JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("resources"), list):
        raise ManifestError(
            f"{path} does not match the expected manifest shape (a JSON object "
            'with a "resources" list)'
        )
    return data


def _parse_resources(data: dict) -> list[ManifestResource]:
    """Parse the "resources" list of *data* into ManifestResource objects.

    Raises ManifestError if any entry is not itself a JSON object.
    """
    resources: list[ManifestResource] = []
    for entry in data.get("resources", []):
        if not isinstance(entry, dict):
            raise ManifestError(f"resource entry is not a JSON object: {entry!r}")
        resources.append(ManifestResource.from_dict(entry))
    return resources


# ---------------------------------------------------------------------------
# Mutating helpers (scripted use / CLI --add, --reap)
# ---------------------------------------------------------------------------


def add_resource(
    workdir: Path,
    kind: str,
    resource_id: str,
    *,
    note: str | None = None,
    teardown: str | None = None,
) -> ManifestResource:
    """Append a new active resource entry to the workspace manifest.

    Creates WORKSPACE-MANIFEST.json first if it does not yet exist.  Raises
    ManifestError if an existing manifest cannot be parsed.
    """
    create_workspace_manifest(workdir)
    data = load_manifest(workdir)
    assert data is not None  # just created it above, or it already existed

    resource = ManifestResource(
        kind=kind,
        id=resource_id,
        created_at=_now_iso(),
        note=note,
        teardown=teardown,
        status="active",
    )
    data["resources"].append(resource.to_dict())
    _write_manifest(workdir, data)
    return resource


def reap_resource(workdir: Path, resource_id: str) -> ManifestResource:
    """Mark the first resource matching *resource_id* as reaped.

    Raises ManifestError if the manifest is absent or cannot be parsed, or
    ValueError if no resource with that id exists.
    """
    data = load_manifest(workdir)
    if data is None:
        raise ManifestError(f"no {MANIFEST_FILENAME} found in {workdir}")

    for entry in data.get("resources", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == resource_id:
            entry["status"] = "reaped"
            entry["reaped_at"] = _now_iso()
            _write_manifest(workdir, data)
            return ManifestResource.from_dict(entry)

    raise ValueError(
        f"no resource with id {resource_id!r} found in {MANIFEST_FILENAME}"
    )


# ---------------------------------------------------------------------------
# Destroy gate
# ---------------------------------------------------------------------------


def enforce_destroy_gate(workdir: Path) -> None:
    """Refuse to let *workdir* be destroyed while manifest resources are unreaped.

    Called by ``workspace.run_workspace`` before ANY ``rmtree`` of a
    workspace (both ``-d`` and ``-f``).  Behavior:

    - No WORKSPACE-MANIFEST.json present: no-op.  The workspace predates
      this feature, or nothing was ever tracked.
    - Manifest present but unparseable (bad JSON, wrong shape, or a
      non-object resource entry): warn loudly and require the same typed
      confirmation as active resources, since safety cannot be verified.
    - Manifest present, parses fine, and every resource is "reaped" (or the
      resources list is empty): no-op.
    - Manifest present with any resource not marked "reaped": print the
      unreaped resources as a table and require the operator to type
      "orphan" before proceeding.

    Aborts via ``sys.exit(1)`` (printing the standard remediation message)
    if the operator does not confirm.  The tool never tears a resource
    down itself -- this is a gate, not a reaper.
    """
    try:
        data = load_manifest(workdir)
    except ManifestError as exc:
        print(f"warning: {exc}")
        print(
            f"{MANIFEST_FILENAME} exists but could not be read, so it is not "
            "possible to confirm there are no outstanding external resources."
        )
        _confirm_orphan(workdir)
        return

    if data is None:
        return

    try:
        resources = _parse_resources(data)
    except ManifestError as exc:
        print(f"warning: {exc}")
        print(
            f"{MANIFEST_FILENAME} exists but its entries could not be parsed, so "
            "it is not possible to confirm there are no outstanding external "
            "resources."
        )
        _confirm_orphan(workdir)
        return

    active = [r for r in resources if r.status != "reaped"]
    if not active:
        return

    print(f"{MANIFEST_FILENAME} lists {len(active)} unreaped resource(s):")
    print()
    print(_render_table(active))
    print()
    _confirm_orphan(workdir)


def _confirm_orphan(workdir: Path) -> None:
    """Prompt for the typed "orphan" confirmation; exit 1 if not given."""
    print(f"Destroying {workdir} now will ORPHAN the resource(s) above.")
    try:
        answer = input(f'Type "{_CONFIRM_WORD}" to proceed anyway: ')
    except EOFError:
        answer = ""
    if answer.strip().lower() != _CONFIRM_WORD:
        print("reap these first or mark them reaped in WORKSPACE-MANIFEST.json")
        sys.exit(1)


def _render_table(resources: list[ManifestResource]) -> str:
    """Render *resources* as a simple aligned table: kind, id, note, teardown."""
    lines = [f"  {'KIND':<14}{'ID':<26}{'NOTE':<24}TEARDOWN"]
    for r in resources:
        lines.append(f"  {r.kind:<14}{r.id:<26}{(r.note or ''):<24}{r.teardown or ''}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Read-only listing (amplifier-workspace manifest <workdir>)
# ---------------------------------------------------------------------------


def format_manifest_listing(workdir: Path) -> str:
    """Render a human-readable listing of the workspace manifest for *workdir*.

    Always returns a string and never raises -- an absent or corrupt
    manifest is reported as a friendly message rather than an error, so
    the ``amplifier-workspace manifest`` subcommand can always exit 0.
    """
    try:
        data = load_manifest(workdir)
    except ManifestError as exc:
        return f"warning: {exc}\nTreat this workspace's manifest as unreliable until fixed."

    if data is None:
        return f"No {MANIFEST_FILENAME} found in {workdir}."

    try:
        resources = _parse_resources(data)
    except ManifestError as exc:
        return f"warning: {exc}\nTreat this workspace's manifest as unreliable until fixed."

    if not resources:
        return f"{MANIFEST_FILENAME}: 0 resources tracked."

    active = [r for r in resources if r.status != "reaped"]
    reaped = [r for r in resources if r.status == "reaped"]

    lines = [
        (
            f"{MANIFEST_FILENAME}: {len(resources)} resource(s) -- "
            f"{len(active)} active, {len(reaped)} reaped"
        ),
        "",
        f"  {'STATUS':<10}{'KIND':<14}{'ID':<26}{'NOTE':<24}TEARDOWN",
    ]
    for r in active + reaped:  # active first
        lines.append(
            f"  {r.status:<10}{r.kind:<14}{r.id:<26}{(r.note or ''):<24}{r.teardown or ''}"
        )
    return "\n".join(lines)
