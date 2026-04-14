"""Pre-flight validation for ZO projects.

Runs a series of checks to verify that a project is ready for ``zo build``.
No API calls — pure local validation.

Usage::

    zo preflight plans/my-project.md
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from zo.plan import parse_plan, validate_plan


@dataclass
class CheckResult:
    """Result of a single pre-flight check."""

    name: str
    passed: bool
    message: str
    warning: bool = False


@dataclass
class PreflightReport:
    """Aggregated results from all pre-flight checks."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed and not c.warning)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.warning)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


def run_preflight(
    plan_path: Path,
    zo_root: Path,
    target_repo: Path | None = None,
) -> PreflightReport:
    """Run all pre-flight checks for a project.

    Args:
        plan_path: Path to the project's plan.md file.
        zo_root: Root of the ZO repository.
        target_repo: Optional path to the delivery repo.

    Returns:
        PreflightReport with all check results.
    """
    report = PreflightReport()
    report.checks.append(_check_claude_cli())
    report.checks.append(_check_tmux())
    report.checks.append(_check_plan(plan_path))
    report.checks.append(_check_agents(plan_path, zo_root))
    if target_repo:
        report.checks.append(_check_target_repo(target_repo))
        report.checks.append(_check_delivery_structure(target_repo))
        report.checks.append(_check_dockerfile(target_repo))
    report.checks.append(_check_memory_roundtrip(zo_root))
    report.checks.append(_check_docker())
    report.checks.append(_check_gpu())
    return report


def _check_claude_cli() -> CheckResult:
    """Check that Claude CLI is available."""
    path = shutil.which("claude")
    if path:
        return CheckResult("Claude CLI", True, f"Found at {path}")
    return CheckResult("Claude CLI", False, "claude not found in PATH")


def _check_tmux() -> CheckResult:
    """Check that tmux is available."""
    path = shutil.which("tmux")
    if path:
        return CheckResult("tmux", True, f"Found at {path}")
    return CheckResult("tmux", False, "tmux not found in PATH")


def _check_plan(plan_path: Path) -> CheckResult:
    """Parse and validate the project plan."""
    if not plan_path.exists():
        return CheckResult("Plan", False, f"File not found: {plan_path}")
    try:
        plan = parse_plan(plan_path)
        report = validate_plan(plan)
        if report.valid:
            return CheckResult("Plan", True, "All 8 sections valid")
        issues = "; ".join(f"{i.field}: {i.message}" for i in report.issues[:3])
        return CheckResult("Plan", False, f"Validation failed: {issues}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Plan", False, f"Parse error: {exc}")


def _check_agents(plan_path: Path, zo_root: Path) -> CheckResult:
    """Verify agent definitions exist for agents listed in the plan."""
    try:
        plan = parse_plan(plan_path)
    except Exception:  # noqa: BLE001
        return CheckResult("Agents", False, "Cannot parse plan to check agents")
    agents_dir = zo_root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return CheckResult("Agents", False, f"Agent dir missing: {agents_dir}")
    active = plan.agents.active_agents if plan.agents else []
    missing = [a for a in active if not (agents_dir / f"{a}.md").exists()]
    if missing:
        return CheckResult("Agents", False, f"Missing definitions: {missing}")
    return CheckResult("Agents", True, f"All {len(active)} agent definitions found")


def _check_target_repo(target_repo: Path) -> CheckResult:
    """Verify the delivery repo exists and is a git repository."""
    if not target_repo.is_dir():
        return CheckResult("Target Repo", False, f"Not found: {target_repo}")
    git_dir = target_repo / ".git"
    if not git_dir.exists():
        return CheckResult("Target Repo", False, "Not a git repository")
    return CheckResult("Target Repo", True, f"Git repo at {target_repo}")


def _check_delivery_structure(target_repo: Path) -> CheckResult:
    """Check that expected delivery repo directories exist."""
    expected = ["data", "src", "reports", "tests", "notebooks"]
    missing = [d for d in expected if not (target_repo / d).is_dir()]
    if missing:
        return CheckResult(
            "Delivery Structure", False,
            f"Missing directories: {missing}. Run zo init --scaffold-delivery",
            warning=True,
        )
    return CheckResult("Delivery Structure", True, "All directories present")


def _check_dockerfile(target_repo: Path) -> CheckResult:
    """Check that Dockerfile exists in the delivery repo."""
    dockerfile = target_repo / "Dockerfile"
    if not dockerfile.exists():
        return CheckResult(
            "Dockerfile", False,
            "No Dockerfile in delivery repo. Run zo init --scaffold-delivery",
            warning=True,
        )
    return CheckResult("Dockerfile", True, "Dockerfile present")


def _check_memory_roundtrip(zo_root: Path) -> CheckResult:
    """Verify memory layer can write and read state."""
    try:
        import tempfile

        from zo._memory_models import SessionState
        from zo.memory import MemoryManager

        with tempfile.TemporaryDirectory() as td:
            mm = MemoryManager(project_dir=Path(td), project_name="preflight-test")
            mm.initialize_project()
            state = SessionState(phase="preflight-check")
            mm.write_state(state)
            loaded = mm.read_state()
            if loaded.phase != "preflight-check":
                return CheckResult("Memory", False, "Round-trip mismatch")
        return CheckResult("Memory", True, "Write/read round-trip OK")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Memory", False, f"Memory error: {exc}")


def _check_docker() -> CheckResult:
    """Check that Docker is available."""
    path = shutil.which("docker")
    if not path:
        return CheckResult("Docker", False, "docker not found in PATH", warning=True)
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return CheckResult("Docker", True, version)
        return CheckResult("Docker", False, "docker --version failed", warning=True)
    except Exception:  # noqa: BLE001
        return CheckResult("Docker", False, "docker check timed out", warning=True)


def _check_gpu() -> CheckResult:
    """Check GPU availability via nvidia-smi (warning only)."""
    path = shutil.which("nvidia-smi")
    if not path:
        return CheckResult(
            "GPU", False, "nvidia-smi not found (no GPU or not on GPU server)",
            warning=True,
        )
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            gpus = result.stdout.strip()
            return CheckResult("GPU", True, f"GPUs: {gpus}")
        return CheckResult("GPU", False, "nvidia-smi failed", warning=True)
    except Exception:  # noqa: BLE001
        return CheckResult("GPU", False, "nvidia-smi timed out", warning=True)
