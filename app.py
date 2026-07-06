"""share-strategy-modeler — Streamlit UI.

Phase 1: allotment harvesting (fixed-price exercise → market sale).
Phase 2: reinvestment/trading sandbox — NO built-in edge; outcomes depend
entirely on user-assumed price paths.
"""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DEFAULTS
from engine import (
    AllotmentConfig,
    CostModel,
    TaxModel,
    even_tranches,
    fixed_move,
    from_csv,
    monte_carlo_gbm,
    run_allotment_harvest,
    run_monte_carlo,
    run_sandbox,
)
from strategies import discover_strategies

# --- Chart chrome (validated reference palette; light mode) ---
SLOT_COLORS = [  # categorical slots, fixed order — color follows the strategy
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]
C_INFLOW = "#2a78d6"
C_OUTFLOW = "#e34948"
C_LINE = "#2a78d6"
C_GRID = "#e1e0d9"
C_MUTED = "#898781"
C_BASELINE = "#c3c2b7"


def base_layout(**overrides):
    layout = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=C_MUTED),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(showgrid=False, linecolor=C_BASELINE, zeroline=False),
        yaxis=dict(gridcolor=C_GRID, gridwidth=1, zerolinecolor=C_BASELINE, zerolinewidth=1),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    layout.update(overrides)
    return layout


st.set_page_config(page_title="Share Strategy Modeler", layout="wide")

st.title("Share Strategy Modeler")
st.warning(
    "**This tool does not predict prices.** Every price used here is an "
    "assumption *you* enter. The reinvestment sandbox has no built-in edge — "
    "modeled profits come entirely from your assumed price paths. "
    "Nothing here is financial or tax advice.",
    icon="⚠️",
)

# ---------------------------------------------------------------- inputs ---
with st.sidebar:
    st.header("Parameters")

    st.subheader("Allotment right")
    total_shares = st.number_input(
        "Shares at fixed price", min_value=1, value=DEFAULTS["total_shares"], step=1
    )
    fixed_price = st.number_input(
        "Fixed (exercise) price ₹", min_value=0.0, value=DEFAULTS["fixed_price"], step=50.0
    )
    market_price = st.number_input(
        "Current market price ₹", min_value=0.01, value=DEFAULTS["market_price"], step=50.0
    )
    deadline = st.date_input("Exercise deadline", value=DEFAULTS["deadline"])
    if deadline < date.today():
        st.error("Deadline is in the past — the right has lapsed.")

    st.subheader("Tax")
    stcg_pct = st.number_input(
        "STCG rate % (incl. cess)",
        min_value=0.0, max_value=100.0,
        value=DEFAULTS["stcg_rate"] * 100, step=0.1,
        help="Indian STCG on listed equity: 20% + 4% cess = 20.8% effective, "
             "on (sale price − cost basis) per sale.",
    )
    tax_netting = st.toggle(
        "Net losses against gains (sandbox)", value=True,
        help="On: trading losses offset gains across the run and STCG is "
             "settled once at the end (realistic annual netting). "
             "Off: every profitable sale is taxed, losses give no relief.",
    )

    st.subheader("Transaction costs")
    costs_enabled = st.toggle("Apply costs", value=DEFAULTS["costs_enabled"])
    cost_pct = st.number_input(
        "% per side", min_value=0.0, value=DEFAULTS["cost_pct_per_side"] * 100,
        step=0.05, format="%.2f", disabled=not costs_enabled,
    )
    cost_flat = st.number_input(
        "Flat ₹ per order", min_value=0.0, value=DEFAULTS["cost_flat_per_order"],
        step=5.0, disabled=not costs_enabled,
    )

    st.subheader("Harvest plan (Phase 1)")
    n_tranches = st.slider("Sell in N tranches", min_value=1, max_value=20, value=4)

    st.subheader("Sandbox (Phase 2)")
    liquidate_end = st.toggle(
        "Liquidate holdings at end", value=True,
        help="Force-sell whatever a strategy still holds at the final price, "
             "so strategies are compared on realized cash.",
    )

config = AllotmentConfig(total_shares=int(total_shares), fixed_price=fixed_price)
cost_model = CostModel(
    pct_per_side=cost_pct / 100, flat_per_order=cost_flat, enabled=costs_enabled
)
tax_model = TaxModel(stcg_rate=stcg_pct / 100)

tab_harvest, tab_sandbox = st.tabs(
    ["Phase 1 · Allotment harvest", "Phase 2 · Trading sandbox"]
)

