"""Phase 1 — Allotment harvesting.

Model exercising the fixed-price allotment and selling into the market:

  * per tranche: exercise (buy at fixed price) → sell at the tranche's
    market price → pay brokerage on both sides → pay STCG on the gain
  * the unexercised allotment is a free call option: a tranche whose sell
    price is below the fixed price is *never* exercised (skipped, zero cost)
  * tranches execute sequentially, so peak cash deployed is the largest
    single tranche outlay, not the whole allotment at once

Taxable gain per tranche follows Indian capital-gains mechanics: net sale
consideration (sale − sell-side costs) minus total acquisition cost
(exercise outlay + buy-side costs). Tax is floored at zero per tranche.
"""

from engine.models import (
    AllotmentConfig,
    AllotmentResult,
    CashflowEvent,
    CostModel,
    TaxModel,
    Tranche,
    TrancheResult,
)


def even_tranches(total_shares: int, n: int, sell_prices) -> list[Tranche]:
    """Split ``total_shares`` into ``n`` near-equal tranches.

    ``sell_prices`` is either a single price (applied to every tranche) or a
    sequence of ``n`` prices, one per tranche. Remainder shares go to the
    earliest tranches, so quantities always sum to ``total_shares``.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    if total_shares < n:
        raise ValueError("cannot split into more tranches than shares")

    if isinstance(sell_prices, (int, float)):
        prices = [float(sell_prices)] * n
    else:
        prices = [float(p) for p in sell_prices]
        if len(prices) != n:
            raise ValueError(f"expected {n} prices, got {len(prices)}")

    base, remainder = divmod(total_shares, n)
    return [
        Tranche(qty=base + (1 if i < remainder else 0), sell_price=prices[i])
        for i in range(n)
    ]


def run_allotment_harvest(
    config: AllotmentConfig,
    tranches: list[Tranche],
    cost_model: CostModel,
    tax_model: TaxModel,
) -> AllotmentResult:
    """Execute the exercise-and-sell plan and return per-tranche economics
    plus a cashflow timeline."""
    total_qty = sum(t.qty for t in tranches)
    if total_qty > config.total_shares:
        raise ValueError(
            f"plan sells {total_qty} shares but the allotment is only "
            f"{config.total_shares}"
        )
    if any(t.qty <= 0 for t in tranches):
        raise ValueError("every tranche must have qty > 0")

    result = AllotmentResult()
    cash = 0.0
    step = 0

    for i, tranche in enumerate(tranches, start=1):
        # Free call option: exercising below the fixed price locks in a
        # guaranteed loss, so the rational move is to let it lapse.
        if tranche.sell_price < config.fixed_price:
            result.tranches.append(
                TrancheResult(
                    qty=tranche.qty,
                    sell_price=tranche.sell_price,
                    exercised=False,
                )
            )
            continue

        buy_notional = tranche.qty * config.fixed_price
        buy_cost = cost_model.order_cost(buy_notional)
        sell_notional = tranche.qty * tranche.sell_price
        sell_cost = cost_model.order_cost(sell_notional)

        gross_spread = sell_notional - buy_notional
        taxable_gain = (sell_notional - sell_cost) - (buy_notional + buy_cost)
        tax = tax_model.tax_on_gain(taxable_gain)
        net_proceeds = gross_spread - buy_cost - sell_cost - tax

        result.tranches.append(
            TrancheResult(
                qty=tranche.qty,
                sell_price=tranche.sell_price,
                exercised=True,
                buy_notional=buy_notional,
                buy_cost=buy_cost,
                sell_notional=sell_notional,
                sell_cost=sell_cost,
                gross_spread=gross_spread,
                taxable_gain=taxable_gain,
                tax=tax,
                net_proceeds=net_proceeds,
                cash_deployed=buy_notional + buy_cost,
            )
        )

        step += 1
        cash -= buy_notional + buy_cost
        result.cashflow.append(
            CashflowEvent(step, f"Exercise tranche {i} ({tranche.qty} sh)", -(buy_notional + buy_cost), cash)
        )
        step += 1
        inflow = sell_notional - sell_cost - tax
        cash += inflow
        result.cashflow.append(
            CashflowEvent(step, f"Sell tranche {i} ({tranche.qty} sh, post-tax)", inflow, cash)
        )

    return result
