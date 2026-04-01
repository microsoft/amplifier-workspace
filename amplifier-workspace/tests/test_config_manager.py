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
