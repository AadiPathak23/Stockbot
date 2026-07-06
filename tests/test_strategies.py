from strategies import discover_strategies
from strategies.base import Action, StrategyState
from strategies.buy_and_hold import strategy as buy_and_hold


def _state(**kw):
    defaults = dict(step=0, price=100.0, cash=1000.0, shares=0, avg_cost=0.0, history=[])
    defaults.update(kw)
    return StrategyState(**defaults)


def test_discovery_finds_builtins_not_base():
    found = discover_strategies()
    assert {"Buy & hold", "Cycle trader", "Dip buyer (+5% target)"} <= set(found)
    assert "base" not in found
    assert all(callable(fn) for fn in found.values())


def test_buy_and_hold_buys_once():
    first = buy_and_hold(_state(step=0))
    later = buy_and_hold(_state(step=3, shares=10))
    assert first.kind == "buy" and first.qty > 0
    assert later.kind == "hold"


def test_dip_buyer_logic():
    from strategies.dip_buyer import strategy as dip

    assert dip(_state(step=0, history=[])).kind == "hold"          # no history yet
    assert dip(_state(step=1, history=[100.0], price=95.0)).kind == "buy"
    assert dip(_state(step=1, history=[100.0], price=105.0)).kind == "hold"
    holding = _state(step=2, shares=10, avg_cost=95.0, history=[100.0, 95.0])
    assert dip(_state(**{**holding.__dict__, "price": 101.0})).kind == "sell"
    assert dip(_state(**{**holding.__dict__, "price": 96.0})).kind == "hold"
