"""Upgrade detection for amplifier-workspace via PEP 610 direct_url.json."""

import importlib.metadata
import json
import shutil
import subprocess
import sys

_PACKAGE_NAME = "amplifier-workspace"
_GIT_URL = "https://github.com/microsoft/amplifier-workspace"


def _get_install_info() -> dict:
    """Detect how amplifier-workspace was installed using PEP 610 direct_url.json.

    Returns a dict with keys:
      - source: 'git' | 'editable' | 'pypi' | 'unknown'
      - version: str
      - commit: str | None
      - url: str | None
    """
    try:
        dist = importlib.metadata.distribution(_PACKAGE_NAME)
        version = dist.metadata["Version"]

        direct_url_text = dist.read_text("direct_url.json")

        if direct_url_text is None:
            # No direct_url.json means it was installed from PyPI
            return {"source": "pypi", "version": version, "commit": None, "url": None}

        direct_url = json.loads(direct_url_text)

        if "vcs_info" in direct_url:
            # Git-based install (pip install git+...)
            vcs_info = direct_url["vcs_info"]
            return {
                "source": "git",
                "version": version,
                "commit": vcs_info.get("commit_id"),
                "url": direct_url.get("url"),
            }

        dir_info = direct_url.get("dir_info", {})
        if dir_info.get("editable"):
            # Editable install (pip install -e .)
            return {
                "source": "editable",
                "version": version,
                "commit": None,
                "url": direct_url.get("url"),
            }

        # direct_url.json exists but no vcs_info or editable dir_info
        return {"source": "pypi", "version": version, "commit": None, "url": None}

    except importlib.metadata.PackageNotFoundError:
        return {"source": "unknown", "version": "0.0.0", "commit": None, "url": None}


def _check_for_update(info: dict) -> tuple[bool, str]:
    """Check if an update is available for amplifier-workspace.

    Returns (update_available, message) tuple.

    - editable: always (False, 'editable install — manage updates manually')
    - git: compare local SHA vs remote SHA via 'git ls-remote {url} HEAD'
    - pypi: (True, 'PyPI version check not yet implemented — upgrading to be safe')
    - unknown: (True, 'unknown install source — upgrading to be safe')
    """
    source = info["source"]

    if source == "editable":
        return (False, "editable install — manage updates manually")

    if source == "unknown":
        return (True, "unknown install source — upgrading to be safe")

    if source == "pypi":
        return (True, "PyPI version check not yet implemented — upgrading to be safe")

    if source == "git":
        url = info.get("url") or _GIT_URL
        local_commit = info.get("commit") or ""

        try:
            result = subprocess.run(
                ["git", "ls-remote", url, "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return (True, "could not check remote — upgrading to be safe")

            stdout = result.stdout.strip()
            if not stdout:
                return (True, "could not check remote — upgrading to be safe")

            # Output format: "<sha>\tHEAD"
            remote_sha = stdout.split()[0]

            if local_commit == remote_sha:
                return (False, f"up to date (commit {remote_sha[:8]})")
            else:
                return (
                    True,
                    f"update available ({local_commit[:8]} → {remote_sha[:8]})",
                )

        except Exception:
            return (True, "could not check remote — upgrading to be safe")

    # Fallback for any unrecognized source
    return (True, "unknown install source — upgrading to be safe")


def _do_upgrade(info: dict) -> bool:
    """Reinstall amplifier-workspace. Tries uv first, falls back to pip.

    Returns True on success, False on failure.
    """
    url = info.get("url") or _GIT_URL
    git_url = f"git+{url}"

    uv_path = shutil.which("uv")
    if uv_path:
        result = subprocess.run(
            [uv_path, "tool", "install", "--force", git_url],
        )
        return result.returncode == 0

    pip_path = shutil.which("pip")
    if pip_path:
        result = subprocess.run(
            [pip_path, "install", "--upgrade", git_url],
        )
        return result.returncode == 0

    print("ERROR: neither uv nor pip found — cannot upgrade")
    return False


def _run_doctor_after_upgrade() -> None:
    """Lazily import and run doctor.run_doctor() to verify new install."""
    doctor = importlib.import_module("amplifier_workspace.doctor")
    doctor.run_doctor()


def run_upgrade(*, force: bool = False, check_only: bool = False) -> None:
    """Run the upgrade workflow.

    Args:
        force: Skip version check and reinstall unconditionally.
        check_only: Print status only, do not install.
    """
    info = _get_install_info()
    print(f"  version : {info['version']}")
    print(f"  commit  : {info['commit'] or 'n/a'}")
    print(f"  source  : {info['source']}")

    if check_only:
        return

    if force:
        print("--force specified, skipping version check")
        update_available = True
    else:
        update_available, message = _check_for_update(info)
        if not update_available:
            print(f"Already up to date — {message}")
            return
        print(f"Update available: {message}")

    success = _do_upgrade(info)
    if success:
        _run_doctor_after_upgrade()
    else:
        sys.exit(1)
