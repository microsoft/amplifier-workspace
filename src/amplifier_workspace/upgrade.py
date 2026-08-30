"""Upgrade detection and self-update for amplifier-workspace via PEP 610 direct_url.json.

The reinstall target is derived STRICTLY from recorded PEP 610 provenance
(``direct_url.json``): a git install is reinstalled from the exact recorded
URL (and tracked ref), while editable / PyPI / unknown installs are REFUSED
with actionable guidance rather than being silently reinstalled from a
hardcoded GitHub URL.  ``_GIT_URL`` below is only the documented default for a
*fresh* install (see README); it is never silently substituted when the
recorded provenance says something else.
"""

import importlib.metadata
import json
import shutil
import subprocess
import sys

_PACKAGE_NAME = "amplifier-workspace"
# Documented default for FRESH installs only (see README "Install"). Never used
# as a silent substitute when a package's recorded provenance disagrees.
_GIT_URL = "https://github.com/microsoft/amplifier-workspace"


class UpgradeRefused(Exception):
    """Provenance does not permit an automated in-place reinstall.

    The exception message is user-facing guidance (multi-line) describing how
    to update this particular kind of install by hand.
    """


_EDITABLE_GUIDANCE = (
    "Refusing to upgrade an editable / local-dev install \u2014 'upgrade' re-fetches a\n"
    "  published build and would clobber your local checkout.\n"
    "  To pick up LOCAL edits, reinstall from your checkout:\n"
    "    uv tool install --from /path/to/checkout --force amplifier-workspace\n"
    "    (or, from inside the checkout)  uv tool install -e . --force\n"
    "  To run a PUSHED branch:\n"
    "    uv tool install --force git+https://github.com/microsoft/amplifier-workspace@<branch>\n"
    "    uvx --from git+https://github.com/microsoft/amplifier-workspace@<branch> amplifier-workspace"
)

_PYPI_GUIDANCE = (
    "Refusing to upgrade: installed from a package index (pip/PyPI), not from git.\n"
    "  Update it with the tool you installed it with, e.g.:\n"
    "    uv tool upgrade amplifier-workspace\n"
    "    pip install --upgrade amplifier-workspace"
)


def _unknown_guidance() -> str:
    """Guidance for an install with no usable PEP 610 provenance."""
    return (
        "Refusing to upgrade: cannot determine how amplifier-workspace was installed\n"
        "  (no PEP 610 provenance recorded).  Reinstall explicitly, e.g.:\n"
        f"    uv tool install --force git+{_GIT_URL}\n"
        "  For local development, see the README 'Developing locally' section."
    )


def _get_install_info() -> dict:
    """Detect how amplifier-workspace was installed using PEP 610 direct_url.json.

    Returns a dict with keys:
      - source: 'git' | 'editable' | 'pypi' | 'unknown'
      - version: str
      - commit: str | None   (git only)
      - url: str | None      (git only)
      - ref: str | None      (git only; the tracked branch/tag, if recorded)
    """
    try:
        dist = importlib.metadata.distribution(_PACKAGE_NAME)
        version = dist.metadata["Version"]

        direct_url_text = dist.read_text("direct_url.json")

        if direct_url_text is None:
            # No direct_url.json means it was installed from PyPI
            return {
                "source": "pypi",
                "version": version,
                "commit": None,
                "url": None,
                "ref": None,
            }

        direct_url = json.loads(direct_url_text)

        if "vcs_info" in direct_url:
            # Git-based install (pip/uv install git+...)
            vcs_info = direct_url["vcs_info"]
            return {
                "source": "git",
                "version": version,
                "commit": vcs_info.get("commit_id"),
                "url": direct_url.get("url"),
                # requested_revision is the symbolic ref (branch/tag) the install
                # tracks; it is what 'upgrade' must re-fetch to move forward.
                "ref": vcs_info.get("requested_revision"),
            }

        dir_info = direct_url.get("dir_info", {})
        if dir_info.get("editable"):
            # Editable install (pip/uv install -e .)
            return {
                "source": "editable",
                "version": version,
                "commit": None,
                "url": direct_url.get("url"),
                "ref": None,
            }

        # direct_url.json exists but no vcs_info or editable dir_info
        return {
            "source": "pypi",
            "version": version,
            "commit": None,
            "url": None,
            "ref": None,
        }

    except importlib.metadata.PackageNotFoundError:
        return {
            "source": "unknown",
            "version": "0.0.0",
            "commit": None,
            "url": None,
            "ref": None,
        }


def _reinstall_target(info: dict) -> str:
    """Return the reinstall spec derived STRICTLY from recorded provenance.

    - git  -> ``git+<recorded url>[@<recorded ref>]``
    - editable / pypi / unknown / not-installed -> raise :class:`UpgradeRefused`
      with source-appropriate guidance.

    Never falls back to ``_GIT_URL`` when the recorded provenance disagrees or
    is absent \u2014 that would silently reinstall a different artifact than the one
    the user actually has.
    """
    source = info["source"]

    if source == "git":
        url = info.get("url")
        if not url:
            raise UpgradeRefused(
                "Refusing to upgrade: git install has no recorded URL in "
                "direct_url.json.\n"
                f"  Reinstall manually, e.g.:  uv tool install --force git+{_GIT_URL}"
            )
        ref = info.get("ref")
        return f"git+{url}@{ref}" if ref else f"git+{url}"

    if source == "editable":
        raise UpgradeRefused(_EDITABLE_GUIDANCE)

    if source == "pypi":
        raise UpgradeRefused(_PYPI_GUIDANCE)

    # unknown / not-installed / anything unrecognized
    raise UpgradeRefused(_unknown_guidance())


