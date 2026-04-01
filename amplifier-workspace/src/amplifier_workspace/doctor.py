"""Health checks for amplifier-workspace (amplifier-workspace doctor)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from amplifier_workspace.config import CONFIG_PATH, load_config

# ── ANSI colour constants ──────────────────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# ── Symbols ────────────────────────────────────────────────────────────────────
_CHECK = f"{GREEN}✓{RESET}"
_FAIL = f"{RED}✗{RESET}"
_WARN = f"{YELLOW}⚠{RESET}"
_SKIP = "-"


# ── Thin lazy wrappers (patched independently in tests) ───────────────────────


def _get_install_info_for_doctor() -> dict:
    """Lazy wrapper around upgrade._get_install_info for independent test patching."""
    from amplifier_workspace.upgrade import _get_install_info  # noqa: PLC0415

    return _get_install_info()


def _check_for_update_doctor(info: dict) -> tuple[bool, str]:
    """Lazy wrapper around upgrade._check_for_update for independent test patching."""
    from amplifier_workspace.upgrade import _check_for_update  # noqa: PLC0415

    return _check_for_update(info)


# ── Formatted output helper ───────────────────────────────────────────────────


def _print_check(label: str, passed: bool | None, detail: str = "") -> None:
    """Print a formatted check line.

    - passed=True  → '  ✓  label  detail'  (green)
    - passed=False → '  ✗  label  detail'  (red)
    - passed=None  → '  -  label (skipped)'
    """
    if passed is None:
        print(f"  {_SKIP}  {label} (skipped)")
    else:
        symbol = _CHECK if passed else _FAIL
        suffix = f"  {detail}" if detail else ""
        print(f"  {symbol}  {label}{suffix}")


# ── Main health-check runner ──────────────────────────────────────────────────


def run_doctor() -> int:
    """Run all always-on health checks and return 0 (all pass) or 1 (any failure)."""
    failures = 0

    print("amplifier-workspace doctor")
    print("=" * 40)

    # 1. Python version (≥3.11 required) ─────────────────────────────────────
    py_ver = sys.version_info
    py_ok = py_ver >= (3, 11)
    py_detail = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    _print_check("Python version", py_ok, py_detail)
    if not py_ok:
        failures += 1

    # 2. amplifier-workspace version + install source ─────────────────────────
    info = _get_install_info_for_doctor()
    version_detail = f"{info['version']}  ({info['source']})"
    if info["source"] == "git" and info.get("commit"):
        version_detail += f"  commit {info['commit'][:8]}"
    _print_check("amplifier-workspace", True, version_detail)

    # 3. Update check (warning if available, not a failure) ───────────────────
    update_available, update_msg = _check_for_update_doctor(info)
    if update_available:
        print(f"  {_WARN}  update available  {update_msg}")
    else:
        _print_check("up to date", True, update_msg)

    # 4. git in PATH (required) ───────────────────────────────────────────────
    git_path = shutil.which("git")
    git_ok = git_path is not None
    _print_check("git in PATH", git_ok, git_path or "not found")
    if not git_ok:
        failures += 1

    # 5. amplifier in PATH (required) ─────────────────────────────────────────
    amp_path = shutil.which("amplifier")
    amp_ok = amp_path is not None
    _print_check("amplifier in PATH", amp_ok, amp_path or "not found")
    if not amp_ok:
        failures += 1

    # 6. Config file exists ───────────────────────────────────────────────────
    config_exists = CONFIG_PATH.exists()
    config_detail = (
        str(CONFIG_PATH)
        if config_exists
        else "not found — run: amplifier-workspace setup"
    )
    _print_check("config file", config_exists, config_detail)
    if not config_exists:
        failures += 1

    # Load config for remaining checks (use defaults if file missing) ─────────
    config = load_config()

    # 7. default_repos count (info only, skipped if none) ─────────────────────
    repos = config.default_repos
    if repos:
        _print_check("default_repos", True, f"{len(repos)} repo(s) configured")
    else:
        _print_check("default_repos", None)

    # 8. agents_template validity ─────────────────────────────────────────────
    tmpl = config.agents_template
    if tmpl:
        tmpl_path = Path(tmpl)
        tmpl_ok = tmpl_path.exists()
        _print_check(
            "agents_template",
            tmpl_ok,
            str(tmpl_path) if tmpl_ok else f"file not found: {tmpl_path}",
        )
        if not tmpl_ok:
            failures += 1
    else:
        _print_check("agents_template", None)

    # 9. tmux conditional stub (full implementation in Task 7) ────────────────
    # TODO Task 7: implement real check when enabled
    _print_check("tmux session", None)

    # 10. Summary ─────────────────────────────────────────────────────────────
    print()
    if failures == 0:
        print(f"{GREEN}All checks passed{RESET}")
    else:
        print(f"{RED}{failures} issue(s) found{RESET}")

    return 0 if failures == 0 else 1
