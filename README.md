# share-strategy-modeler

Model two distinct phases of a fixed-price share allotment:

1. **Allotment harvesting** — exercise up to 1,980 shares at ₹3,700 (until the
   October deadline) and sell into the market, with Indian STCG (20.8%
   effective) and brokerage modeled per tranche. The unexercised allotment is
   treated as a free call option: never exercised below the fixed price.
2. **Reinvestment / trading sandbox** — reinvest net proceeds into
   market-priced shares under pluggable strategies. **No built-in edge**:
   results depend entirely on user-assumed price paths.

> ⚠️ This tool does not predict prices and is not financial or tax advice.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\python -m streamlit run app.py   # UI
.venv\Scripts\python -m pytest                 # tests
```

## Layout

- `config.py` — configurable defaults (shares, prices, tax, costs, deadline)
- `engine/` — calculation logic (`allotment.py` = Phase 1, `sandbox.py` = Phase 2)
- `strategies/` — pluggable strategies; interface documented in `strategies/base.py`
- `app.py` — Streamlit UI
- `tests/` — pytest suite

## Write your own strategy

Drop a `.py` file into `strategies/` with:

```python
from strategies.base import Action, StrategyState

def strategy(state: StrategyState) -> Action:
    ...
```

It is auto-discovered and appears in the app's dropdown. Full contract in
`strategies/base.py`.
