"""Tests for manifest.py: scaffolding, read/parse, add/reap, destroy gate, listing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from amplifier_workspace.manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ManifestResource,
    add_resource,
    create_workspace_manifest,
    enforce_destroy_gate,
    format_manifest_listing,
    load_manifest,
    manifest_path,
    reap_resource,
)


def _write_raw(workdir: Path, data: dict | str) -> None:
    """Write raw manifest content (dict is JSON-encoded, str written as-is)."""
    content = json.dumps(data) if isinstance(data, dict) else data
    manifest_path(workdir).write_text(content)


class TestCreateWorkspaceManifest:
    def test_creates_manifest_with_empty_resources(self, tmp_path: Path):
        """Creates WORKSPACE-MANIFEST.json with version 1 and no resources."""
        create_workspace_manifest(tmp_path)
        target = tmp_path / MANIFEST_FILENAME
        assert target.exists()
        data = json.loads(target.read_text())
        assert data == {"version": 1, "resources": []}

    def test_skips_if_already_exists(self, tmp_path: Path):
        """Does not overwrite an existing manifest (idempotent)."""
        _write_raw(tmp_path, {"version": 1, "resources": [{"kind": "x", "id": "y"}]})
        create_workspace_manifest(tmp_path)
        data = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
        assert data["resources"] == [{"kind": "x", "id": "y"}]

    def test_pretty_printed(self, tmp_path: Path):
        """The written file is indented (human-editable), not a single line."""
        create_workspace_manifest(tmp_path)
        text = (tmp_path / MANIFEST_FILENAME).read_text()
        assert "\n" in text
        assert text.endswith("\n")


class TestLoadManifest:
    def test_returns_none_when_absent(self, tmp_path: Path):
        """Returns None when no manifest file exists."""
        assert load_manifest(tmp_path) is None

    def test_parses_valid_manifest(self, tmp_path: Path):
        """Returns the parsed dict for a well-formed manifest."""
        _write_raw(tmp_path, {"version": 1, "resources": [{"kind": "dtu", "id": "a"}]})
        data = load_manifest(tmp_path)
        assert data is not None
        assert data["resources"][0]["id"] == "a"

    def test_raises_on_invalid_json(self, tmp_path: Path):
        """Raises ManifestError when the file is not valid JSON."""
        _write_raw(tmp_path, "{not valid json")
        with pytest.raises(ManifestError):
            load_manifest(tmp_path)

    def test_raises_on_missing_resources_key(self, tmp_path: Path):
        """Raises ManifestError when the top-level shape has no resources list."""
        _write_raw(tmp_path, {"version": 1})
        with pytest.raises(ManifestError):
            load_manifest(tmp_path)

    def test_raises_on_non_list_resources(self, tmp_path: Path):
        """Raises ManifestError when "resources" is not a list."""
        _write_raw(tmp_path, {"version": 1, "resources": "nope"})
        with pytest.raises(ManifestError):
            load_manifest(tmp_path)

    def test_raises_on_non_dict_top_level(self, tmp_path: Path):
        """Raises ManifestError when the top level is a JSON array, not an object."""
        _write_raw(tmp_path, "[1, 2, 3]")
        with pytest.raises(ManifestError):
            load_manifest(tmp_path)


class TestManifestResourceFromDict:
    def test_tolerant_of_missing_optional_fields(self):
        """Missing note/teardown/reaped_at default to None."""
        r = ManifestResource.from_dict({"kind": "dtu", "id": "a"})
        assert r.note is None
        assert r.teardown is None
        assert r.reaped_at is None

    def test_missing_status_defaults_to_active(self):
        """A hand-edited entry with no 'status' key is treated as active (fail closed)."""
        r = ManifestResource.from_dict({"kind": "dtu", "id": "a"})
        assert r.status == "active"

    def test_unknown_status_value_defaults_to_active(self):
        """An unrecognised status string is treated as active, not silently accepted."""
        r = ManifestResource.from_dict({"kind": "dtu", "id": "a", "status": "bogus"})
        assert r.status == "active"

    def test_reaped_status_preserved(self):
        """A well-formed 'reaped' status round-trips correctly."""
        r = ManifestResource.from_dict({"kind": "dtu", "id": "a", "status": "reaped"})
        assert r.status == "reaped"


class TestAddResource:
    def test_creates_manifest_if_absent_then_adds(self, tmp_path: Path):
        """add_resource scaffolds the manifest first if it doesn't exist."""
        add_resource(tmp_path, "dtu", "dtu-1")
        data = load_manifest(tmp_path)
        assert data is not None
        assert len(data["resources"]) == 1
        assert data["resources"][0]["id"] == "dtu-1"

    def test_new_resource_is_active_with_timestamp(self, tmp_path: Path):
        """A newly added resource is active and has a created_at timestamp."""
        resource = add_resource(tmp_path, "dtu", "dtu-1")
        assert resource.status == "active"
        assert resource.created_at != ""

    def test_note_and_teardown_recorded(self, tmp_path: Path):
        """Optional note and teardown hint are stored."""
        add_resource(
            tmp_path,
            "gitea-repo",
            "myorg/myrepo",
            note="scratch repo",
            teardown="delete via gitea UI",
        )
        data = load_manifest(tmp_path)
        entry = data["resources"][0]
        assert entry["note"] == "scratch repo"
        assert entry["teardown"] == "delete via gitea UI"

    def test_appends_without_clobbering_existing_entries(self, tmp_path: Path):
        """Adding a second resource keeps the first one intact."""
        add_resource(tmp_path, "dtu", "dtu-1")
        add_resource(tmp_path, "tmux", "sess-1")
        data = load_manifest(tmp_path)
        ids = [r["id"] for r in data["resources"]]
        assert ids == ["dtu-1", "sess-1"]


