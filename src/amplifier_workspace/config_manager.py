"""TOML config read/write and CRUD operations for amplifier-workspace."""

from __future__ import annotations

import difflib
import importlib.resources
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from .config import (
    CONFIG_PATH,
    DEFAULT_BUNDLE,
    DEFAULT_REPOS,
    DEFAULT_WINDOWS,
    load_config,
)

# ---------------------------------------------------------------------------
# Schema: the set of keys config understands (defect 2 — reject typo'd keys)
# ---------------------------------------------------------------------------

# Fixed scalar keys and their value type.
_KEY_TYPES: dict[str, str] = {
    "workspace.bundle": "str",
    "workspace.default_repos": "list",
    "workspace.agents_template": "str",
    "tmux.enabled": "bool",
}

# Dynamic dict sections: any leaf under one of these prefixes is a legal key
# of the given type (e.g. ``tmux.windows.<name>`` -> str).
_DYNAMIC_DICT_PREFIXES: dict[str, str] = {
    "tmux.windows": "str",
}

_BOOL_TRUE = {"true", "1", "yes"}
_BOOL_FALSE = {"false", "0", "no"}


class ConfigKeyError(Exception):
    """Raised when a config key is not part of the schema.

    Carries the offending key, the full valid-keys list, and any close-match
    suggestions so the CLI can render a helpful ``did you mean ...?`` message
    and exit with a usage error.
    """

    def __init__(self, key: str, valid_keys: list[str], suggestions: list[str]) -> None:
        self.key = key
        self.valid_keys = valid_keys
        self.suggestions = suggestions
        message = f"unknown config key: {key!r}"
        if suggestions:
            message += f" (did you mean {suggestions[0]}?)"
        super().__init__(message)


class ConfigValueError(Exception):
    """Raised when a value cannot be coerced/validated for its key's type."""


def known_keys() -> list[str]:
    """Return the human-facing list of valid keys (dynamic prefixes shown as <name>)."""
    keys = list(_KEY_TYPES.keys())
    keys += [f"{prefix}.<name>" for prefix in _DYNAMIC_DICT_PREFIXES]
    return keys


def is_dynamic_dict_leaf(key: str) -> bool:
    """Return True if *key* is a 3-part leaf under a dynamic dict prefix."""
    parts = key.split(".")
    return (
        len(parts) == 3
        and bool(parts[2])
        and f"{parts[0]}.{parts[1]}" in _DYNAMIC_DICT_PREFIXES
    )


def key_type(key: str) -> str | None:
    """Return the schema type of *key* ('str' | 'bool' | 'list'), or None if unknown."""
    if key in _KEY_TYPES:
        return _KEY_TYPES[key]
    if is_dynamic_dict_leaf(key):
        parts = key.split(".")
        return _DYNAMIC_DICT_PREFIXES[f"{parts[0]}.{parts[1]}"]
    return None


def is_known_key(key: str) -> bool:
    """Return True if *key* is part of the schema."""
    return key_type(key) is not None


def is_addable_key(key: str) -> bool:
    """Return True if *key* is a list key or a dynamic dict leaf (valid for ``add``)."""
    return key_type(key) == "list" or is_dynamic_dict_leaf(key)


def suggest_keys(key: str) -> list[str]:
    """Return up to 3 close-match suggestions for an unknown *key* (difflib)."""
    candidates = list(_KEY_TYPES.keys()) + list(_DYNAMIC_DICT_PREFIXES.keys())
    return difflib.get_close_matches(key, candidates, n=3, cutoff=0.5)


def validate_key(key: str) -> str:
    """Return the schema type of *key*, or raise ConfigKeyError if unknown."""
    kind = key_type(key)
    if kind is None:
        raise ConfigKeyError(key, known_keys(), suggest_keys(key))
    return kind


def coerce_for_set(key: str, raw: str) -> Any:
    """Coerce a raw string *raw* to the type *key* expects (for ``config set``).

    - bool keys accept true/false/1/0/yes/no (case-insensitive).
    - list keys are rejected (use ``config add`` / ``config remove``).
    - str keys pass through unchanged.

    Raises ConfigValueError on an unacceptable value or a list key.
    """
    kind = key_type(key)
    if kind == "list":
        raise ConfigValueError(
            f"{key} is a list — use 'config add {key} <value>' or "
            f"'config remove {key} <value>'"
        )
    if kind == "bool":
        low = raw.strip().lower()
        if low in _BOOL_TRUE:
            return True
        if low in _BOOL_FALSE:
            return False
        raise ConfigValueError(
            f"{key} expects a boolean (true/false/1/0/yes/no), got {raw!r}"
        )
    # str (fixed or dynamic dict leaf)
    return raw


