"""Unit tests for zo.permissions_overlay.

Covers four scenarios:
  1. Existing settings.local.json — overlay merges defaultMode, restore preserves original
  2. No settings.local.json — overlay creates one, restore deletes it
  3. Malformed settings.local.json — overlay treats it as empty
  4. Stale overlay from a crashed run — startup cleanup restores
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from zo.permissions_overlay import apply_bypass_overlay, cleanup_stale_overlay

if TYPE_CHECKING:
    from pathlib import Path

# ------------------------------------------------------------------ #
# Scenario 1: existing settings.local.json
# ------------------------------------------------------------------ #


class TestExistingSettings:
    def test_overlay_merges_default_mode_preserving_allow_list(
        self, tmp_path: Path
    ) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        original = {
            "permissions": {
                "allow": ["mcp__Foo__*", "Bash(npm install *)"],
                "deny": ["Bash(rm -rf *)"],
            },
        }
        settings.write_text(json.dumps(original))

        apply_bypass_overlay(claude_dir)

        # Overlay merged in defaultMode; existing allow/deny preserved
        new_content = json.loads(settings.read_text())
        assert new_content["permissions"]["defaultMode"] == "bypassPermissions"
        assert new_content["permissions"]["allow"] == [
            "mcp__Foo__*", "Bash(npm install *)",
        ]
        assert new_content["permissions"]["deny"] == ["Bash(rm -rf *)"]

        # Backup file exists with original content
        backup = claude_dir / "settings.local.json.zo-backup"
        assert backup.exists()
        assert json.loads(backup.read_text()) == original

    def test_restore_returns_original_and_removes_backup(
        self, tmp_path: Path
    ) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        original = {"permissions": {"allow": ["mcp__Foo__*"]}}
        settings.write_text(json.dumps(original))

        restore = apply_bypass_overlay(claude_dir)
        restore()

        # Settings.local.json restored exactly
        assert json.loads(settings.read_text()) == original
        # Backup deleted
        assert not (claude_dir / "settings.local.json.zo-backup").exists()

    def test_restore_is_idempotent(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        settings.write_text('{"permissions": {"allow": ["X"]}}')

        restore = apply_bypass_overlay(claude_dir)
        restore()
        # Second call is a no-op — does not raise
        restore()

        assert settings.exists()


# ------------------------------------------------------------------ #
# Scenario 2: no settings.local.json
# ------------------------------------------------------------------ #


class TestNoExistingSettings:
    def test_overlay_creates_settings_when_none_exists(
        self, tmp_path: Path
    ) -> None:
        claude_dir = tmp_path / ".claude"
        # Directory may not even exist yet — apply should create it
        assert not claude_dir.exists()

        apply_bypass_overlay(claude_dir)

        settings = claude_dir / "settings.local.json"
        assert settings.exists()
        content = json.loads(settings.read_text())
        assert content["permissions"]["defaultMode"] == "bypassPermissions"

        # Backup file holds the no-original sentinel
        backup = claude_dir / "settings.local.json.zo-backup"
        assert backup.exists()
        assert backup.read_text() == "__ZO_NO_ORIGINAL_FILE__"

    def test_restore_removes_overlay_when_no_original(
        self, tmp_path: Path
    ) -> None:
        claude_dir = tmp_path / ".claude"

        restore = apply_bypass_overlay(claude_dir)
        restore()

        # Both the overlay AND the sentinel backup should be gone
        assert not (claude_dir / "settings.local.json").exists()
        assert not (claude_dir / "settings.local.json.zo-backup").exists()


# ------------------------------------------------------------------ #
# Scenario 3: malformed existing settings
# ------------------------------------------------------------------ #


class TestMalformedSettings:
    def test_overlay_handles_invalid_json(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        settings.write_text("{ not valid json ... ")

        # Should not raise — treats malformed file as empty
        apply_bypass_overlay(claude_dir)

        new_content = json.loads(settings.read_text())
        assert new_content["permissions"]["defaultMode"] == "bypassPermissions"

    def test_restore_returns_original_malformed_content(
        self, tmp_path: Path
    ) -> None:
        """Even if the original was malformed, restore returns it
        verbatim — we don't silently 'fix' the user's file."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        bad_text = "{ not valid json ... "
        settings.write_text(bad_text)

        restore = apply_bypass_overlay(claude_dir)
        restore()

        assert settings.read_text() == bad_text


# ------------------------------------------------------------------ #
# Scenario 4: stale overlay (crash recovery)
# ------------------------------------------------------------------ #


class TestStaleCleanup:
    def test_cleanup_restores_original_from_backup(
        self, tmp_path: Path
    ) -> None:
        """Simulate a crashed previous run: backup file present,
        settings.local.json holds the overlay.  Cleanup should
        restore."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        backup = claude_dir / "settings.local.json.zo-backup"

        original = {"permissions": {"allow": ["mcp__Foo__*"]}}
        backup.write_text(json.dumps(original))
        # Overlay-state file (what crashed-mid-run would have left)
        settings.write_text(json.dumps({
            "permissions": {
                "allow": ["mcp__Foo__*"],
                "defaultMode": "bypassPermissions",
            },
        }))

        cleaned = cleanup_stale_overlay(claude_dir)

        assert cleaned is True
        assert json.loads(settings.read_text()) == original
        assert not backup.exists()

    def test_cleanup_removes_overlay_when_no_original(
        self, tmp_path: Path
    ) -> None:
        """Simulate a crashed run where no original settings.local.json
        existed before — cleanup should delete the overlay, not
        restore it as a no-original sentinel."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        backup = claude_dir / "settings.local.json.zo-backup"

        backup.write_text("__ZO_NO_ORIGINAL_FILE__")
        settings.write_text(json.dumps({
            "permissions": {"defaultMode": "bypassPermissions"},
        }))

        cleaned = cleanup_stale_overlay(claude_dir)

        assert cleaned is True
        assert not settings.exists()
        assert not backup.exists()

    def test_cleanup_no_op_when_no_backup(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        # Normal state: no backup file, possibly a regular settings file
        settings = claude_dir / "settings.local.json"
        settings.write_text('{"permissions": {"allow": ["X"]}}')

        cleaned = cleanup_stale_overlay(claude_dir)

        assert cleaned is False
        # Normal settings file untouched
        assert json.loads(settings.read_text()) == {
            "permissions": {"allow": ["X"]},
        }

    def test_cleanup_no_op_when_directory_missing(
        self, tmp_path: Path
    ) -> None:
        """Calling cleanup against a non-existent .claude directory
        must not raise."""
        claude_dir = tmp_path / "does-not-exist" / ".claude"
        cleaned = cleanup_stale_overlay(claude_dir)
        assert cleaned is False


# ------------------------------------------------------------------ #
# Scenario 5: permissions block existed but wasn't a dict
# ------------------------------------------------------------------ #


class TestPermissionsBlockNotDict:
    def test_overlay_replaces_non_dict_permissions_block(
        self, tmp_path: Path
    ) -> None:
        """Defensive: if permissions is somehow a list or string,
        overlay should still produce a valid merged config."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.local.json"
        settings.write_text('{"permissions": ["not", "a", "dict"]}')

        apply_bypass_overlay(claude_dir)

        new_content = json.loads(settings.read_text())
        assert isinstance(new_content["permissions"], dict)
        assert (
            new_content["permissions"]["defaultMode"]
            == "bypassPermissions"
        )
