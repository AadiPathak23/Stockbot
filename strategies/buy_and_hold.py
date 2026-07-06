"""Buy & hold: go all-in on the first step, never trade again.

The baseline every other strategy should be compared against — it pays
brokerage twice (entry + final liquidation) and tax once.
"""

from strategies.base import Action, StrategyState

STRATEGY_NAME = "Buy & hold"


def strategy(state: StrategyState) -> Action:
    if state.step == 0:
        return Action("buy", qty=10**9)  # the sandbox caps at what cash affords
    return Action("hold")
