"""Temporarily overlay ``.claude/settings.local.json`` with bypassPermissions mode.

Used when the user passes ``--bypass-permissions`` (explicitly or implied
by ``--gate-mode full-auto``).  In tmux mode the Claude Code CLI flag
``--dangerously-skip-permissions`` can't be used (Claude Code exits
immediately in interactive mode), so the equivalent effect is achieved
via the settings-file mechanism: write
``permissions.defaultMode: "bypassPermissions"`` into the project's
``.claude/settings.local.json`` for the duration of the run.

The overlay is restored on three paths:

1. Normal exit — via the ``restore_fn`` returned to the caller, who
   wires it to ``atexit.register`` and SIGINT/SIGTERM handlers.
2. Crash before restore — a sibling backup file
   (``settings.local.json.zo-backup``) is left on disk.  The next
   ``zo`` invocation that calls :func:`cleanup_stale_overlay` will
   detect it and restore.
3. Manual recovery — the backup file is human-readable; a user can
   move it back themselves if both auto-paths fail.

Designed to be **idempotent and crash-resilient**: never mutates the
user's settings file without leaving a recoverable backup, and the
restore step is safe to call multiple times.
"""
from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = ["apply_bypass_overlay", "cleanup_stale_overlay"]

_BACKUP_SUFFIX = ".zo-backup"
_NO_ORIGINAL_MARKER = "__ZO_NO_ORIGINAL_FILE__"


def _settings_path(claude_dir: Path) -> Path:
    return claude_dir / "settings.local.json"


def _backup_path(claude_dir: Path) -> Path:
    return claude_dir / f"settings.local.json{_BACKUP_SUFFIX}"


def apply_bypass_overlay(claude_dir: Path) -> Callable[[], None]:
    """Write a bypass-permissions overlay; return a restore callable.

    Backs up the original ``settings.local.json`` (if any) to a sibling
    ``.zo-backup`` file, then writes a merged version that contains the
    user's existing settings plus ``permissions.defaultMode:
    "bypassPermissions"``.

    The returned callable restores the original file (or removes the
    one we created if there was no original) and deletes the backup.
    Safe to call multiple times — subsequent calls are no-ops.

    Args:
        claude_dir: The ``.claude/`` directory whose ``settings.local.json``
            should be overlaid.  Created if missing.

    Returns:
        A zero-argument callable that restores the file.
    """
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_file = _settings_path(claude_dir)
    backup_file = _backup_path(claude_dir)

    # 1. Capture original (or mark its absence).
    if settings_file.exists():
        original_content = settings_file.read_text(encoding="utf-8")
        backup_file.write_text(original_content, encoding="utf-8")
        try:
            existing = json.loads(original_content)
            if not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {}
    else:
        original_content = None
        # Leave a sentinel so cleanup_stale_overlay knows to delete,
        # not restore, in a crash-recovery scenario.
        backup_file.write_text(_NO_ORIGINAL_MARKER, encoding="utf-8")
        existing = {}

    # 2. Merge defaultMode into permissions (preserve allow/deny/etc.).
    permissions = existing.get("permissions") or {}
    if not isinstance(permissions, dict):
        permissions = {}
    permissions["defaultMode"] = "bypassPermissions"
    existing["permissions"] = permissions

    # 3. Write overlay.
    settings_file.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    # 4. Build restore callable.
    restored = False

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        if original_content is not None:
            settings_file.write_text(original_content, encoding="utf-8")
        else:
            with contextlib.suppress(FileNotFoundError):
                settings_file.unlink()
        with contextlib.suppress(FileNotFoundError):
            backup_file.unlink()

    return restore


def cleanup_stale_overlay(claude_dir: Path) -> bool:
    """Detect + restore a leftover overlay from a crashed previous run.

    Called at ZO command startup.  If a ``.zo-backup`` file is present
    in ``claude_dir``, restore the original settings file (or remove
    it if the backup is the no-original sentinel) and delete the
    backup.

    Args:
        claude_dir: The ``.claude/`` directory to inspect.

    Returns:
        True if a stale overlay was found and cleaned; False otherwise.
    """
    backup_file = _backup_path(claude_dir)
    if not backup_file.exists():
        return False

    settings_file = _settings_path(claude_dir)
    content = backup_file.read_text(encoding="utf-8")

    if content == _NO_ORIGINAL_MARKER:
        with contextlib.suppress(FileNotFoundError):
            settings_file.unlink()
    else:
        settings_file.write_text(content, encoding="utf-8")

    with contextlib.suppress(FileNotFoundError):
        backup_file.unlink()

    return True
