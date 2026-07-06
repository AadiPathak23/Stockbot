"""Cycle trader: all-in buy whenever flat, sell everything the next step.

Deliberately maximal churn — pairs with the "fixed % move per cycle" path
mode to make the brokerage + STCG drag of repeated round-trips visible.
"""

from strategies.base import Action, StrategyState

STRATEGY_NAME = "Cycle trader"


def strategy(state: StrategyState) -> Action:
    if state.shares == 0:
        return Action("buy", qty=10**9)
    return Action("sell", qty=state.shares)