def _check_for_update(info: dict) -> tuple[bool, str]:
    """Check if an update is available for amplifier-workspace.

    Returns (update_available, message).

    Honesty rule (muxplex parity): never fabricate an update signal for a
    source we cannot actually compare.

    - editable: (False, 'editable install ...') \u2014 not checkable
    - git: compare local SHA vs remote SHA via 'git ls-remote {url} HEAD'
    - pypi: (False, 'not checkable ...') \u2014 no PyPI version check implemented
    - unknown: (False, 'not checkable ...')
    """
    source = info["source"]

    if source == "editable":
        return (False, "editable install \u2014 manage updates manually")

    if source == "unknown":
        return (False, "not checkable \u2014 unknown install source")

    if source == "pypi":
        return (False, "not checkable \u2014 pip/PyPI install (no version check)")

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
                return (True, "could not check remote \u2014 upgrading to be safe")

            stdout = result.stdout.strip()
            if not stdout:
                return (True, "could not check remote \u2014 upgrading to be safe")

            # Output format: "<sha>\tHEAD"
            remote_sha = stdout.split()[0]

            if local_commit == remote_sha:
                return (False, f"up to date (commit {remote_sha[:8]})")
            else:
                return (
                    True,
                    f"update available ({local_commit[:8]} \u2192 {remote_sha[:8]})",
                )

        except Exception:
            return (True, "could not check remote \u2014 upgrading to be safe")

    # Any unrecognized source: do not fabricate an update signal.
    return (False, "not checkable \u2014 unrecognized install source")


def _do_upgrade(info: dict) -> bool:
    """Reinstall amplifier-workspace from its recorded provenance.

    Tries uv first, falls back to pip.  Returns True on success, False on
    failure (including a provenance refusal, which is printed).
    """
    try:
        target = _reinstall_target(info)
    except UpgradeRefused as exc:
        print(str(exc))
        return False

    uv_path = shutil.which("uv")
    if uv_path:
        result = subprocess.run(
            [uv_path, "tool", "install", "--force", target],
        )
        return result.returncode == 0

    pip_path = shutil.which("pip")
    if pip_path:
        result = subprocess.run(
            [pip_path, "install", "--upgrade", target],
        )
        return result.returncode == 0

    print("ERROR: neither uv nor pip found \u2014 cannot upgrade")
    return False


def _run_doctor_after_upgrade() -> None:
    """Lazily import and run doctor.run_doctor() to verify new install."""
    doctor = importlib.import_module("amplifier_workspace.doctor")
    doctor.run_doctor()


def _format_version(info: dict) -> str:
    """Render 'version (commit8)' or just 'version' when no commit is recorded."""
    commit = info.get("commit")
    if commit:
        return f"{info['version']} ({commit[:8]})"
    return str(info["version"])


def _report_version_move(before: dict, after: dict) -> None:
    """Report whether the reinstall actually moved the version/commit.

    Honesty rule: if nothing moved, say so plainly and suggest why, rather
    than implying a successful bump.
    """
    same_version = before.get("version") == after.get("version")
    same_commit = before.get("commit") == after.get("commit")
    if same_version and same_commit:
        print(f"  version unchanged: {_format_version(after)}")
        print(
            "  (already at the latest published commit, or a cached build was reused)"
        )
    else:
        print(f"  upgraded: {_format_version(before)} \u2192 {_format_version(after)}")


def run_upgrade(*, force: bool = False, check_only: bool = False) -> None:
    """Run the self-update workflow for the amplifier-workspace CLI tool.

    This updates the *tool itself*, not any workspace's repos (that is
    ``amplifier-workspace update``).

    Args:
        force: Skip version check and reinstall unconditionally.
        check_only: Print status only, do not install.
    """
    info = _get_install_info()
    print(f"  version : {info['version']}")
    print(f"  commit  : {info['commit'] or 'n/a'}")
    print(f"  source  : {info['source']}")
    if info.get("ref"):
        print(f"  ref     : {info['ref']}")

    if check_only:
        return

    # Provenance gate BEFORE any install attempt: derive the reinstall target
    # strictly, or refuse with guidance (never silently reinstall from _GIT_URL).
    try:
        _reinstall_target(info)
    except UpgradeRefused as exc:
        print(str(exc))
        sys.exit(2)

    if force:
        print("--force specified, skipping version check")
    else:
        update_available, message = _check_for_update(info)
        if not update_available:
            print(f"Already up to date \u2014 {message}")
            return
        print(f"Update available: {message}")

    before = info
    success = _do_upgrade(info)
    if not success:
        sys.exit(1)

    # Verify the install actually moved (re-read metadata) before declaring victory.
    after = _get_install_info()
    _report_version_move(before, after)

    _run_doctor_after_upgrade()
