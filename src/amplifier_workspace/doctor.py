"""Health checks for amplifier-workspace (amplifier-workspace doctor)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from amplifier_workspace.config import CONFIG_PATH, load_config
from amplifier_workspace.install import get_install_hint

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


def _get_version(cmd: str, flag: str) -> str:
    """Return version string from running ``cmd flag``, or empty string on failure."""
    try:
        result = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


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


def _print_remedy(text: str) -> None:
    """Print an indented remedy line (muxplex convention: 'Run: <fix>').

    Pairs with a preceding failure/warning line so every problem the doctor
    surfaces comes with an actionable next step.
    """
    print(f"    Run: {text}")


def _looks_like_workspace(path: Path) -> bool:
    """Return True if *path* looks like an amplifier-workspace scaffold.

    Any one of the scaffolded markers is enough — an *older* workspace created
    before the manifest feature has AGENTS.md and .amplifier/settings.yaml but
    no WORKSPACE-MANIFEST.json, which is exactly the case the manifest check
    below wants to warn about.
    """
    return (
        (path / "AGENTS.md").exists()
        or (path / ".amplifier" / "settings.yaml").exists()
        or (path / "WORKSPACE-MANIFEST.json").exists()
    )


def _packaged_agents_md() -> bytes | None:
    """Return the bytes of the packaged AGENTS.md template, or None on failure."""
    try:
        import importlib.resources

        pkg_file = (
            importlib.resources.files("amplifier_workspace") / "templates" / "AGENTS.md"
        )
        return pkg_file.read_bytes()
    except Exception:
        return None


# ── Main health-check runner ──────────────────────────────────────────────────


def run_doctor(workdir: Path | None = None) -> int:
    """Run all always-on health checks and return 0 (all pass) or 1 (any failure).

    *workdir* selects the directory for the workspace-scoped checks (manifest
    presence and AGENTS.md template drift).  When None, the current working
    directory is used; those checks are skipped entirely unless the target
    looks like a workspace.
    """
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
    # Honest 3-way: only 'git' installs can actually be compared against a
    # remote. For editable/pypi/unknown we say "not checkable" rather than
    # fabricating an update signal (muxplex parity). Warnings never fail doctor.
    if info["source"] == "git":
        update_available, update_msg = _check_for_update_doctor(info)
        if update_available:
            print(f"  {_WARN}  update available  {update_msg}")
            _print_remedy("amplifier-workspace upgrade")
        else:
            _print_check("up to date", True, update_msg)
    else:
        reason = {
            "editable": "editable install — manage updates manually",
            "pypi": "pip/PyPI install — no version check",
            "unknown": "unknown install source",
        }.get(info["source"], "unrecognized install source")
        print(f"  {_WARN}  update check  not checkable ({reason})")

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

    # 9. tmux conditional checks ────────────────────────────────────────────────
    if config.tmux.enabled:
        # 9a. Check tmux binary
        tmux_path = shutil.which("tmux")
        if tmux_path:
            tmux_ver = (
                _get_version("tmux", "-V") or f"{tmux_path} (version unavailable)"
            )
            _print_check("tmux binary", True, tmux_ver)
        else:
            hint = get_install_hint("tmux")
            detail = "not found" + (f"  hint: {hint}" if hint else "")
            _print_check("tmux binary", False, detail)
            failures += 1

        # 9b. Report window count and check each window tool
        window_count = len(config.tmux.windows)
        print(f"  {window_count} window(s) configured")
        for window_name, command in config.tmux.windows.items():
            if not command:
                continue
            base_cmd = command.split()[0]
            tool_path = shutil.which(base_cmd)
            if tool_path:
                _print_check(f"tmux window '{window_name}'", True, base_cmd)
            else:
                hint = get_install_hint(base_cmd)
                detail = f"{base_cmd}: not found"
                if hint:
                    detail += f"  hint: {hint}"
                detail += f"  (or remove '{window_name}' from config)"
                _print_check(f"tmux window '{window_name}'", False, detail)
                failures += 1
    else:
        _print_check("tmux session", None)

    # 9.5 Workspace-scoped checks (only when the target directory is a workspace)
    target = workdir if workdir is not None else Path.cwd()
    if _looks_like_workspace(target):
        from amplifier_workspace import manifest as _manifest

        print()
        print(f"  workspace: {target}")

        # Manifest presence / parse / active-resource count
        mpath = _manifest.manifest_path(target)
        if not mpath.exists():
            print(f"  {_WARN}  WORKSPACE-MANIFEST.json  not found")
            _print_remedy(
                f"amplifier-workspace manifest {target} --add <kind> <id>"
                "   (or re-run setup)"
            )
        else:
            try:
                data = _manifest.load_manifest(target)
                resources = _manifest.iter_resources(data or {})
            except _manifest.ManifestError as exc:
                _print_check("WORKSPACE-MANIFEST.json", False, f"unparseable: {exc}")
                _print_remedy(
                    "fix or delete WORKSPACE-MANIFEST.json (it gates destroy)"
                )
                failures += 1
            else:
                active = [r for r in resources if r.status != "reaped"]
                if active:
                    print(
                        f"  {_WARN}  WORKSPACE-MANIFEST.json  "
                        f"{len(active)} active resource(s) — these gate destroy"
                    )
                    for r in active:
                        print(f"         - {r.kind}  {r.id}")
                    _print_remedy(
                        f"amplifier-workspace manifest {target}   (reap before destroy)"
                    )
                else:
                    _print_check(
                        "WORKSPACE-MANIFEST.json",
                        True,
                        f"{len(resources)} resource(s), 0 active",
                    )

        # AGENTS.md template drift (workspace copy vs packaged template)
        agents_path = target / "AGENTS.md"
        packaged = _packaged_agents_md()
        if not agents_path.exists():
            _print_check("AGENTS.md", None)
        elif config.agents_template:
            # A custom template is configured, so drift from the packaged
            # template is expected and not meaningful — don't cry wolf.
            _print_check("AGENTS.md template", None)
        elif packaged is None:
            _print_check("AGENTS.md template", None)
        else:
            import hashlib

            ws_hash = hashlib.sha256(agents_path.read_bytes()).hexdigest()
            pkg_hash = hashlib.sha256(packaged).hexdigest()
            if ws_hash != pkg_hash:
                print(
                    f"  {_WARN}  AGENTS.md differs from the packaged template "
                    "(older scaffold or local edits)"
                )
                _print_remedy(
                    "diff against the packaged template; intentional edits are fine"
                )
            else:
                _print_check("AGENTS.md template", True, "matches packaged")

    # 10. Summary ─────────────────────────────────────────────────────────────
    print()
    if failures == 0:
        print(f"{GREEN}All checks passed{RESET}")
    else:
        print(f"{RED}{failures} issue(s) found{RESET}")

    return 0 if failures == 0 else 1