class TestReapResource:
    def test_marks_matching_resource_reaped(self, tmp_path: Path):
        """reap_resource sets status to reaped and stamps reaped_at."""
        add_resource(tmp_path, "dtu", "dtu-1")
        reaped = reap_resource(tmp_path, "dtu-1")
        assert reaped.status == "reaped"
        assert reaped.reaped_at is not None

        data = load_manifest(tmp_path)
        assert data["resources"][0]["status"] == "reaped"

    def test_raises_value_error_when_id_not_found(self, tmp_path: Path):
        """Raises ValueError for an id that isn't in the manifest."""
        add_resource(tmp_path, "dtu", "dtu-1")
        with pytest.raises(ValueError, match="no resource with id"):
            reap_resource(tmp_path, "does-not-exist")

    def test_raises_manifest_error_when_absent(self, tmp_path: Path):
        """Raises ManifestError when there is no manifest to reap from."""
        with pytest.raises(ManifestError):
            reap_resource(tmp_path, "dtu-1")


class TestEnforceDestroyGate:
    def test_noop_when_manifest_absent(self, tmp_path: Path, monkeypatch):
        """Returns immediately (no prompt) when no manifest file exists."""
        prompted = {"called": False}
        monkeypatch.setattr(
            "builtins.input", lambda *_: prompted.update(called=True) or ""
        )
        enforce_destroy_gate(tmp_path)  # must not raise
        assert prompted["called"] is False

    def test_noop_when_resources_empty(self, tmp_path: Path, monkeypatch):
        """Returns immediately when the manifest exists but has no resources."""
        create_workspace_manifest(tmp_path)
        prompted = {"called": False}
        monkeypatch.setattr(
            "builtins.input", lambda *_: prompted.update(called=True) or ""
        )
        enforce_destroy_gate(tmp_path)
        assert prompted["called"] is False

    def test_noop_when_all_resources_reaped(self, tmp_path: Path, monkeypatch):
        """Returns immediately when every tracked resource is already reaped."""
        add_resource(tmp_path, "dtu", "dtu-1")
        reap_resource(tmp_path, "dtu-1")
        prompted = {"called": False}
        monkeypatch.setattr(
            "builtins.input", lambda *_: prompted.update(called=True) or ""
        )
        enforce_destroy_gate(tmp_path)
        assert prompted["called"] is False

    def test_aborts_when_active_resource_and_confirmation_declined(
        self, tmp_path: Path, monkeypatch
    ):
        """Exits with code 1 when an active resource exists and 'orphan' is not typed."""
        add_resource(tmp_path, "dtu", "dtu-1")
        monkeypatch.setattr("builtins.input", lambda *_: "no")
        with pytest.raises(SystemExit) as exc_info:
            enforce_destroy_gate(tmp_path)
        assert exc_info.value.code == 1

    def test_proceeds_when_active_resource_and_orphan_typed(
        self, tmp_path: Path, monkeypatch
    ):
        """Returns normally when the operator types the exact confirmation word."""
        add_resource(tmp_path, "dtu", "dtu-1")
        monkeypatch.setattr("builtins.input", lambda *_: "orphan")
        enforce_destroy_gate(tmp_path)  # must not raise

    def test_confirmation_is_case_insensitive_and_stripped(
        self, tmp_path: Path, monkeypatch
    ):
        """'Orphan' / ' orphan ' etc. are accepted, not just an exact lowercase match."""
        add_resource(tmp_path, "dtu", "dtu-1")
        monkeypatch.setattr("builtins.input", lambda *_: "  ORPHAN  ")
        enforce_destroy_gate(tmp_path)  # must not raise

    def test_aborts_on_eof(self, tmp_path: Path, monkeypatch):
        """Exits with code 1 when stdin is closed (EOFError) instead of hanging."""
        add_resource(tmp_path, "dtu", "dtu-1")

        def _raise_eof(*_args, **_kwargs):
            raise EOFError

        monkeypatch.setattr("builtins.input", _raise_eof)
        with pytest.raises(SystemExit) as exc_info:
            enforce_destroy_gate(tmp_path)
        assert exc_info.value.code == 1

    def test_requires_confirmation_on_corrupt_manifest(
        self, tmp_path: Path, monkeypatch
    ):
        """A manifest that fails to parse still requires 'orphan' -- fail safe, not silent."""
        _write_raw(tmp_path, "{not valid json")
        monkeypatch.setattr("builtins.input", lambda *_: "no")
        with pytest.raises(SystemExit) as exc_info:
            enforce_destroy_gate(tmp_path)
        assert exc_info.value.code == 1

    def test_corrupt_manifest_confirmation_accepted(self, tmp_path: Path, monkeypatch):
        """Typing 'orphan' on a corrupt manifest proceeds without raising."""
        _write_raw(tmp_path, "{not valid json")
        monkeypatch.setattr("builtins.input", lambda *_: "orphan")
        enforce_destroy_gate(tmp_path)  # must not raise

    def test_requires_confirmation_when_resource_entry_not_a_dict(
        self, tmp_path: Path, monkeypatch
    ):
        """A malformed (non-object) resource entry is treated like a corrupt manifest."""
        _write_raw(tmp_path, {"version": 1, "resources": ["not-an-object"]})
        monkeypatch.setattr("builtins.input", lambda *_: "no")
        with pytest.raises(SystemExit):
            enforce_destroy_gate(tmp_path)


