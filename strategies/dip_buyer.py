"""Dip buyer: buy all-in after a down step, sell once the position is up
TARGET_GAIN over its (cost-inclusive) average cost.

This is the template to copy for your own strategy — it shows how to use
``history``, ``avg_cost`` and holdings from the state. Duplicate this file,
rename STRATEGY_NAME, edit the logic, and it appears in the app dropdown.
"""

from strategies.base import Action, StrategyState

STRATEGY_NAME = "Dip buyer (+5% target)"

TARGET_GAIN = 0.05  # sell when price ≥ avg_cost × (1 + TARGET_GAIN)


def strategy(state: StrategyState) -> Action:
    if state.shares == 0:
        if state.history and state.price < state.history[-1]:
            return Action("buy", qty=10**9)
        return Action("hold")
    if state.price >= state.avg_cost * (1 + TARGET_GAIN):
        return Action("sell", qty=state.shares)
    return Action("hold")
