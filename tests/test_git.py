"""Tests for git.py pure functions: repo_name_from_url and is_git_repo."""

from pathlib import Path
from unittest.mock import call, patch


from amplifier_workspace.git import (
    add_submodule,
    checkout_submodules,
    init_repo,
    initial_commit,
    is_git_repo,
    repo_name_from_url,
)


class TestRepoNameFromUrl:
    def test_https_with_git_suffix(self):
        url = "https://github.com/org/my-repo.git"
        assert repo_name_from_url(url) == "my-repo"

    def test_https_without_git_suffix(self):
        url = "https://github.com/org/my-repo"
        assert repo_name_from_url(url) == "my-repo"

    def test_ssh_format(self):
        url = "git@github.com:org/repo.git"
        assert repo_name_from_url(url) == "repo"

    def test_hyphenated_name(self):
        url = "https://github.com/org/amplifier-workspace.git"
        assert repo_name_from_url(url) == "amplifier-workspace"

    def test_simple_name(self):
        url = "https://github.com/org/amplifier.git"
        assert repo_name_from_url(url) == "amplifier"


class TestIsGitRepo:
    def test_git_dir_exists(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        assert is_git_repo(tmp_path) is True

    def test_no_git_dir(self, tmp_path: Path):
        assert is_git_repo(tmp_path) is False

    def test_git_is_file(self, tmp_path: Path):
        # Submodules have .git as a file, not a directory
        (tmp_path / ".git").write_text("gitdir: ../.git/modules/sub\n")
        assert is_git_repo(tmp_path) is True

    def test_nonexistent_path(self, tmp_path: Path):
        nonexistent = tmp_path / "does-not-exist"
        assert is_git_repo(nonexistent) is False


# ---------------------------------------------------------------------------
# Subprocess-wrapper tests
# ---------------------------------------------------------------------------


class TestInitRepo:
    def test_calls_git_init(self, tmp_path: Path):
        with patch("subprocess.run") as mock_run:
            init_repo(tmp_path)
        mock_run.assert_called_once_with(["git", "init"], cwd=tmp_path, check=True)

    def test_skips_if_already_git_repo(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        with patch("subprocess.run") as mock_run:
            init_repo(tmp_path)
        mock_run.assert_not_called()

    def test_creates_directory_if_missing(self, tmp_path: Path):
        target = tmp_path / "new-repo"
        with patch("subprocess.run") as mock_run:
            init_repo(target)
        assert target.exists()
        mock_run.assert_called_once()


class TestAddSubmodule:
    def test_calls_git_submodule_add(self, tmp_path: Path):
        url = "https://github.com/org/my-repo.git"
        with patch("subprocess.run") as mock_run:
            add_submodule(tmp_path, url)
        mock_run.assert_called_once_with(
            ["git", "submodule", "add", url], cwd=tmp_path, check=True
        )

    def test_skips_if_directory_exists(self, tmp_path: Path):
        url = "https://github.com/org/my-repo.git"
        (tmp_path / "my-repo").mkdir()
        with patch("subprocess.run") as mock_run:
            add_submodule(tmp_path, url)
        mock_run.assert_not_called()

    def test_derives_name_from_url(self, tmp_path: Path):
        url = "git@github.com:org/amplifier-core.git"
        (tmp_path / "amplifier-core").mkdir()
        with patch("subprocess.run") as mock_run:
            add_submodule(tmp_path, url)
        mock_run.assert_not_called()


class TestCheckoutSubmodules:
    def test_calls_git_submodule_foreach(self, tmp_path: Path):
        with patch("subprocess.run") as mock_run:
            checkout_submodules(tmp_path)
        mock_run.assert_called_once_with(
            [
                "git",
                "submodule",
                "foreach",
                "git checkout main || git checkout master",
            ],
            cwd=tmp_path,
            check=True,
        )


class TestInitialCommit:
    def test_calls_add_then_commit(self, tmp_path: Path):
        message = "Initial commit"
        with patch("subprocess.run") as mock_run:
            initial_commit(tmp_path, message)
        assert mock_run.call_count == 2
        assert mock_run.call_args_list == [
            call(["git", "add", "."], cwd=tmp_path, check=True),
            call(["git", "commit", "-m", message], cwd=tmp_path, check=True),
        ]
