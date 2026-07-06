"""Trading-sandbox engine tests with hand-computed reference numbers."""

import pytest

from engine import CostModel, TaxModel, fixed_move, max_affordable_qty, run_sandbox
from strategies.base import Action
from strategies.buy_and_hold import strategy as buy_and_hold
from strategies.cycle_trader import strategy as cycle_trader

TAX = TaxModel(stcg_rate=0.208)
NO_COSTS = CostModel(enabled=False)
COSTS = CostModel(pct_per_side=0.001, flat_per_order=20.0)


def test_max_affordable_qty():
    assert max_affordable_qty(1000.0, 100.0, NO_COSTS) == 10
    # flat ₹20 only: (1000 − 20) // 100 = 9
    assert max_affordable_qty(1000.0, 100.0, CostModel(0.0, 20.0)) == 9
    # 0.1% + ₹20: 980 // 100.1 = 9
    assert max_affordable_qty(1000.0, 100.0, COSTS) == 9
    assert max_affordable_qty(10.0, 100.0, COSTS) == 0
    assert max_affordable_qty(0.0, 100.0, NO_COSTS) == 0


def test_buy_and_hold_hand_computed():
    """₹1000, path 100→110→120, no costs: buy 10 @100, liquidate @120,
    gain 200, tax 41.6, net 158.4."""
    r = run_sandbox(1000.0, [100.0, 110.0, 120.0], buy_and_hold, NO_COSTS, TAX)
    assert r.gross_profit == pytest.approx(200.0)
    assert r.total_tax == pytest.approx(41.6)
    assert r.net_profit == pytest.approx(158.4)
    assert r.total_costs == 0.0
    assert r.final_shares == 0
    assert r.final_cash == pytest.approx(1158.4)
    assert r.peak_cash_deployed == pytest.approx(1000.0)
    assert r.cash_series == pytest.approx([0.0, 0.0, 1158.4])
    assert r.equity_series == pytest.approx([1000.0, 1100.0, 1158.4])


def test_buy_capped_by_cash_including_costs():
    r = run_sandbox(1000.0, [100.0, 100.0], buy_and_hold, CostModel(0.0, 20.0), TAX)
    buy = r.trades[0]
    assert buy.kind == "buy"
    assert buy.qty == 9  # not 10 — the flat ₹20 must also be payable
    assert buy.cost == 20.0


def test_sell_capped_at_holdings():
    def overseller(state):
        if state.step == 0:
            return Action("buy", 5)
        return Action("sell", 999)

    r = run_sandbox(1000.0, [100.0, 110.0], overseller, NO_COSTS, TAX)
    sells = [t for t in r.trades if t.kind == "sell"]
    assert len(sells) == 1
    assert sells[0].qty == 5


def test_weighted_average_cost_basis():
    """Buy 5 @100 then 5 @120 → avg cost 110; liquidate @120 → gain 100."""
    def two_buys(state):
        if state.step == 0:
            return Action("buy", 5)
        if state.step == 1:
            return Action("buy", 5)
        return Action("hold")

    r = run_sandbox(2000.0, [100.0, 120.0, 120.0], two_buys, NO_COSTS, TAX)
    liq = r.trades[-1]
    assert liq.kind == "sell"
    assert liq.realized_gain == pytest.approx(10 * (120.0 - 110.0))


def test_tax_netting_vs_per_sale():
    """Path 100→80→80→120: lose 200, then make 400.
    Netting taxes 200; per-sale taxes the full 400."""
    def churn(state):
        if state.step == 0:
            return Action("buy", 10)
        if state.step == 1:
            return Action("sell", 10)
        if state.step == 2:
            return Action("buy", 10)
        return Action("hold")

    path = [100.0, 80.0, 80.0, 120.0]
    netted = run_sandbox(1000.0, path, churn, NO_COSTS, TAX, tax_netting=True)
    per_sale = run_sandbox(1000.0, path, churn, NO_COSTS, TAX, tax_netting=False)

    assert netted.total_tax == pytest.approx(0.208 * 200.0)   # 41.6
    assert netted.net_profit == pytest.approx(158.4)
    assert per_sale.total_tax == pytest.approx(0.208 * 400.0)  # 83.2
    assert per_sale.net_profit == pytest.approx(116.8)


def test_no_liquidation_keeps_unrealized_untaxed():
    r = run_sandbox(
        1000.0, [100.0, 110.0], buy_and_hold, NO_COSTS, TAX, liquidate_at_end=False
    )
    assert r.final_shares == 10
    assert r.total_tax == 0.0
    assert r.net_profit == pytest.approx(100.0)  # mark-to-market
    assert r.gross_profit == pytest.approx(100.0)


def test_flat_path_with_costs_loses_exactly_the_friction():
    """No price movement → the only P&L is brokerage (taxable gain < 0 → no tax)."""
    r = run_sandbox(100_000.0, [100.0, 100.0, 100.0], buy_and_hold, COSTS, TAX)
    assert r.total_tax == 0.0
    assert r.net_profit == pytest.approx(-r.total_costs)


def test_cycle_trader_alternates_and_pays_more_friction():
    """On the same rising path, churn must net less than buy & hold once
    costs are on (same spread captured, more brokerage, earlier tax)."""
    path = fixed_move(100.0, 0.05, 6)
    hold = run_sandbox(100_000.0, path, buy_and_hold, COSTS, TAX)
    cycle = run_sandbox(100_000.0, path, cycle_trader, COSTS, TAX)

    kinds = [t.kind for t in cycle.trades]
    assert kinds[:4] == ["buy", "sell", "buy", "sell"]
    assert cycle.total_costs > hold.total_costs
    assert cycle.net_profit < hold.net_profit


def test_unknown_action_kind_raises():
    with pytest.raises(ValueError, match="unknown action"):
        run_sandbox(1000.0, [100.0], lambda s: Action("short", 5), NO_COSTS, TAX)


def test_empty_path_raises():
    with pytest.raises(ValueError):
        run_sandbox(1000.0, [], buy_and_hold, NO_COSTS, TAX)


def test_monte_carlo_distribution():
    from engine import monte_carlo_gbm, run_monte_carlo

    paths = monte_carlo_gbm(100.0, 0.08, 0.25, n_steps=30, n_paths=40, seed=7)
    mc = run_monte_carlo(1000.0, paths, buy_and_hold, NO_COSTS, TAX)
    assert mc.net_profits.shape == (40,)
    assert mc.percentiles[5] <= mc.percentiles[50] <= mc.percentiles[95]
    assert 0.0 <= mc.prob_loss <= 1.0
    assert len(mc.sample_results) == 20
