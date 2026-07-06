"""Phase 1 (allotment harvesting) engine tests.

Hand-computed reference numbers use the project defaults:
1980 shares, fixed ₹3700, market ₹4700, STCG 20.8%,
costs 0.1%/side + ₹20/order.
"""

import pytest

from engine import (
    AllotmentConfig,
    CostModel,
    TaxModel,
    Tranche,
    even_tranches,
    run_allotment_harvest,
)

CONFIG = AllotmentConfig(total_shares=1980, fixed_price=3700.0)
TAX = TaxModel(stcg_rate=0.208)
NO_COSTS = CostModel(enabled=False)
COSTS = CostModel(pct_per_side=0.001, flat_per_order=20.0)


def test_single_sale_gross_spread():
    result = run_allotment_harvest(
        CONFIG, [Tranche(1980, 4700.0)], NO_COSTS, TAX
    )
    # (4700 − 3700) × 1980
    assert result.gross_spread == pytest.approx(1_980_000.0)
    assert result.shares_exercised == 1980


def test_tax_without_costs():
    result = run_allotment_harvest(
        CONFIG, [Tranche(1980, 4700.0)], NO_COSTS, TAX
    )
    assert result.total_tax == pytest.approx(0.208 * 1_980_000.0)  # 411,840
    assert result.net_proceeds == pytest.approx(1_980_000.0 - 411_840.0)


def test_costs_reduce_taxable_gain_and_net():
    result = run_allotment_harvest(
        CONFIG, [Tranche(1980, 4700.0)], COSTS, TAX
    )
    buy_cost = 1980 * 3700 * 0.001 + 20    # 7,346
    sell_cost = 1980 * 4700 * 0.001 + 20   # 9,326
    taxable = 1_980_000.0 - buy_cost - sell_cost
    tax = 0.208 * taxable

    t = result.tranches[0]
    assert t.buy_cost == pytest.approx(buy_cost)
    assert t.sell_cost == pytest.approx(sell_cost)
    assert t.taxable_gain == pytest.approx(taxable)
    assert result.total_tax == pytest.approx(tax)
    assert result.net_proceeds == pytest.approx(
        1_980_000.0 - buy_cost - sell_cost - tax
    )


def test_never_exercise_below_fixed_price():
    """The unexercised allotment is a free call option: below ₹3700 the
    rational value of exercising is negative, so the tranche is skipped."""
    result = run_allotment_harvest(
        CONFIG, [Tranche(1980, 3600.0)], COSTS, TAX
    )
    t = result.tranches[0]
    assert not t.exercised
    assert result.shares_exercised == 0
    assert result.shares_skipped == 1980
    assert result.gross_spread == 0.0
    assert result.total_tax == 0.0
    assert result.net_proceeds == 0.0
    assert result.cashflow == []


def test_at_the_money_costs_never_produce_negative_tax():
    """Selling exactly at ₹3700 with costs on → taxable gain is negative,
    tax must floor at zero (no negative tax credit)."""
    result = run_allotment_harvest(
        CONFIG, [Tranche(100, 3700.0)], COSTS, TAX
    )
    t = result.tranches[0]
    assert t.exercised
    assert t.taxable_gain < 0
    assert t.tax == 0.0
    assert t.net_proceeds == pytest.approx(-(t.buy_cost + t.sell_cost))


def test_even_tranches_split_exactly():
    tranches = even_tranches(1980, 4, 4700.0)
    assert [t.qty for t in tranches] == [495, 495, 495, 495]

    tranches = even_tranches(1980, 7, 4700.0)
    assert sum(t.qty for t in tranches) == 1980
    assert max(t.qty for t in tranches) - min(t.qty for t in tranches) <= 1


def test_even_tranches_per_tranche_prices():
    tranches = even_tranches(1980, 3, [4700.0, 4800.0, 4600.0])
    assert [t.sell_price for t in tranches] == [4700.0, 4800.0, 4600.0]

    with pytest.raises(ValueError):
        even_tranches(1980, 3, [4700.0, 4800.0])  # wrong length


def test_tranching_matches_single_sale_except_flat_fees():
    """Same total qty at the same price: percentage costs and tax are
    identical; the only difference is the extra flat ₹20 per order."""
    one = run_allotment_harvest(
        CONFIG, even_tranches(1980, 1, 4700.0), COSTS, TAX
    )
    four = run_allotment_harvest(
        CONFIG, even_tranches(1980, 4, 4700.0), COSTS, TAX
    )
    extra_orders = (4 - 1) * 2  # 3 extra tranches × 2 sides
    extra_flat = extra_orders * 20.0
    # tax shrinks slightly because the extra fees are deductible
    tax_saved = 0.208 * extra_flat
    assert four.net_proceeds == pytest.approx(
        one.net_proceeds - extra_flat + tax_saved
    )


def test_peak_cash_deployed_is_per_tranche_not_total():
    """Tranches run sequentially, so 4 tranches need ~1/4 of the cash a
    single all-at-once exercise needs."""
    one = run_allotment_harvest(
        CONFIG, even_tranches(1980, 1, 4700.0), NO_COSTS, TAX
    )
    four = run_allotment_harvest(
        CONFIG, even_tranches(1980, 4, 4700.0), NO_COSTS, TAX
    )
    assert one.peak_cash_deployed == pytest.approx(1980 * 3700.0)
    assert four.peak_cash_deployed == pytest.approx(495 * 3700.0)


def test_cashflow_timeline_ends_at_net_proceeds():
    result = run_allotment_harvest(
        CONFIG, even_tranches(1980, 4, 4700.0), COSTS, TAX
    )
    assert len(result.cashflow) == 8  # 4 × (exercise + sell)
    assert result.cashflow[-1].cumulative == pytest.approx(result.net_proceeds)


def test_cannot_sell_more_than_the_allotment():
    with pytest.raises(ValueError, match="1980"):
        run_allotment_harvest(CONFIG, [Tranche(1981, 4700.0)], NO_COSTS, TAX)


def test_rejects_non_positive_tranche_qty():
    with pytest.raises(ValueError):
        run_allotment_harvest(CONFIG, [Tranche(0, 4700.0)], NO_COSTS, TAX)


def test_costs_toggle_off_means_zero_friction():
    result = run_allotment_harvest(
        CONFIG, [Tranche(500, 4700.0)], CostModel(enabled=False), TAX
    )
    t = result.tranches[0]
    assert t.buy_cost == 0.0
    assert t.sell_cost == 0.0
    assert t.taxable_gain == pytest.approx(t.gross_spread)
