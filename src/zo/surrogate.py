"""Surrogate (secondary) ZO sessions that share one project safely.

A *surrogate* is a non-orchestrating session — e.g. ``zo report`` — that runs
concurrently with the primary model session on the SAME project without racing
on shared state. It never drives the phase machine, never mutates the
experiment registry, and never writes canonical ``.zo/memory``.

Isolation is structural, not lock-based:

* **Artifacts / git** — a git worktree of the delivery repo on a ``<role>/<id>``
  branch. The surrogate writes ``paper/``/``reports/`` there; consolidation
  merges the branch back.
* **Memory** — a *delta* store at ``<delivery>/.zo/surrogates/<id>/`` with its
  own STATE/DECISION_LOG/PRIORS. The primary session keeps writing canonical
  ``.zo/memory``; consolidation folds the deltas back in.
* **Liveness** — a per-PID lock file at
  ``<delivery>/.zo/surrogates/locks/<pid>.json``. Every ZO session drops one on
  launch and removes it on exit, so the platform can tell which sessions are
  live and auto-consolidate when the last one closes.

Nothing here touches the public platform repo — surrogates live entirely in the
private delivery repo, and ``.zo/surrogates/`` is gitignored as transient
bookkeeping.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "SurrogateLayout",
    "surrogates_root",
    "locks_dir",
    "archive_dir",
    "new_surrogate_id",
    "create_surrogate",
    "load_surrogate",
    "register_session",
    "deregister_session",
    "sweep_locks",
    "live_sessions",
    "pending_surrogates",
    "archive_surrogate",
    "remove_worktree",
    "commit_worktree",
    "merge_branch",
]

_SURROGATES = "surrogates"
_LOCKS = "locks"
_ARCHIVE = "archive"


@dataclass
class SurrogateLayout:
    """Resolved paths for one surrogate session."""

    surrogate_id: str
    role: str
    delivery_repo: Path  # main delivery repo (canonical .zo lives here)
    worktree: Path  # git worktree on the surrogate's branch
    branch: str
    memory_root: Path  # <delivery>/.zo/surrogates/<id>/ (delta memory store)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def surrogates_root(delivery_repo: Path) -> Path:
    """Root of the surrogate bookkeeping area in the delivery repo."""
    return Path(delivery_repo) / ".zo" / _SURROGATES


def locks_dir(delivery_repo: Path) -> Path:
    """Directory holding per-PID liveness lock files."""
    return surrogates_root(delivery_repo) / _LOCKS


def archive_dir(delivery_repo: Path) -> Path:
    """Directory holding consolidated (archived) surrogate memory stores."""
    return surrogates_root(delivery_repo) / _ARCHIVE


def new_surrogate_id(role: str = "report") -> str:
    """A human-readable, sortable, unique id, e.g. ``report-20260604-141233``."""
    return f"{role}-{datetime.now(UTC):%Y%m%d-%H%M%S}"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _branch_exists(repo: Path, branch: str) -> bool:
    res = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    return res.returncode == 0


def _worktree_for_branch(repo: Path, branch: str) -> Path | None:
    """Return the worktree path checked out on ``branch``, if any."""
    res = _git(repo, "worktree", "list", "--porcelain")
    if res.returncode != 0:
        return None
    target = f"branch refs/heads/{branch}"
    current: Path | None = None
    for line in res.stdout.splitlines():
        if line.startswith("worktree "):
            current = Path(line[len("worktree ") :])
        elif line == target and current is not None:
            return current
    return None


def _default_worktree_path(delivery_repo: Path, surrogate_id: str) -> Path:
    """A sibling directory next to the delivery repo: ``<repo>-<id>``."""
    repo = Path(delivery_repo)
    return repo.parent / f"{repo.name}-{surrogate_id}"


def _ensure_surrogates_gitignored(delivery_repo: Path) -> None:
    """Ensure ``.zo/surrogates/`` is gitignored (transient bookkeeping)."""
    gitignore = Path(delivery_repo) / ".gitignore"
    entry = ".zo/surrogates/"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if entry in existing.split():
        return
    with open(gitignore, "a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(f"{entry}\n")


# ---------------------------------------------------------------------------
# Surrogate lifecycle
# ---------------------------------------------------------------------------


def create_surrogate(
    delivery_repo: Path,
    *,
    role: str = "report",
    surrogate_id: str | None = None,
    worktree: Path | None = None,
    branch: str | None = None,
) -> SurrogateLayout:
    """Create (or resume) a worktree + delta-memory store for a surrogate.

    Idempotent per ``surrogate_id``: if the surrogate already exists, its
    worktree/branch/memory are reused (this is how ``zo report`` resumes).

    Args:
        delivery_repo: The main delivery repo (must be a git repo with ``.zo/``).
        role: Surrogate role, used in the id and branch name (default ``report``).
        surrogate_id: Explicit id to create/resume; auto-generated if omitted.
        worktree: Override the worktree path (default: sibling ``<repo>-<id>``).
        branch: Override the branch name (default ``<role>/<id>``).

    Returns:
        The resolved :class:`SurrogateLayout`.

    Raises:
        RuntimeError: If ``git worktree add`` fails.
    """
    delivery_repo = Path(delivery_repo).resolve()
    sid = surrogate_id or new_surrogate_id(role)
    branch = branch or f"{role}/{sid}"
    wt = Path(worktree).resolve() if worktree else _default_worktree_path(delivery_repo, sid)
    mem_root = surrogates_root(delivery_repo) / sid

    _ensure_surrogates_gitignored(delivery_repo)
    mem_root.mkdir(parents=True, exist_ok=True)
    locks_dir(delivery_repo).mkdir(parents=True, exist_ok=True)

    # Scaffold the empty delta-memory store (STATE/DECISION_LOG/PRIORS + sessions/).
    from zo.memory import MemoryManager

    MemoryManager(
        project_dir=delivery_repo, project_name=sid, memory_root=mem_root,
    ).initialize_project()

    # Create (or reuse) the worktree on the surrogate branch.
    if not wt.exists():
        if _branch_exists(delivery_repo, branch):
            res = _git(delivery_repo, "worktree", "add", str(wt), branch)
        else:
            res = _git(delivery_repo, "worktree", "add", "-b", branch, str(wt))
        if res.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed for {wt} on {branch}: {res.stderr.strip()}"
            )

    return SurrogateLayout(
        surrogate_id=sid,
        role=role,
        delivery_repo=delivery_repo,
        worktree=wt,
        branch=branch,
        memory_root=mem_root,
    )


def load_surrogate(delivery_repo: Path, surrogate_id: str) -> SurrogateLayout | None:
    """Reconstruct a surrogate's layout from disk, or ``None`` if unknown."""
    delivery_repo = Path(delivery_repo).resolve()
    mem_root = surrogates_root(delivery_repo) / surrogate_id
    if not mem_root.is_dir():
        return None
    role = surrogate_id.split("-", 1)[0] or "report"
    branch = f"{role}/{surrogate_id}"
    wt = _worktree_for_branch(delivery_repo, branch) or _default_worktree_path(
        delivery_repo, surrogate_id,
    )
    return SurrogateLayout(
        surrogate_id=surrogate_id,
        role=role,
        delivery_repo=delivery_repo,
        worktree=wt,
        branch=branch,
        memory_root=mem_root,
    )


