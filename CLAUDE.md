# share-strategy-modeler

Streamlit app modeling two strictly separated phases of a fixed-price share
allotment. GitHub: https://github.com/AadiPathak23/Stockbot (branch `main`).

## Domain (defaults live in `config.py` — all user-editable in the UI)
- Right to buy exactly **1980 shares @ ₹3700**, in unlimited chunks, until
  **2026-10-31**. Share #1981+ costs market price (₹4700 assumed).
- Indian STCG on listed equity: **20.8% effective** (20% + 4% cess) on
  (sale − cost basis) per sale. Short-term = held <12 months.
- Brokerage: 0.1% per side + ₹20/order flat, toggleable.
- **Free call option rule:** never exercise below ₹3700 — the engine skips
  those tranches; keep it that way.

## Architecture
- `engine/allotment.py` — Phase 1: exercise → sell tranches; tax, costs,
  cashflow timeline. Tranches run sequentially (peak cash = largest tranche).
- `engine/sandbox.py` — Phase 2 simulator. **No built-in edge** (profits come
  only from user-assumed price paths; the UI must keep saying so). Rules it
  enforces: buys capped by cash incl. costs, sells capped by holdings,
  weighted-avg cost basis incl. buy-side brokerage, STCG per sale with
  optional annual netting (`tax_netting`), optional end liquidation.
- `engine/price_paths.py` — path generators: `fixed_move`, `from_csv`
  (needs a `close` column), `monte_carlo_gbm` (seeded GBM).
- `strategies/` — pluggable: any module with `strategy(state) -> Action`
  is auto-discovered into the UI dropdown. Contract in `strategies/base.py`;
  `dip_buyer.py` is the copy-me template.
- `app.py` — UI. Phase 1 tab + Phase 2 tab (side-by-side strategy
  comparison, Monte Carlo histogram with percentiles). Chart palette:
  8 fixed categorical slots, blue `#2a78d6` inflows / red `#e34948` outflows.
- `tests/` — 37 pytest tests with hand-computed reference numbers; keep new
  engine math covered the same way.

## Commands
```powershell
.venv\Scripts\python -m pytest -q                     # tests
.venv\Scripts\python -m streamlit run app.py --server.port 8630
```
**Port 8501 is occupied on this machine — always use 8630.**

## Conventions
- Git commits: authored solely by the user; **no Claude Co-Authored-By
  trailer** (explicit user request). No `gh` CLI; push over HTTPS.
- Prominent "not financial advice / tool doesn't predict prices" disclaimers
  in the UI are intentional — never remove them.