# --------------------------------------------------------------- phase 1 ---
with tab_harvest:
    st.caption(
        "Exercising below the fixed price is never modeled — the unexercised "
        "allotment is treated as a free call option and left to lapse."
    )

    same_price = st.checkbox("Sell all tranches at the current market price", value=True)
    if same_price:
        prices_p1 = [market_price] * n_tranches
    else:
        cols = st.columns(min(n_tranches, 5))
        prices_p1 = [
            cols[i % len(cols)].number_input(
                f"Tranche {i + 1} sell ₹", min_value=0.0, value=market_price,
                step=50.0, key=f"tp{i}",
            )
            for i in range(n_tranches)
        ]

    result = run_allotment_harvest(
        config, even_tranches(config.total_shares, n_tranches, prices_p1),
        cost_model, tax_model,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Gross spread", f"₹{result.gross_spread:,.0f}")
    m2.metric("Total tax", f"₹{result.total_tax:,.0f}")
    m3.metric("Net profit", f"₹{result.net_proceeds:,.0f}")
    m4.metric("Peak cash deployed", f"₹{result.peak_cash_deployed:,.0f}")
    if result.shares_skipped:
        st.info(
            f"{result.shares_skipped} shares NOT exercised (sell price below "
            f"₹{config.fixed_price:,.0f}) — the option is left to lapse."
        )

    per_tranche = pd.DataFrame(
        [
            {
                "Tranche": i + 1,
                "Qty": t.qty,
                "Sell ₹": t.sell_price,
                "Exercised": "yes" if t.exercised else "no (lapse)",
                "Gross spread ₹": t.gross_spread,
                "Costs ₹": t.buy_cost + t.sell_cost,
                "Tax ₹": t.tax,
                "Net ₹": t.net_proceeds,
                "Cash deployed ₹": t.cash_deployed,
            }
            for i, t in enumerate(result.tranches)
        ]
    )
    st.dataframe(
        per_tranche.style.format(
            {c: "{:,.0f}" for c in per_tranche.columns if c.endswith("₹")}
        ),
        use_container_width=True, hide_index=True,
    )

    if result.cashflow:
        c1, c2 = st.columns(2)
        steps = [e.step for e in result.cashflow]
        labels = [e.label for e in result.cashflow]
        amounts = [e.amount for e in result.cashflow]
        cumulative = [e.cumulative for e in result.cashflow]

        fig_cf = go.Figure()
        for name, color, keep in (
            ("Cash out (exercise)", C_OUTFLOW, lambda a: a < 0),
            ("Cash in (sale, post-tax)", C_INFLOW, lambda a: a >= 0),
        ):
            xs = [s for s, a in zip(steps, amounts) if keep(a)]
            ys = [a for a in amounts if keep(a)]
            texts = [l for l, a in zip(labels, amounts) if keep(a)]
            fig_cf.add_bar(
                x=xs, y=ys, name=name, marker_color=color, width=0.55,
                customdata=texts,
                hovertemplate="%{customdata}<br>₹%{y:,.0f}<extra></extra>",
            )
        fig_cf.update_layout(
            title="Cash flow per event", barmode="overlay",
            xaxis_title="Event", yaxis_title="₹", **base_layout(),
        )
        c1.plotly_chart(fig_cf, use_container_width=True)

        fig_cum = go.Figure(
            go.Scatter(
                x=steps, y=cumulative, mode="lines+markers",
                line=dict(color=C_LINE, width=2, shape="hv"),
                marker=dict(size=8, color=C_LINE),
                customdata=labels,
                hovertemplate="%{customdata}<br>cash: ₹%{y:,.0f}<extra></extra>",
                name="Cash position",
            )
        )
        fig_cum.update_layout(
            title="Cumulative cash position (ends at net profit)",
            xaxis_title="Event", yaxis_title="₹", showlegend=False, **base_layout(),
        )
        c2.plotly_chart(fig_cum, use_container_width=True)

# --------------------------------------------------------------- phase 2 ---
with tab_sandbox:
    st.caption(
        "**No built-in edge.** This sandbox only turns *your* price "
        "assumptions into after-tax, after-cost outcomes. A profitable result "
        "here means your assumed path was profitable — nothing more."
    )

    strat_map = discover_strategies()
    slot_of = {name: i % len(SLOT_COLORS) for i, name in enumerate(strat_map)}

    top1, top2 = st.columns([1, 1])
    with top1:
        use_p1 = st.toggle(
            f"Start with Phase 1 net proceeds (₹{result.net_proceeds:,.0f})",
            value=True,
        )
        if use_p1:
            start_cash = float(result.net_proceeds)
        else:
            start_cash = st.number_input(
                "Starting cash ₹", min_value=0.0, value=1_500_000.0, step=50_000.0
            )
    with top2:
        chosen = st.multiselect(
            "Strategies to compare (side by side)",
            list(strat_map),
            default=[n for n in ("Buy & hold", "Cycle trader") if n in strat_map],
            help="Drop your own .py into strategies/ (see strategies/base.py) "
                 "and it appears here.",
        )

    mode = st.radio(
        "Price path mode",
        ["Fixed % move", "CSV upload", "Monte Carlo"],
        horizontal=True,
    )

    prices = None
    mc_paths = None
    if mode == "Fixed % move":
        f1, f2 = st.columns(2)
        move_pct = f1.number_input(
            "Move per cycle %", min_value=-99.0, value=5.0, step=0.5, format="%.1f"
        )
        cycles = f2.slider("Number of cycles", 1, 60, 6)
        prices = fixed_move(market_price, move_pct / 100, cycles)

    elif mode == "CSV upload":
        up = st.file_uploader(
            "CSV with a 'close' column (optional 'date' column)", type=["csv"]
        )
        if up is None:
            st.info("Upload a CSV of historical prices to run this mode.")
        else:
            try:
                df_up = pd.read_csv(up)
                prices = from_csv(df_up)
                with st.expander(f"Preview — {len(prices)} prices"):
                    st.dataframe(df_up.head(20), use_container_width=True)
            except Exception as exc:
                st.error(f"Could not read the CSV: {exc}")

    else:  # Monte Carlo
        g1, g2, g3, g4, g5 = st.columns(5)
        drift_pct = g1.number_input("Annual drift %", value=8.0, step=1.0)
        vol_pct = g2.number_input("Annual volatility %", min_value=0.0, value=25.0, step=1.0)
        n_steps = g3.slider("Trading days", 20, 504, 126)
        n_paths = g4.slider("Paths", 50, 1000, 200, step=50)
        seed = g5.number_input("Seed", min_value=0, value=42, step=1)
        mc_paths = monte_carlo_gbm(
            market_price, drift_pct / 100, vol_pct / 100,
            n_steps=n_steps, n_paths=n_paths, seed=int(seed),
        )

    ready = start_cash > 0 and chosen and (prices is not None or mc_paths is not None)
    if start_cash <= 0:
        st.error("No cash to reinvest — Phase 1 nets ₹0 with current inputs.")
    elif not chosen:
        st.info("Pick at least one strategy to compare.")

    # ---- deterministic modes: fixed % / CSV ----
    if ready and prices is not None:
        with st.expander("Assumed price path"):
            fig_path = go.Figure(
                go.Scatter(
                    x=list(range(len(prices))), y=prices, mode="lines",
                    line=dict(color=C_MUTED, width=2),
                    hovertemplate="step %{x}<br>₹%{y:,.2f}<extra></extra>",
                )
            )
            fig_path.update_layout(
                title="Price path (your assumption)", xaxis_title="Step",
                yaxis_title="₹", showlegend=False, **base_layout(),
            )
            st.plotly_chart(fig_path, use_container_width=True)

        rows = []
        runs = {}
        for name in chosen:
            try:
                runs[name] = run_sandbox(
                    start_cash, prices, strat_map[name], cost_model, tax_model,
                    liquidate_at_end=liquidate_end, tax_netting=tax_netting,
                )
            except Exception as exc:
                st.error(f"Strategy “{name}” failed: {exc}")
                continue
            r = runs[name]
            rows.append({
                "Strategy": name,
                "Gross profit ₹": r.gross_profit,
                "Costs ₹": r.total_costs,
                "Tax ₹": r.total_tax,
                "Net profit ₹": r.net_profit,
                "Peak cash deployed ₹": r.peak_cash_deployed,
                "Max drawdown ₹": r.max_drawdown,
                "Final value ₹": start_cash + r.net_profit,
            })

        if rows:
            df_cmp = pd.DataFrame(rows)
            st.dataframe(
                df_cmp.style.format(
                    {c: "{:,.0f}" for c in df_cmp.columns if c.endswith("₹")}
                ),
                use_container_width=True, hide_index=True,
            )

            ch1, ch2 = st.columns(2)
            fig_cash2 = go.Figure()
            fig_np = go.Figure()
            for name, r in runs.items():
                color = SLOT_COLORS[slot_of[name]]
                xs = list(range(len(r.cash_series)))
                fig_cash2.add_scatter(
                    x=xs, y=r.cash_series, mode="lines", name=name,
                    line=dict(color=color, width=2),
                    hovertemplate=name + "<br>step %{x}<br>cash ₹%{y:,.0f}<extra></extra>",
                )
                fig_np.add_scatter(
                    x=xs, y=[e - start_cash for e in r.equity_series],
                    mode="lines", name=name, line=dict(color=color, width=2),
                    hovertemplate=name + "<br>step %{x}<br>net ₹%{y:,.0f}<extra></extra>",
                )
            fig_cash2.update_layout(
                title="Cash on hand over time", xaxis_title="Step",
                yaxis_title="₹", **base_layout(),
            )
            fig_np.update_layout(
                title="Cumulative net profit (mark-to-market)", xaxis_title="Step",
                yaxis_title="₹", **base_layout(),
            )
            ch1.plotly_chart(fig_cash2, use_container_width=True)
            ch2.plotly_chart(fig_np, use_container_width=True)

            for name, r in runs.items():
                with st.expander(f"Trade log — {name} ({len(r.trades)} orders)"):
                    if r.trades:
                        df_tr = pd.DataFrame(
                            [
                                {
                                    "Step": t.step, "Side": t.kind, "Qty": t.qty,
                                    "Price ₹": t.price, "Brokerage ₹": t.cost,
                                    "Realized gain ₹": t.realized_gain,
                                    "Tax ₹": t.tax,
                                }
                                for t in r.trades
                            ]
                        )
                        st.dataframe(
                            df_tr.style.format(
                                {c: "{:,.2f}" for c in df_tr.columns if c.endswith("₹")}
                            ),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.write("No trades.")

    # ---- Monte Carlo mode ----
    if ready and mc_paths is not None:
        st.caption(
            f"{mc_paths.shape[0]} simulated paths × {mc_paths.shape[1] - 1} "
            "steps. The distribution below is over *simulated* paths drawn "
            "from your drift/volatility assumptions."
        )
        rows = []
        mc_runs = {}
        for name in chosen:
            try:
                mc_runs[name] = run_monte_carlo(
                    start_cash, mc_paths, strat_map[name], cost_model, tax_model,
                    liquidate_at_end=liquidate_end, tax_netting=tax_netting,
                )
            except Exception as exc:
                st.error(f"Strategy “{name}” failed: {exc}")
                continue
            mc = mc_runs[name]
            rows.append({
                "Strategy": name,
                "P5 ₹": mc.percentiles[5],
                "P25 ₹": mc.percentiles[25],
                "Median net ₹": mc.percentiles[50],
                "P75 ₹": mc.percentiles[75],
                "P95 ₹": mc.percentiles[95],
                "Mean ₹": float(mc.net_profits.mean()),
                "P(loss) %": 100 * mc.prob_loss,
            })

        if rows:
            df_mc = pd.DataFrame(rows)
            fmt = {c: "{:,.0f}" for c in df_mc.columns if c.endswith("₹")}
            fmt["P(loss) %"] = "{:.1f}"
            st.dataframe(
                df_mc.style.format(fmt), use_container_width=True, hide_index=True
            )

            fig_hist = go.Figure()
            for name, mc in mc_runs.items():
                fig_hist.add_histogram(
                    x=mc.net_profits, name=name, nbinsx=40, opacity=0.6,
                    marker_color=SLOT_COLORS[slot_of[name]],
                    hovertemplate=name + "<br>net ₹%{x:,.0f}<br>paths: %{y}<extra></extra>",
                )
            fig_hist.update_layout(
                title="Distribution of net profit across paths",
                xaxis_title="Net profit ₹", yaxis_title="Paths",
                barmode="overlay", **base_layout(),
            )
            if len(mc_runs) == 1:
                only = next(iter(mc_runs.values()))
                for p in (5, 50, 95):
                    fig_hist.add_vline(
                        x=only.percentiles[p], line_dash="dash", line_width=1,
                        line_color=C_MUTED,
                        annotation_text=f"P{p}", annotation_font_color=C_MUTED,
                    )
            st.plotly_chart(fig_hist, use_container_width=True)

            if len(mc_runs) == 1:
                name, mc = next(iter(mc_runs.items()))
                fig_fan = go.Figure()
                for i, sample in enumerate(mc.sample_results):
                    fig_fan.add_scatter(
                        x=list(range(len(sample.equity_series))),
                        y=[e - start_cash for e in sample.equity_series],
                        mode="lines", showlegend=False,
                        line=dict(color=SLOT_COLORS[slot_of[name]], width=1),
                        opacity=0.35, hoverinfo="skip",
                    )
                fig_fan.update_layout(
                    title=f"Sample paths — cumulative net profit ({name})",
                    xaxis_title="Step", yaxis_title="₹", **base_layout(),
                )
                st.plotly_chart(fig_fan, use_container_width=True)

st.divider()
st.caption(
    "⚠️ Price assumptions are user inputs. This tool does not predict prices "
    "and is not financial, investment, or tax advice."
)
