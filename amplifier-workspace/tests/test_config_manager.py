"""Tests for config_manager.py: _toml_value serializer and read/write roundtrip."""


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
