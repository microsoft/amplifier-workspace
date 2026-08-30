"""Tests for config_manager.py: _toml_value serializer, read/write roundtrip, and CRUD."""

import pytest


class TestTomlValue:
    def test_bool_true(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value(True) == "true"

    def test_bool_false(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value(False) == "false"

    def test_string_plain(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value("hello") == '"hello"'

    def test_string_with_double_quotes(self):
        from amplifier_workspace.config_manager import _toml_value

        # Python string: say "hi"  →  TOML: "say \"hi\""
        assert _toml_value('say "hi"') == r'"say \"hi\""'

    def test_string_with_backslash(self):
        from amplifier_workspace.config_manager import _toml_value

        # Python string contains one backslash → TOML doubles it: "back\\slash"
        assert _toml_value("back\\slash") == '"back\\\\slash"'

    def test_integer(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value(42) == "42"

    def test_float(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value(3.14) == "3.14"

    def test_list_of_strings(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value(["a", "b", "c"]) == '["a", "b", "c"]'

    def test_empty_list(self):
        from amplifier_workspace.config_manager import _toml_value

        assert _toml_value([]) == "[]"

    def test_list_of_urls(self):
        from amplifier_workspace.config_manager import _toml_value

        urls = [
            "https://github.com/foo/bar.git",
            "https://github.com/baz/qux.git",
        ]
        result = _toml_value(urls)
        assert (
            result
            == '["https://github.com/foo/bar.git", "https://github.com/baz/qux.git"]'
        )


class TestReadWriteConfigRaw:
    def test_read_returns_empty_dict_when_file_missing(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        monkeypatch.setattr(
            config_manager, "CONFIG_PATH", tmp_path / "nonexistent.toml"
        )
        result = config_manager.read_config_raw()
        assert result == {}

    def test_write_creates_file_and_directory(self, tmp_path):
        from amplifier_workspace.config_manager import write_config_raw

        target = tmp_path / "subdir" / "config.toml"
        data = {"workspace": {"bundle": "test"}}
        write_config_raw(data, path=target)
        assert target.exists()

    def test_write_produces_workspace_section_header(self, tmp_path):
        from amplifier_workspace.config_manager import write_config_raw

        target = tmp_path / "config.toml"
        data = {"workspace": {"bundle": "my-bundle"}}
        write_config_raw(data, path=target)
        content = target.read_text()
        assert "[workspace]" in content
        assert 'bundle = "my-bundle"' in content

    def test_write_handles_nested_tmux_windows(self, tmp_path):
        from amplifier_workspace.config_manager import write_config_raw

        target = tmp_path / "config.toml"
        data = {
            "tmux": {
                "enabled": False,
                "windows": {"amplifier": "", "shell": ""},
            }
        }
        write_config_raw(data, path=target)
        content = target.read_text()
        assert "[tmux]" in content
        assert "[tmux.windows]" in content
        assert 'amplifier = ""' in content

    def test_roundtrip_preserves_values(self, tmp_path):
        from amplifier_workspace.config_manager import read_config_raw, write_config_raw

        data = {
            "workspace": {
                "bundle": "my-bundle",
                "default_repos": ["https://github.com/foo/bar.git"],
            },
            "tmux": {
                "enabled": True,
                "windows": {"main": "vim ."},
            },
        }
        target = tmp_path / "config.toml"
        write_config_raw(data, path=target)
        result = read_config_raw(path=target)

        assert result["workspace"]["bundle"] == "my-bundle"
        assert result["workspace"]["default_repos"] == [
            "https://github.com/foo/bar.git"
        ]
        assert result["tmux"]["enabled"] is True
        assert result["tmux"]["windows"]["main"] == "vim ."


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


class TestParseKey:
    def test_two_parts_returns_section_key_none(self):
        from amplifier_workspace.config_manager import _parse_key

        assert _parse_key("workspace.bundle") == ("workspace", "bundle", None)

    def test_three_parts_returns_section_key_nested(self):
        from amplifier_workspace.config_manager import _parse_key

        assert _parse_key("tmux.windows.main") == ("tmux", "windows", "main")

    def test_single_part_raises_value_error_with_dot_message(self):
        from amplifier_workspace.config_manager import _parse_key

        with pytest.raises(ValueError, match="dot"):
            _parse_key("workspace")


class TestGetSetNestedSetting:
    def test_set_and_get_scalar(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        config_manager.set_nested_setting("tmux.enabled", True)
        assert config_manager.get_nested_setting("tmux.enabled") is True

    def test_set_and_get_string(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        config_manager.set_nested_setting("workspace.bundle", "my-bundle")
        assert config_manager.get_nested_setting("workspace.bundle") == "my-bundle"

    def test_set_nested_dict_entry(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        config_manager.set_nested_setting("tmux.windows.git", "lazygit")
        assert config_manager.get_nested_setting("tmux.windows.git") == "lazygit"

    def test_get_missing_key_returns_none(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        config_path.write_text("")
        assert config_manager.get_nested_setting("workspace.nonexistent") is None

    def test_creates_file_on_first_write(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        assert not config_path.exists()
        config_manager.set_nested_setting("workspace.bundle", "test")
        assert config_path.exists()


class TestAddToSetting:
    def test_add_to_existing_list(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": ["repo1"]}}, path=config_path)
        config_manager.add_to_setting("workspace.default_repos", "repo2")
        result = config_manager.get_nested_setting("workspace.default_repos")
        assert "repo2" in result

    def test_add_duplicate_returns_already_message(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": ["repo1"]}}, path=config_path)
        msg = config_manager.add_to_setting("workspace.default_repos", "repo1")
        assert "already" in msg.lower()

    def test_add_dict_entry(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        config_path.write_text("")
        config_manager.add_to_setting("tmux.windows.git", "lazygit")
        assert config_manager.get_nested_setting("tmux.windows.git") == "lazygit"


class TestRemoveFromSetting:
    def test_remove_from_list_by_value(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw(
            {"workspace": {"default_repos": ["repo1", "repo2"]}}, path=config_path
        )
        msg = config_manager.remove_from_setting("workspace.default_repos", "repo1")
        result = config_manager.get_nested_setting("workspace.default_repos")
        assert "repo1" not in result
        assert "repo1" in msg

    def test_remove_from_list_by_index(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw(
            {"workspace": {"default_repos": ["repo1", "repo2"]}}, path=config_path
        )
        msg = config_manager.remove_from_setting("workspace.default_repos", 0)
        assert "index 0" in msg
        assert "repo1" in msg

    def test_remove_dict_entry(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw({"tmux": {"windows": {"git": "lazygit"}}}, path=config_path)
        config_manager.remove_from_setting("tmux.windows.git")
        assert config_manager.get_nested_setting("tmux.windows.git") is None

    def test_remove_nonexistent_raises_value_error_with_not_found(
        self, monkeypatch, tmp_path
    ):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw({"workspace": {"default_repos": ["repo1"]}}, path=config_path)
        with pytest.raises(ValueError, match="not found"):
            config_manager.remove_from_setting("workspace.default_repos", "nonexistent")

    def test_remove_scalar_key_deletes_bogus_key(self, monkeypatch, tmp_path):
        """A bogus scalar key (defect 7) can be removed with no value."""
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        # 'tmux.enable' is the classic defect-2 typo written as a string.
        write_config_raw(
            {"tmux": {"enable": "True", "enabled": True}}, path=config_path
        )
        msg = config_manager.remove_from_setting("tmux.enable")
        assert "removed" in msg
        assert config_manager.get_nested_setting("tmux.enable") is None
        # The real key is untouched.
        assert config_manager.get_nested_setting("tmux.enabled") is True

    def test_remove_missing_scalar_key_raises_not_found(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
        write_config_raw({"tmux": {"enabled": True}}, path=config_path)
        with pytest.raises(ValueError, match="not found"):
            config_manager.remove_from_setting("tmux.enable")


# ---------------------------------------------------------------------------
# Schema validation, coercion, suggestions (defects 2, 3)
# ---------------------------------------------------------------------------


class TestKeySchema:
    def test_known_scalar_keys_have_types(self):
        from amplifier_workspace import config_manager as cm

        assert cm.key_type("workspace.bundle") == "str"
        assert cm.key_type("workspace.default_repos") == "list"
        assert cm.key_type("tmux.enabled") == "bool"

    def test_dynamic_window_leaf_is_known_str(self):
        from amplifier_workspace import config_manager as cm

        assert cm.key_type("tmux.windows.git") == "str"
        assert cm.is_dynamic_dict_leaf("tmux.windows.git") is True
        assert cm.is_known_key("tmux.windows.anything")

    def test_unknown_key_type_is_none(self):
        from amplifier_workspace import config_manager as cm

        assert cm.key_type("tmux.enable") is None
        assert cm.is_known_key("tmux.enable") is False

    def test_validate_key_raises_config_key_error_with_suggestion(self):
        from amplifier_workspace import config_manager as cm

        with pytest.raises(cm.ConfigKeyError) as exc_info:
            cm.validate_key("tmux.enable")
        exc = exc_info.value
        assert "tmux.enabled" in exc.suggestions
        assert "tmux.enabled" in str(exc)  # did-you-mean rendered in message
        assert "tmux.enabled" in exc.valid_keys

    def test_known_keys_includes_dynamic_placeholder(self):
        from amplifier_workspace import config_manager as cm

        keys = cm.known_keys()
        assert "tmux.enabled" in keys
        assert "tmux.windows.<name>" in keys

    def test_is_addable_key(self):
        from amplifier_workspace import config_manager as cm

        assert cm.is_addable_key("workspace.default_repos") is True  # list
        assert cm.is_addable_key("tmux.windows.git") is True  # dynamic dict leaf
        assert cm.is_addable_key("tmux.enabled") is False  # bool scalar
        assert cm.is_addable_key("workspace.bundle") is False  # str scalar


class TestCoerceForSet:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("YES", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
        ],
    )
    def test_bool_coercion_matrix(self, raw, expected):
        from amplifier_workspace import config_manager as cm

        assert cm.coerce_for_set("tmux.enabled", raw) is expected

    def test_bad_bool_raises_config_value_error(self):
        from amplifier_workspace import config_manager as cm

        with pytest.raises(cm.ConfigValueError, match="boolean"):
            cm.coerce_for_set("tmux.enabled", "maybe")

    def test_list_key_set_is_rejected(self):
        from amplifier_workspace import config_manager as cm

        with pytest.raises(cm.ConfigValueError, match="config add"):
            cm.coerce_for_set("workspace.default_repos", "http://x")

    def test_string_passes_through(self):
        from amplifier_workspace import config_manager as cm

        assert cm.coerce_for_set("workspace.bundle", "my-bundle") == "my-bundle"
        assert cm.coerce_for_set("tmux.windows.git", "lazygit") == "lazygit"


class TestSetReturnsChangeMessage:
    def test_set_reports_old_and_new(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager as cm

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(cm, "CONFIG_PATH", config_path)
        cm.set_nested_setting("tmux.enabled", False)
        msg = cm.set_nested_setting("tmux.enabled", True)
        assert msg == "tmux.enabled = true (was false)"

    def test_set_reports_unset_previous(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager as cm

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(cm, "CONFIG_PATH", config_path)
        config_path.write_text("")
        msg = cm.set_nested_setting("workspace.bundle", "custom")
        assert "custom" in msg
        assert "was unset" in msg


class TestKeyExistsInFile:
    def test_scalar_and_leaf_presence(self, monkeypatch, tmp_path):
        from amplifier_workspace import config_manager as cm
        from amplifier_workspace.config_manager import write_config_raw

        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(cm, "CONFIG_PATH", config_path)
        write_config_raw(
            {"tmux": {"enable": "True", "windows": {"git": "lazygit"}}},
            path=config_path,
        )
        assert cm.key_exists_in_file("tmux.enable") is True
        assert cm.key_exists_in_file("tmux.windows.git") is True
        assert cm.key_exists_in_file("tmux.enabled") is False


# ---------------------------------------------------------------------------
# Listing, defaults, diff, backup (defects 4, 5)
# ---------------------------------------------------------------------------


class TestFormatConfigListing:
    def test_lists_grouped_no_python_repr(self, tmp_path):
        from amplifier_workspace.config_manager import (
            format_config_listing,
            write_config_raw,
        )

        config_path = tmp_path / "config.toml"
        write_config_raw(
            {"workspace": {"default_repos": ["url1", "url2"]}}, path=config_path
        )
        out = format_config_listing(config_path)
        assert "[workspace]" in out
        assert "[tmux]" in out
        # No Python list repr.
        assert "['url1'" not in out
        assert "['url1', 'url2']" not in out
        # One-per-line indented.
        assert "    url1" in out
        assert "    url2" in out
        # File path shown as header comment.
        assert str(config_path) in out
        assert out.startswith("# config:")

    def test_unknown_key_flagged_inline(self, tmp_path):
        from amplifier_workspace.config_manager import (
            format_config_listing,
            write_config_raw,
        )

        config_path = tmp_path / "config.toml"
        write_config_raw(
            {"tmux": {"enable": "True", "enabled": True}}, path=config_path
        )
        out = format_config_listing(config_path)
        assert "# unknown key (ignored): tmux.enable" in out

    def test_missing_file_shows_defaults_header(self, tmp_path):
        from amplifier_workspace.config_manager import format_config_listing

        out = format_config_listing(tmp_path / "nope.toml")
        assert "showing defaults" in out
        assert "[workspace]" in out


class TestDefaultsAndDiff:
    def test_default_config_dict_shape(self):
        from amplifier_workspace.config_manager import default_config_dict

        d = default_config_dict()
        assert d["workspace"]["bundle"] == "amplifier-dev"
        assert d["tmux"]["enabled"] is False
        assert "amplifier" in d["tmux"]["windows"]

    def test_diff_from_defaults_reports_changes(self, tmp_path):
        from amplifier_workspace.config_manager import (
            diff_from_defaults,
            write_config_raw,
        )

        config_path = tmp_path / "config.toml"
        write_config_raw(
            {"workspace": {"bundle": "custom"}, "tmux": {"enabled": True}},
            path=config_path,
        )
        diffs = {k: (cur, dflt) for k, cur, dflt in diff_from_defaults(config_path)}
        assert "workspace.bundle" in diffs
        assert diffs["workspace.bundle"][0] == "custom"
        assert "tmux.enabled" in diffs

    def test_diff_empty_when_defaults(self, tmp_path):
        from amplifier_workspace.config_manager import (
            diff_from_defaults,
            write_default_config,
        )

        config_path = tmp_path / "config.toml"
        write_default_config(config_path)
        assert diff_from_defaults(config_path) == []


class TestBackupConfig:
    def test_backup_creates_timestamped_copy(self, tmp_path):
        from amplifier_workspace.config_manager import backup_config

        config_path = tmp_path / "config.toml"
        config_path.write_text('[workspace]\nbundle = "x"\n')
        backup = backup_config(config_path)
        assert backup is not None
        assert backup.exists()
        assert ".bak-" in backup.name
        assert backup.read_text() == config_path.read_text()

    def test_backup_returns_none_when_no_file(self, tmp_path):
        from amplifier_workspace.config_manager import backup_config

        assert backup_config(tmp_path / "missing.toml") is None