def _display_value(val: Any) -> str:
    """Render a value for human-facing messages (no Python repr)."""
    if val is None:
        return "unset"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, dict):
        return ", ".join(f"{k}={v}" for k, v in val.items()) or "(empty)"
    if isinstance(val, list):
        return ", ".join(str(x) for x in val) or "(empty)"
    return str(val)


# ---------------------------------------------------------------------------
# Low-level TOML serialisation helpers
# ---------------------------------------------------------------------------


def _toml_value(val: Any) -> str:
    """Serialize a Python value to its TOML inline representation."""
    # bool must be checked before int because bool is a subclass of int
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        if not val:
            return "[]"
        items = ", ".join(_toml_value(item) for item in val)
        return f"[{items}]"
    # Fallback for unexpected types
    return str(val)


# ---------------------------------------------------------------------------
# Raw read / write
# ---------------------------------------------------------------------------


def config_exists() -> bool:
    """Return True if the config file exists on disk."""
    return CONFIG_PATH.exists()


def read_config_raw(path: Path | None = None) -> dict:
    """Read the TOML config file and return the raw dict.

    Returns an empty dict when the file is missing.
    """
    p = path if path is not None else CONFIG_PATH
    if not p.exists():
        return {}
    with p.open("rb") as fh:
        return tomllib.load(fh)


def write_config(data: dict) -> None:
    """Write *data* dict to the default config file location.

    Convenience wrapper around ``write_config_raw`` for callers (e.g. the
    wizard) that always write to ``CONFIG_PATH``.
    """
    write_config_raw(data)


def write_config_raw(data: dict, path: Path | None = None) -> None:
    """Write *data* to the TOML config file.

    Handles one level of nesting: a nested dict value inside a section
    is written as a ``[section.subsection]`` header.
    """
    p = path if path is not None else CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for section, section_data in data.items():
        flat = {k: v for k, v in section_data.items() if not isinstance(v, dict)}
        nested = {k: v for k, v in section_data.items() if isinstance(v, dict)}

        lines.append(f"[{section}]")
        for k, v in flat.items():
            lines.append(f"{k} = {_toml_value(v)}")

        for subsection, subdata in nested.items():
            lines.append("")
            lines.append(f"[{section}.{subsection}]")
            for k, v in subdata.items():
                lines.append(f"{k} = {_toml_value(v)}")

        lines.append("")

    p.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Key parsing
# ---------------------------------------------------------------------------


def _parse_key(key: str) -> tuple[str, str, str | None]:
    """Split a dot-notation key into (section, subsection_or_key, leaf|None).

    * 2-part key ``"workspace.bundle"``   → ``("workspace", "bundle", None)``
    * 3-part key ``"tmux.windows.main"``  → ``("tmux", "windows", "main")``

    Raises ValueError if the key has fewer than 2 parts.
    """
    parts = key.split(".")
    if len(parts) < 2:
        raise ValueError(f"Key must have at least two dot-separated parts: {key!r}")
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], parts[2]


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def _ensure_config_exists() -> None:
    """Seed the config file from the bundled default-config.toml if absent."""
    if CONFIG_PATH.exists():
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        pkg = (
            importlib.resources.files("amplifier_workspace")
            / "templates"
            / "default-config.toml"
        )
        CONFIG_PATH.write_bytes(pkg.read_bytes())
    except Exception:
        # If the template is missing, create an empty file so the key can be set
        CONFIG_PATH.write_text("")


def get_nested_setting(key: str) -> Any:
    """Return the value for *key* (dot-notation) from the config file.

    Returns ``None`` if the file or key is missing.
    """
    section, sub, leaf = _parse_key(key)
    data = read_config_raw()
    if leaf is None:
        return data.get(section, {}).get(sub)
    return data.get(section, {}).get(sub, {}).get(leaf)


def set_nested_setting(key: str, value: Any) -> str:
    """Set *value* for *key* (dot-notation), creating the file if absent.

    Returns a human-readable ``key = new (was old)`` change message so callers
    can report exactly what happened (defect 6 — successful set printed nothing).
    """
    _ensure_config_exists()
    section, sub, leaf = _parse_key(key)
    data = read_config_raw()

    data.setdefault(section, {})
    if leaf is None:
        old = data[section].get(sub)
        data[section][sub] = value
    else:
        data[section].setdefault(sub, {})
        old = data[section][sub].get(leaf)
        data[section][sub][leaf] = value

    write_config_raw(data)
    return f"{key} = {_display_value(value)} (was {_display_value(old)})"


