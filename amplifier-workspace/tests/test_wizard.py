"""Tests for wizard.py: _prompt helper, run_wizard steps 1 and 2."""

from unittest.mock import patch

import pytest

from amplifier_workspace.config import DEFAULT_BUNDLE, DEFAULT_REPOS
from amplifier_workspace.wizard import _prompt, run_wizard


class TestPrompt:
    def test_returns_user_input(self):
        """_prompt returns whatever the user typed."""
        with patch("builtins.input", side_effect=iter(["hello"])):
            result = _prompt("Enter something")
        assert result == "hello"

    def test_returns_default_on_empty_input(self):
        """_prompt returns the default when user presses Enter without typing."""
        with patch("builtins.input", side_effect=iter([""])):
            result = _prompt("Enter something", default="my-default")
        assert result == "my-default"

    def test_propagates_keyboard_interrupt(self):
        """_prompt must NOT catch KeyboardInterrupt; it must propagate upward."""
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                _prompt("Enter something")


class TestRunWizard:
    def test_accepts_default_repos_on_y(self):
        """Answering Y keeps DEFAULT_REPOS and DEFAULT_BUNDLE in the written config."""
        # inputs: "Y" → keep repos, "" → accept default bundle, "" → default template choice
        with patch("builtins.input", side_effect=iter(["Y", "", ""])):
            with patch("amplifier_workspace.wizard.write_config") as mock_write:
                run_wizard()
        mock_write.assert_called_once()
        written_data = mock_write.call_args[0][0]
        assert written_data["workspace"]["default_repos"] == DEFAULT_REPOS
        assert written_data["workspace"]["bundle"] == DEFAULT_BUNDLE

    def test_accepts_custom_repos_on_n(self):
        """Answering n prompts for comma-separated URLs; custom URL appears in config."""
        custom_url = "https://github.com/custom/repo.git"
        # inputs: "n" → reject defaults, custom URL → repos, "" → default bundle, "" → default template choice
        with patch("builtins.input", side_effect=iter(["n", custom_url, "", ""])):
            with patch("amplifier_workspace.wizard.write_config") as mock_write:
                run_wizard()
        written_data = mock_write.call_args[0][0]
        assert custom_url in written_data["workspace"]["default_repos"]

    def test_ctrl_c_writes_nothing(self):
        """Ctrl+C at any prompt cancels the wizard; write_config is never called."""
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with patch("amplifier_workspace.wizard.write_config") as mock_write:
                run_wizard()
        mock_write.assert_not_called()

    def test_stores_custom_bundle_name(self):
        """Entering a custom bundle name at step 2 is written to config."""
        custom_bundle = "my-custom-bundle"
        # inputs: "Y" → keep default repos, custom bundle name, "" → default template choice
        with patch("builtins.input", side_effect=iter(["Y", custom_bundle, ""])):
            with patch("amplifier_workspace.wizard.write_config") as mock_write:
                run_wizard()
        written_data = mock_write.call_args[0][0]
        assert written_data["workspace"]["bundle"] == custom_bundle

    def test_wizard_step3_choice_1_stores_empty_template(self):
        """Choosing '1' (built-in) at step 3 stores agents_template='' in config."""
        # inputs: "Y" → keep repos, "" → default bundle, "1" → built-in template
        with patch("builtins.input", side_effect=iter(["Y", "", "1"])):
            with patch("amplifier_workspace.wizard.write_config") as mock_write:
                run_wizard()
        written_data = mock_write.call_args[0][0]
        assert written_data["workspace"]["agents_template"] == ""

    def test_wizard_step3_choice_2_stores_custom_path(self):
        """Choosing '2' (custom) at step 3 then entering a path stores that path in config."""
        custom_path = "/path/to/AGENTS.md"
        # inputs: "Y" → keep repos, "" → default bundle, "2" → custom template, path
        with patch("builtins.input", side_effect=iter(["Y", "", "2", custom_path])):
            with patch("amplifier_workspace.wizard.write_config") as mock_write:
                run_wizard()
        written_data = mock_write.call_args[0][0]
        assert written_data["workspace"]["agents_template"] == custom_path

    def test_wizard_step4_stub_mentions_phase3_or_tmux(self):
        """Step 4 prints a message mentioning 'tmux', 'phase', or 'next'."""
        # inputs: "Y" → keep repos, "" → default bundle, "" → default template choice
        with patch("builtins.input", side_effect=iter(["Y", "", ""])):
            with patch("amplifier_workspace.wizard.write_config"):
                with patch("builtins.print") as mock_print:
                    run_wizard()
        all_output = " ".join(str(call) for call in mock_print.call_args_list).lower()
        assert "tmux" in all_output or "phase" in all_output or "next" in all_output
