"""Phase 2 — Reinvestment / trading sandbox.

Runs a pluggable strategy (see ``strategies/base.py``) over a price path,
enforcing the rules a strategy is not allowed to break:

  * buys are capped at what cash affords INCLUDING costs
  * sells are capped at shares held
  * cost basis is weighted-average, and includes buy-side costs
    (matching Indian acquisition-cost treatment and Phase 1)
  * every sell realizes STCG on (net sale consideration − avg_cost·qty);
    with ``tax_netting=True`` gains and losses net across the run and tax
    is settled once at the end (realistic annual netting); with ``False``
    each sale is taxed independently with a floor at zero
  * ``liquidate_at_end=True`` force-sells at the last price so strategies
    are comparable on realized cash

IMPORTANT: this sandbox has NO built-in edge. Every rupee of modeled
profit comes from the user's assumed price path, not from the tool.
"""

from dataclasses import dataclass, field

import numpy as np

from engine.models import CostModel, TaxModel
from strategies.base import Action, StrategyState


@dataclass
class Trade:
    step: int
    kind: str          # "buy" | "sell"
    qty: int
    price: float
    cost: float                 # brokerage on this order
    realized_gain: float = 0.0  # sells only (net of costs both sides via basis)
    tax: float = 0.0            # per-sale tax mode only


@dataclass
class SandboxResult:
    initial_cash: float
    trades: list[Trade] = field(default_factory=list)
    cash_series: list[float] = field(default_factory=list)    # cash after each step
    equity_series: list[float] = field(default_factory=list)  # cash + shares·price
    final_cash: float = 0.0
    final_shares: int = 0
    gross_profit: float = 0.0
    total_costs: float = 0.0
    total_tax: float = 0.0
    net_profit: float = 0.0
    peak_cash_deployed: float = 0.0
    max_drawdown: float = 0.0   # worst peak-to-trough of equity, in ₹


def max_affordable_qty(cash: float, price: float, cost_model: CostModel) -> int:
    """Largest integer qty with qty·price + order_cost(qty·price) ≤ cash."""
    if price <= 0 or cash <= 0:
        return 0
    if not cost_model.enabled:
        return int(cash // price)
    budget = cash - cost_model.flat_per_order
    if budget <= 0:
        return 0
    return max(0, int(budget // (price * (1 + cost_model.pct_per_side))))


def run_sandbox(
    initial_cash: float,
    prices,
    strategy_fn,
    cost_model: CostModel,
    tax_model: TaxModel,
    liquidate_at_end: bool = True,
    tax_netting: bool = True,
) -> SandboxResult:
    prices = [float(p) for p in prices]
    if len(prices) < 1:
        raise ValueError("price path is empty")
    if initial_cash < 0:
        raise ValueError("initial cash cannot be negative")

    cash = initial_cash
    shares = 0
    avg_cost = 0.0
    trades: list[Trade] = []
    realized_gains: list[float] = []
    cash_series: list[float] = []
    equity_series: list[float] = []
    total_buy_notional = 0.0
    total_sell_notional = 0.0
    total_costs = 0.0
    total_tax = 0.0

    def do_buy(step: int, qty: int, price: float) -> None:
        nonlocal cash, shares, avg_cost, total_buy_notional, total_costs
        qty = min(int(qty), max_affordable_qty(cash, price, cost_model))
        if qty <= 0:
            return
        notional = qty * price
        cost = cost_model.order_cost(notional)
        cash -= notional + cost
        avg_cost = (shares * avg_cost + notional + cost) / (shares + qty)
        shares += qty
        total_buy_notional += notional
        total_costs += cost
        trades.append(Trade(step, "buy", qty, price, cost))

    def do_sell(step: int, qty: int, price: float) -> None:
        nonlocal cash, shares, avg_cost, total_sell_notional, total_costs, total_tax
        qty = min(int(qty), shares)
        if qty <= 0:
            return
        notional = qty * price
        cost = cost_model.order_cost(notional)
        gain = (notional - cost) - avg_cost * qty
        tax = 0.0 if tax_netting else tax_model.tax_on_gain(gain)
        cash += notional - cost - tax
        shares -= qty
        if shares == 0:
            avg_cost = 0.0
        realized_gains.append(gain)
        total_sell_notional += notional
        total_costs += cost
        total_tax += tax
        trades.append(Trade(step, "sell", qty, price, cost, gain, tax))

    for step, price in enumerate(prices):
        state = StrategyState(
            step=step, price=price, cash=cash, shares=shares,
            avg_cost=avg_cost, history=prices[:step],
        )
        action = strategy_fn(state) or Action("hold")
        if action.kind == "buy":
            do_buy(step, action.qty, price)
        elif action.kind == "sell":
            do_sell(step, action.qty, price)
        elif action.kind != "hold":
            raise ValueError(f"strategy returned unknown action kind: {action.kind!r}")
        cash_series.append(cash)
        equity_series.append(cash + shares * price)

    # Peak deployment is measured on end-of-step cash, before settlement.
    peak_cash_deployed = max(0.0, initial_cash - min(cash_series))

    last_price = prices[-1]
    if liquidate_at_end and shares > 0:
        do_sell(len(prices) - 1, shares, last_price)
    if tax_netting:
        end_tax = tax_model.tax_on_gain(sum(realized_gains))
        cash -= end_tax
        total_tax += end_tax
    cash_series[-1] = cash
    equity_series[-1] = cash + shares * last_price

    max_dd = 0.0
    peak_eq = float("-inf")
    for eq in equity_series:
        peak_eq = max(peak_eq, eq)
        max_dd = max(max_dd, peak_eq - eq)

    result = SandboxResult(
        initial_cash=initial_cash,
        trades=trades,
        cash_series=cash_series,
        equity_series=equity_series,
        final_cash=cash,
        final_shares=shares,
        gross_profit=total_sell_notional - total_buy_notional + shares * last_price,
        total_costs=total_costs,
        total_tax=total_tax,
        net_profit=(cash + shares * last_price) - initial_cash,
        peak_cash_deployed=peak_cash_deployed,
        max_drawdown=max_dd,
    )
    return result


@dataclass
class MonteCarloResult:
    net_profits: np.ndarray
    percentiles: dict            # {5: ₹, 25: ₹, 50: ₹, 75: ₹, 95: ₹}
    prob_loss: float             # fraction of paths ending below breakeven
    sample_results: list[SandboxResult]  # first few full runs, for fan charts


def run_monte_carlo(
    initial_cash: float,
    paths: np.ndarray,
    strategy_fn,
    cost_model: CostModel,
    tax_model: TaxModel,
    liquidate_at_end: bool = True,
    tax_netting: bool = True,
    n_samples: int = 20,
) -> MonteCarloResult:
    """Run the same strategy over every path; return the outcome distribution."""
    nets = []
    samples: list[SandboxResult] = []
    for i, path in enumerate(paths):
        r = run_sandbox(
            initial_cash, list(path), strategy_fn, cost_model, tax_model,
            liquidate_at_end=liquidate_at_end, tax_netting=tax_netting,
        )
        nets.append(r.net_profit)
        if i < n_samples:
            samples.append(r)
    nets = np.asarray(nets)
    percentiles = {p: float(np.percentile(nets, p)) for p in (5, 25, 50, 75, 95)}
    return MonteCarloResult(
        net_profits=nets,
        percentiles=percentiles,
        prob_loss=float((nets < 0).mean()),
        sample_results=samples,
    )
