"""Strategy discovery: any module in this package exposing a callable
``strategy(state) -> Action`` shows up in the app's dropdown."""

import importlib
import pkgutil

import strategies as _pkg
from strategies.base import Action, StrategyState

_INTERNAL = {"base"}


def discover_strategies() -> dict[str, callable]:
    """Return {display_name: strategy_fn} for every pluggable strategy."""
    found = {}
    for info in pkgutil.iter_modules(_pkg.__path__):
        if info.name in _INTERNAL:
            continue
        module = importlib.import_module(f"strategies.{info.name}")
        fn = getattr(module, "strategy", None)
        if callable(fn):
            name = getattr(module, "STRATEGY_NAME", info.name)
            found[name] = fn
    return found


__all__ = ["Action", "StrategyState", "discover_strategies"]
