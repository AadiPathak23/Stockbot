"""Price-path generators for the Phase 2 trading sandbox.

These produce the *assumed* price paths the sandbox trades against. None of
them predict anything: fixed_move and monte_carlo_gbm turn user assumptions
into numbers, from_csv replays history the user supplies.
"""

import numpy as np
import pandas as pd


def fixed_move(start: float, pct_per_cycle: float, n_cycles: int) -> list[float]:
    """Deterministic compounding path: price moves ``pct_per_cycle`` (e.g.
    0.05 = +5%, -0.03 = −3%) each cycle for ``n_cycles`` cycles.

    Returns ``n_cycles + 1`` prices, starting with ``start`` itself.
    """
    if start <= 0:
        raise ValueError("start price must be positive")
    if n_cycles < 1:
        raise ValueError("need at least 1 cycle")
    if pct_per_cycle <= -1:
        raise ValueError("a move of -100% or worse is not a price path")
    return [start * (1 + pct_per_cycle) ** i for i in range(n_cycles + 1)]


def from_csv(df: pd.DataFrame) -> list[float]:
    """Extract a price path from an uploaded CSV.

    Requires a ``close`` column (case-insensitive). If a ``date`` column is
    present, rows are sorted by it. All prices must be positive numbers.
    """
    cols = {str(c).lower().strip(): c for c in df.columns}
    if "close" not in cols:
        raise ValueError("CSV must have a 'close' column")

    out = df.copy()
    if "date" in cols:
        out[cols["date"]] = pd.to_datetime(out[cols["date"]], errors="raise")
        out = out.sort_values(cols["date"])

    prices = pd.to_numeric(out[cols["close"]], errors="coerce").astype(float)
    if prices.isna().any():
        raise ValueError("'close' column contains non-numeric values")
    if (prices <= 0).any():
        raise ValueError("all prices must be positive")
    if len(prices) < 2:
        raise ValueError("need at least 2 rows to trade against")
    return prices.tolist()


def monte_carlo_gbm(
    start: float,
    annual_drift: float,
    annual_vol: float,
    n_steps: int,
    n_paths: int,
    seed: int | None = None,
    steps_per_year: int = 252,
) -> np.ndarray:
    """Geometric Brownian motion paths.

    S_{t+1} = S_t · exp((μ − σ²/2)·Δt + σ·√Δt·Z),  Δt = 1/steps_per_year

    Returns an array of shape ``(n_paths, n_steps + 1)``; column 0 is
    ``start`` on every path. Seeded for reproducibility.
    """
    if start <= 0:
        raise ValueError("start price must be positive")
    if n_steps < 1 or n_paths < 1:
        raise ValueError("n_steps and n_paths must be >= 1")
    if annual_vol < 0:
        raise ValueError("volatility cannot be negative")

    rng = np.random.default_rng(seed)
    dt = 1.0 / steps_per_year
    z = rng.standard_normal((n_paths, n_steps))
    increments = (annual_drift - 0.5 * annual_vol**2) * dt + annual_vol * np.sqrt(dt) * z
    log_growth = np.cumsum(increments, axis=1)
    paths = start * np.exp(np.hstack([np.zeros((n_paths, 1)), log_growth]))
    return paths
