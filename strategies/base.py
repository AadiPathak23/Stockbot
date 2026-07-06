"""The pluggable strategy interface for the Phase 2 trading sandbox.

Write your own strategy
-----------------------
Drop a ``.py`` file into ``strategies/`` containing a module-level function
named ``strategy`` with this exact signature:

    def strategy(state: StrategyState) -> Action:
        ...

The sandbox calls it once per price step. It receives the full current
state and returns what to do at this step. Example — buy everything on the
first step and hold:

    from strategies.base import Action, StrategyState

    STRATEGY_NAME = "Buy & hold"  # optional; shown in the UI dropdown

    def strategy(state: StrategyState) -> Action:
        if state.step == 0 and state.cash >= state.price:
            return Action("buy", qty=int(state.cash // state.price))
        return Action("hold")

The file is auto-discovered and appears in the app's strategy dropdown.

Rules the sandbox enforces (your function doesn't need to):
  * buys are capped at what cash affords (incl. costs); sells at shares held
  * every sell realises STCG on (sale price − average cost basis)
  * there is NO edge in the sandbox — outcomes depend entirely on the
    price path you configured, not on the tool
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class StrategyState:
    """Everything a strategy is allowed to see at one price step."""

    step: int                 # 0-based index of the current price step
    price: float              # current market price, ₹/share
    cash: float               # cash available to deploy, ₹
    shares: int               # shares currently held
    avg_cost: float           # average cost basis of held shares, ₹/share
    history: list[float] = field(default_factory=list)  # prices before `step`


@dataclass
class Action:
    """What the strategy wants to do at this step."""

    kind: Literal["buy", "sell", "hold"]
    qty: int = 0  # ignored for "hold"


def strategy(state: StrategyState) -> Action:  # pragma: no cover - reference impl
    """Reference no-op strategy (documents the required signature)."""
    return Action("hold")