def add_to_setting(key: str, value: Any) -> str:
    """Append *value* to a list setting or add a key to a dict setting.

    No duplicate list entries are added.  Returns a human-readable message.
    """
    _ensure_config_exists()
    section, sub, leaf = _parse_key(key)
    data = read_config_raw()
    data.setdefault(section, {})

    if leaf is None:
        current = data[section].get(sub)
        if isinstance(current, list):
            if value in current:
                return f"{key}: {value!r} already present (no change)"
            current.append(value)
            data[section][sub] = current
            write_config_raw(data)
            return f"{key}: added {value!r}"
        if isinstance(current, dict):
            if not isinstance(value, dict):
                raise ValueError("Must supply a dict to add to a dict setting")
            current.update(value)
            data[section][sub] = current
            write_config_raw(data)
            return f"{key}: added {list(value.keys())}"
        # Scalar — replace
        data[section][sub] = value
        write_config_raw(data)
        return f"{key}: set to {value!r}"
    else:
        data[section].setdefault(sub, {})
        current = data[section][sub]
        if isinstance(current, dict):
            current[leaf] = value
            write_config_raw(data)
            return f"{key}: set to {value!r}"
        raise ValueError(f"Cannot add to non-dict subsection at {key!r}")


def remove_from_setting(key: str, value: Any = None) -> str:
    """Remove *value* from a list (or by index) or remove a dict entry.

    Returns a human-readable message.  Raises ValueError for missing items.
    """
    _ensure_config_exists()
    section, sub, leaf = _parse_key(key)
    data = read_config_raw()
    data.setdefault(section, {})

    if leaf is None:
        current = data[section].get(sub)
        if isinstance(current, list):
            if value is None:
                raise ValueError(
                    f"{key}: provide a value to remove from the list "
                    f"(e.g. 'config remove {key} <value>')"
                )
            if isinstance(value, int):
                if value < 0 or value >= len(current):
                    raise ValueError(f"{key}: index {value} out of range")
                removed = current.pop(value)
                data[section][sub] = current
                write_config_raw(data)
                return f"{key}: removed index {value} ({removed!r})"
            if value not in current:
                raise ValueError(f"{key}: {value!r} not found")
            current.remove(value)
            data[section][sub] = current
            write_config_raw(data)
            return f"{key}: removed {value!r}"
        if isinstance(current, dict):
            if value is None:
                raise ValueError(
                    f"{key}: provide the sub-key to remove "
                    f"(e.g. 'config remove {key}.<name>')"
                )
            if value not in current:
                raise ValueError(f"{key}: key {value!r} not found")
            del current[value]
            data[section][sub] = current
            write_config_raw(data)
            return f"{key}: removed key {value!r}"
        if sub in data.get(section, {}):
            # Scalar key (e.g. a bogus 'tmux.enable' typo) — remove it wholesale.
            old = data[section][sub]
            del data[section][sub]
            write_config_raw(data)
            return f"{key}: removed (was {_display_value(old)})"
        raise ValueError(f"{key}: not found")
    else:
        inner = data[section].get(sub, {})
        if leaf not in inner:
            raise ValueError(f"{key}: key {leaf!r} not found")
        del inner[leaf]
        data[section][sub] = inner
        write_config_raw(data)
        return f"{key}: removed key {leaf!r}"


def key_exists_in_file(key: str, path: Path | None = None) -> bool:
    """Return True if *key* is physically present in the config file on disk.

    Used so ``config remove`` can clean up a bogus key (defect 7) even though
    that key is not part of the schema.
    """
    data = read_config_raw(path)
    parts = key.split(".")
    if len(parts) == 2:
        return isinstance(data.get(parts[0]), dict) and parts[1] in data[parts[0]]
    if len(parts) == 3:
        section = data.get(parts[0], {})
        sub = section.get(parts[1], {}) if isinstance(section, dict) else {}
        return isinstance(sub, dict) and parts[2] in sub
    return False


def format_get_value(val: Any) -> str:
    """Render a value for ``config get`` (lists one-per-line, no Python repr)."""
    if isinstance(val, list):
        return "\n".join(str(x) for x in val)
    return _display_value(val)


# ---------------------------------------------------------------------------
# Human-readable listing (config list) — defect 4
# ---------------------------------------------------------------------------


