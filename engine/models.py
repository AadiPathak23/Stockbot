"""Core data models shared by both phases of the modeler."""

from dataclasses import dataclass, field


@dataclass
class CostModel:
    """Brokerage / transaction costs, charged once per order (per side).

    cost = notional * pct_per_side + flat_per_order

    Set ``enabled=False`` to model a frictionless world.
    """

    pct_per_side: float = 0.001
    flat_per_order: float = 20.0
    enabled: bool = True

    def order_cost(self, notional: float) -> float:
        if not self.enabled or notional <= 0:
            return 0.0
        return notional * self.pct_per_side + self.flat_per_order


@dataclass
class TaxModel:
    """Indian STCG on listed equity: flat rate on the gain of every sale.

    Default 20.8% = 20% STCG + 4% cess. Losses produce zero tax here
    (loss set-off across sales is out of scope for per-tranche modeling).
    """

    stcg_rate: float = 0.208

    def tax_on_gain(self, gain: float) -> float:
        return self.stcg_rate * max(0.0, gain)


@dataclass
class AllotmentConfig:
    """The right to buy ``total_shares`` at ``fixed_price``, in unlimited
    chunks, until a deadline. Share #(total_shares+1) onward costs market
    price — that is Phase 2's territory, not this config's.
    """

    total_shares: int = 1980
    fixed_price: float = 3700.0


@dataclass
class Tranche:
    """One planned exercise-and-sell batch: buy ``qty`` at the fixed price,
    sell the same ``qty`` at ``sell_price``."""

    qty: int
    sell_price: float


@dataclass
class TrancheResult:
    qty: int
    sell_price: float
    exercised: bool
    buy_notional: float = 0.0
    buy_cost: float = 0.0
    sell_notional: float = 0.0
    sell_cost: float = 0.0
    gross_spread: float = 0.0
    taxable_gain: float = 0.0
    tax: float = 0.0
    net_proceeds: float = 0.0
    cash_deployed: float = 0.0  # peak cash out the door for this tranche


@dataclass
class CashflowEvent:
    step: int
    label: str
    amount: float      # negative = cash out, positive = cash in
    cumulative: float  # running cash position after this event


@dataclass
class AllotmentResult:
    tranches: list[TrancheResult] = field(default_factory=list)
    cashflow: list[CashflowEvent] = field(default_factory=list)

    @property
    def shares_exercised(self) -> int:
        return sum(t.qty for t in self.tranches if t.exercised)

    @property
    def shares_skipped(self) -> int:
        return sum(t.qty for t in self.tranches if not t.exercised)

    @property
    def gross_spread(self) -> float:
        return sum(t.gross_spread for t in self.tranches)

    @property
    def total_costs(self) -> float:
        return sum(t.buy_cost + t.sell_cost for t in self.tranches)

    @property
    def total_tax(self) -> float:
        return sum(t.tax for t in self.tranches)

    @property
    def net_proceeds(self) -> float:
        """Net profit of the harvest: spread − costs − tax."""
        return sum(t.net_proceeds for t in self.tranches)

    @property
    def peak_cash_deployed(self) -> float:
        """Max cash simultaneously out the door. Tranches run sequentially
        (exercise → sell → next tranche), so the peak is the largest single
        tranche outlay, not the sum."""
        return max((t.cash_deployed for t in self.tranches), default=0.0)
