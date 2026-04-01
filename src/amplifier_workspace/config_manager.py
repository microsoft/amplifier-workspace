"""TOML config read/write and CRUD operations for amplifier-workspace."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from .config import CONFIG_PATH


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


def set_nested_setting(key: str, value: Any) -> None:
    """Set *value* for *key* (dot-notation), creating the file if absent."""
    _ensure_config_exists()
    section, sub, leaf = _parse_key(key)
    data = read_config_raw()

    data.setdefault(section, {})
    if leaf is None:
        data[section][sub] = value
    else:
        data[section].setdefault(sub, {})
        data[section][sub][leaf] = value

    write_config_raw(data)


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
            if value not in current:
                raise ValueError(f"{key}: key {value!r} not found")
            del current[value]
            data[section][sub] = current
            write_config_raw(data)
            return f"{key}: removed key {value!r}"
        raise ValueError(f"{key}: setting is not a list or dict")
    else:
        inner = data[section].get(sub, {})
        if leaf not in inner:
            raise ValueError(f"{key}: key {leaf!r} not found")
        del inner[leaf]
        data[section][sub] = inner
        write_config_raw(data)
        return f"{key}: removed key {leaf!r}"
