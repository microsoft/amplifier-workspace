"""Tests for git.py pure functions: repo_name_from_url and is_git_repo."""

from pathlib import Path


from amplifier_workspace.git import is_git_repo, repo_name_from_url


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