# ---------------------------------------------------------------------------
# Liveness registry (per-PID lock files)
# ---------------------------------------------------------------------------


def register_session(
    delivery_repo: Path,
    *,
    role: str,
    surrogate_id: str | None = None,
    worktree: Path | None = None,
    pid: int | None = None,
) -> Path:
    """Write a per-PID lock file marking this session live. Returns its path."""
    delivery_repo = Path(delivery_repo).resolve()
    pid = pid if pid is not None else os.getpid()
    ld = locks_dir(delivery_repo)
    ld.mkdir(parents=True, exist_ok=True)
    lock = ld / f"{pid}.json"
    lock.write_text(
        json.dumps(
            {
                "pid": pid,
                "role": role,
                "surrogate_id": surrogate_id,
                "worktree": str(worktree) if worktree else None,
                "started_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return lock


def deregister_session(delivery_repo: Path, pid: int | None = None) -> None:
    """Remove this session's lock file (idempotent)."""
    pid = pid if pid is not None else os.getpid()
    lock = locks_dir(delivery_repo) / f"{pid}.json"
    with contextlib.suppress(FileNotFoundError):
        lock.unlink()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    except OSError:
        return False
    return True


def sweep_locks(delivery_repo: Path) -> list[dict]:
    """Prune dead-PID (and corrupt) lock files; return the live sessions left."""
    ld = locks_dir(delivery_repo)
    if not ld.is_dir():
        return []
    live: list[dict] = []
    for lock in sorted(ld.glob("*.json")):
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            with contextlib.suppress(FileNotFoundError):
                lock.unlink()
            continue
        if _pid_alive(int(data.get("pid", -1))):
            live.append(data)
        else:
            with contextlib.suppress(FileNotFoundError):
                lock.unlink()
    return live


def live_sessions(
    delivery_repo: Path, *, exclude_pid: int | None = None,
) -> list[dict]:
    """Live sessions after a sweep, optionally excluding one PID (e.g. self)."""
    sessions = sweep_locks(delivery_repo)
    if exclude_pid is not None:
        sessions = [s for s in sessions if int(s.get("pid", -1)) != exclude_pid]
    return sessions


# ---------------------------------------------------------------------------
# Pending / archive
# ---------------------------------------------------------------------------


def pending_surrogates(delivery_repo: Path) -> list[str]:
    """Surrogate ids with a delta-memory store that are not yet archived."""
    root = surrogates_root(delivery_repo)
    if not root.is_dir():
        return []
    skip = {_LOCKS, _ARCHIVE}
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and p.name not in skip
    )


def archive_surrogate(delivery_repo: Path, surrogate_id: str) -> Path | None:
    """Move a consolidated surrogate's memory store into ``archive/``."""
    src = surrogates_root(delivery_repo) / surrogate_id
    if not src.is_dir():
        return None
    dst_parent = archive_dir(delivery_repo)
    dst_parent.mkdir(parents=True, exist_ok=True)
    dst = dst_parent / surrogate_id
    if dst.exists():
        dst = dst_parent / f"{surrogate_id}-{datetime.now(UTC):%H%M%S}"
    src.rename(dst)
    return dst


def remove_worktree(delivery_repo: Path, worktree: Path) -> bool:
    """Remove a surrogate's git worktree (best-effort)."""
    res = _git(delivery_repo, "worktree", "remove", "--force", str(worktree))
    return res.returncode == 0


def commit_worktree(worktree: Path, *, message: str) -> bool:
    """Stage and commit all changes in a worktree.

    Returns True if a commit was created, False if there was nothing to commit
    (or the commit failed). Used by consolidation to capture pending artifacts
    onto the surrogate branch before merging, so a worktree removal can't lose
    uncommitted work.
    """
    _git(worktree, "add", "-A")
    res = _git(worktree, "commit", "-m", message)
    return res.returncode == 0


def merge_branch(delivery_repo: Path, branch: str, *, message: str) -> tuple[bool, str]:
    """Merge ``branch`` into the delivery repo's current branch (``--no-ff``).

    Returns ``(ok, detail)``. On failure the merge is aborted so the working
    tree is left clean for the primary session.
    """
    res = _git(delivery_repo, "merge", "--no-ff", "-m", message, branch)
    if res.returncode == 0:
        return True, res.stdout.strip()
    _git(delivery_repo, "merge", "--abort")
    return False, res.stderr.strip()
