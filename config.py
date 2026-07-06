"""Configurable defaults for the share-strategy-modeler.

Every value here is a *default* — the Streamlit UI exposes each one as an
editable input. Change them here to change what the app starts with.
"""

from datetime import date

DEFAULTS = {
    # --- Allotment right (Phase 1) ---
    "total_shares": 1980,        # shares purchasable at the fixed price
    "fixed_price": 3700.0,       # ₹ per share, exercise price
    "market_price": 4700.0,      # ₹ per share, current market price
    "deadline": date(2026, 10, 31),  # last date the right is exercisable

    # --- Tax ---
    # Indian STCG on listed equity: 20% + 4% cess = 20.8% effective,
    # applied to (sale price − cost basis) on every short-term sale.
    "stcg_rate": 0.208,

    # --- Transaction costs (toggleable) ---
    "costs_enabled": True,
    "cost_pct_per_side": 0.001,   # 0.1% of notional, charged on buy AND sell
    "cost_flat_per_order": 20.0,  # ₹ flat per order
}
