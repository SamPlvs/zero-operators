"""Public extension points for Zero Operators.

These hooks let a downstream build add capabilities WITHOUT editing ZO core
files. The public build registers nothing here, so default behavior is
unchanged. Two seams are exposed:

1. **Orchestrator class** — register a custom :class:`~zo.orchestrator.Orchestrator`
   subclass that the CLI instantiates instead of the default.
2. **CLI command plugins** — contribute commands/options to the ``zo`` CLI,
   discovered from the ``zo.commands`` entry-point group or registered in-process.

A plugin is a callable ``register(cli_group)`` that may add commands/options to
the group and/or call :func:`set_orchestrator_class`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    import click

logger = logging.getLogger(__name__)

CLI_ENTRYPOINT_GROUP = "zo.commands"


# ---------------------------------------------------------------------------
# Orchestrator class override
# ---------------------------------------------------------------------------

_orchestrator_class: type | None = None


def set_orchestrator_class(cls: type | None) -> None:
    """Register a custom Orchestrator subclass for the CLI to instantiate.

    Passing ``None`` restores the default (the built-in Orchestrator).
    """
    global _orchestrator_class
    _orchestrator_class = cls


def get_orchestrator_class() -> type | None:
    """Return the registered Orchestrator subclass, or ``None`` for the default."""
    return _orchestrator_class


# ---------------------------------------------------------------------------
# CLI command plugins
# ---------------------------------------------------------------------------

_cli_plugins: list[Callable[[click.Group], None]] = []


def register_cli_plugin(fn: Callable[[click.Group], None]) -> None:
    """Register an in-process CLI plugin ``fn(cli_group)``.

    Handy for tests and import-side-effect plugins. Most downstream builds will
    instead expose a ``zo.commands`` entry point (discovered automatically).
    """
    _cli_plugins.append(fn)


def load_cli_plugins(cli_group: click.Group) -> list[str]:
    """Apply all in-process + entry-point CLI plugins to ``cli_group``.

    Each plugin is a callable ``register(cli_group)``. Failures are logged and
    skipped, so a broken plugin can never break the core CLI. Returns the names
    of plugins that loaded successfully.
    """
    loaded: list[str] = []

    for fn in list(_cli_plugins):
        name = getattr(fn, "__name__", repr(fn))
        try:
            fn(cli_group)
            loaded.append(name)
        except Exception as exc:  # noqa: BLE001 - never let a plugin break the CLI
            logger.warning("zo CLI plugin %r failed: %s", name, exc)

    try:
        from importlib.metadata import entry_points

        eps = list(entry_points(group=CLI_ENTRYPOINT_GROUP))
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort
        logger.warning("zo CLI plugin discovery failed: %s", exc)
        eps = []

    for ep in eps:
        try:
            register = ep.load()
            register(cli_group)
            loaded.append(ep.name)
        except Exception as exc:  # noqa: BLE001 - skip a broken plugin
            logger.warning("zo CLI plugin entry point %r failed: %s", ep.name, exc)

    return loaded


def _reset_for_tests() -> None:
    """Reset all registered extensions. Test helper only."""
    global _orchestrator_class
    _orchestrator_class = None
    _cli_plugins.clear()