class TestFormatManifestListing:
    def test_reports_absent_manifest(self, tmp_path: Path):
        """Never raises; reports a friendly message when nothing is tracked."""
        message = format_manifest_listing(tmp_path)
        assert "No WORKSPACE-MANIFEST.json" in message

    def test_reports_empty_resources(self, tmp_path: Path):
        """Reports zero resources tracked when the manifest is freshly scaffolded."""
        create_workspace_manifest(tmp_path)
        message = format_manifest_listing(tmp_path)
        assert "0 resources tracked" in message

    def test_reports_corrupt_manifest_without_raising(self, tmp_path: Path):
        """A corrupt manifest is reported as a warning string, never an exception."""
        _write_raw(tmp_path, "{not valid json")
        message = format_manifest_listing(tmp_path)
        assert "warning" in message.lower()

    def test_lists_active_and_reaped_with_counts(self, tmp_path: Path):
        """Listing shows both active and reaped resources, with a summary count."""
        add_resource(tmp_path, "dtu", "dtu-1")
        add_resource(tmp_path, "tmux", "sess-1")
        reap_resource(tmp_path, "sess-1")

        message = format_manifest_listing(tmp_path)
        assert "2 resource(s)" in message
        assert "1 active" in message
        assert "1 reaped" in message
        assert "dtu-1" in message
        assert "sess-1" in message

    def test_active_listed_before_reaped(self, tmp_path: Path):
        """Active resources are listed before reaped ones, regardless of insertion order."""
        add_resource(tmp_path, "dtu", "dtu-1")
        reap_resource(tmp_path, "dtu-1")
        add_resource(tmp_path, "tmux", "sess-1")  # active, added after the reaped one

        message = format_manifest_listing(tmp_path)
        assert message.index("sess-1") < message.index("dtu-1")
