"""Tests for zo.extensions — the public extension seams.

Covers the orchestrator-class override hook and the CLI plugin loader. These
seams are no-ops in the public build (nothing registered), so default behavior
is unchanged; the tests assert both the default no-op and the override paths.
"""

from __future__ import annotations

import click
import pytest

from zo import extensions


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Reset extension state and stub entry-point discovery to empty by default."""
    extensions._reset_for_tests()
    monkeypatch.setattr("importlib.metadata.entry_points", lambda *, group: [])
    yield
    extensions._reset_for_tests()


def _fresh_group() -> click.Group:
    @click.group()
    def g() -> None:  # pragma: no cover - body never invoked
        pass

    return g


class TestOrchestratorClassHook:
    def test_default_is_none(self) -> None:
        assert extensions.get_orchestrator_class() is None

    def test_set_and_get(self) -> None:
        class Custom:
            pass

        extensions.set_orchestrator_class(Custom)
        assert extensions.get_orchestrator_class() is Custom

    def test_reset_to_none(self) -> None:
        class Custom:
            pass

        extensions.set_orchestrator_class(Custom)
        extensions.set_orchestrator_class(None)
        assert extensions.get_orchestrator_class() is None


class TestCliPlugins:
    def test_no_plugins_is_noop(self) -> None:
        g = _fresh_group()
        loaded = extensions.load_cli_plugins(g)
        assert loaded == []
        assert list(g.commands) == []

    def test_in_process_plugin_adds_command(self) -> None:
        def register(grp: click.Group) -> None:
            @grp.command("hello")
            def _hello() -> None:  # pragma: no cover
                pass

        extensions.register_cli_plugin(register)
        g = _fresh_group()
        loaded = extensions.load_cli_plugins(g)
        assert "register" in loaded
        assert "hello" in g.commands

    def test_plugin_can_set_orchestrator_class(self) -> None:
        class Custom:
            pass

        def register(grp: click.Group) -> None:
            extensions.set_orchestrator_class(Custom)

        extensions.register_cli_plugin(register)
        extensions.load_cli_plugins(_fresh_group())
        assert extensions.get_orchestrator_class() is Custom

    def test_broken_plugin_is_skipped(self) -> None:
        def bad(grp: click.Group) -> None:
            raise RuntimeError("boom")

        def good(grp: click.Group) -> None:
            @grp.command("ok")
            def _ok() -> None:  # pragma: no cover
                pass

        extensions.register_cli_plugin(bad)
        extensions.register_cli_plugin(good)
        g = _fresh_group()
        loaded = extensions.load_cli_plugins(g)  # must not raise
        assert "ok" in g.commands
        assert "good" in loaded
        assert "bad" not in loaded

    def test_entry_point_discovery(self, monkeypatch) -> None:
        class FakeEP:
            name = "fake"

            def load(self):
                def register(grp: click.Group) -> None:
                    @grp.command("frompoint")
                    def _f() -> None:  # pragma: no cover
                        pass

                return register

        def fake_entry_points(*, group: str):
            assert group == extensions.CLI_ENTRYPOINT_GROUP
            return [FakeEP()]

        monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
        g = _fresh_group()
        loaded = extensions.load_cli_plugins(g)
        assert "fake" in loaded
        assert "frompoint" in g.commands