def _flag_unknown_keys(raw_section: Any, section_name: str) -> list[str]:
    """Return '# unknown key (ignored): ...' lines for unknown scalar keys."""
    lines: list[str] = []
    if not isinstance(raw_section, dict):
        return lines
    for k, v in raw_section.items():
        full = f"{section_name}.{k}"
        # A nested dict under a known dynamic prefix (e.g. tmux.windows) is fine.
        if full in _DYNAMIC_DICT_PREFIXES and isinstance(v, dict):
            continue
        if full not in _KEY_TYPES:
            lines.append(f"# unknown key (ignored): {full}")
    return lines


def format_config_listing(path: Path | None = None) -> str:
    """Render the effective config grouped by section (defect 4).

    - File path shown as a header comment.
    - List values printed one-per-line, indented (never a Python list repr).
    - Keys present in the TOML but not in the schema are flagged inline.
    """
    p = path if path is not None else CONFIG_PATH
    raw = read_config_raw(p)
    cfg = load_config(p)

    lines: list[str] = []
    if p.exists():
        lines.append(f"# config: {p}")
    else:
        lines.append("# config: (none yet — showing defaults)")

    # [workspace]
    lines.append("[workspace]")
    lines.append(f"bundle = {cfg.bundle}")
    if cfg.default_repos:
        lines.append("default_repos =")
        lines.extend(f"    {repo}" for repo in cfg.default_repos)
    else:
        lines.append("default_repos = (empty)")
    lines.append(f"agents_template = {cfg.agents_template or '(unset)'}")
    lines.extend(_flag_unknown_keys(raw.get("workspace"), "workspace"))

    # [tmux]
    lines.append("")
    lines.append("[tmux]")
    lines.append(f"enabled = {'true' if cfg.tmux.enabled else 'false'}")
    lines.extend(_flag_unknown_keys(raw.get("tmux"), "tmux"))

    # [tmux.windows]
    lines.append("")
    lines.append("[tmux.windows]")
    if isinstance(cfg.tmux.windows, dict):
        for name, command in cfg.tmux.windows.items():
            lines.append(f"{name} = {command}")

    # Any wholly-unknown top-level sections.
    for section_name, section_data in raw.items():
        if section_name in ("workspace", "tmux"):
            continue
        if isinstance(section_data, dict):
            lines.extend(
                f"# unknown key (ignored): {section_name}.{k}" for k in section_data
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reset with backup + diff display — defect 5
# ---------------------------------------------------------------------------


def default_config_dict() -> dict:
    """Return the canonical default configuration as a raw dict."""
    return {
        "workspace": {
            "default_repos": list(DEFAULT_REPOS),
            "bundle": DEFAULT_BUNDLE,
            "agents_template": "",
        },
        "tmux": {
            "enabled": False,
            "windows": dict(DEFAULT_WINDOWS),
        },
    }


def diff_from_defaults(path: Path | None = None) -> list[tuple[str, Any, Any]]:
    """Return (key, current, default) tuples for every setting that differs.

    Powers the 'here is what you would lose' display before a reset.
    """
    cfg = load_config(path if path is not None else CONFIG_PATH)
    diffs: list[tuple[str, Any, Any]] = []
    if cfg.bundle != DEFAULT_BUNDLE:
        diffs.append(("workspace.bundle", cfg.bundle, DEFAULT_BUNDLE))
    if list(cfg.default_repos) != list(DEFAULT_REPOS):
        diffs.append(("workspace.default_repos", cfg.default_repos, DEFAULT_REPOS))
    if cfg.agents_template != "":
        diffs.append(("workspace.agents_template", cfg.agents_template, ""))
    if cfg.tmux.enabled is not False:
        diffs.append(("tmux.enabled", cfg.tmux.enabled, False))
    if dict(cfg.tmux.windows) != dict(DEFAULT_WINDOWS):
        diffs.append(("tmux.windows", cfg.tmux.windows, DEFAULT_WINDOWS))
    return diffs


def backup_config(path: Path | None = None) -> Path | None:
    """Copy the existing config to ``config.toml.bak-<UTCstamp>``.

    Returns the backup path, or None if there was no file to back up.
    """
    p = path if path is not None else CONFIG_PATH
    if not p.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = p.with_name(f"{p.name}.bak-{stamp}")
    backup.write_bytes(p.read_bytes())
    return backup


def write_default_config(path: Path | None = None) -> None:
    """Write the canonical defaults to the config file (used by reset)."""
    write_config_raw(default_config_dict(), path)
