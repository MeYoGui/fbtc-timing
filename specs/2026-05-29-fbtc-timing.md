# FBTC Market Timing Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions + GitHub Pages pipeline that fetches Bitcoin market signals daily, computes a backtested composite score, and renders a clean static dashboard at https://meyogui.github.io/fbtc-timing.

**Architecture:** Six proven cycle indicators (MVRV Z-Score, 200-Week MA, Monthly RSI, Pi Cycle, Puell Multiple, Fear & Greed) are fetched from free APIs, scored 0/50/100, and weighted by a backtesting pass that defines a good entry as an 18-month hold producing ≥ 50% return while in the bottom 40% of the cycle's price range. A GitHub Actions cron job runs the full pipeline daily and commits the generated `docs/index.html` which GitHub Pages serves.

**Tech Stack:** Python 3.11, pandas, numpy, requests, Jinja2, Chart.js (CDN), pytest, GitHub Actions, GitHub Pages

---

## File Map

```
fbtc-timing/
├── .github/workflows/
│   ├── daily.yml              # daily cron: fetch → compute → score → build → push
│   └── backtest.yml           # manual workflow_dispatch: re-derive weights.json
├── data/
│   ├── btc_history.csv        # merged price + on-chain + fear&greed (generated)
│   ├── signal_history.csv     # daily signal readings for all 6 signals (generated)
│   ├── current_signals.json   # latest signal readings (generated)
│   ├── current_score.json     # composite score + verdict for today (generated)
│   └── weights.json           # signal weights from backtest (committed manually)
├── scripts/
│   ├── fetch_data.py          # pulls CoinGecko, CoinMetrics, alternative.me → btc_history.csv
│   ├── compute_signals.py     # computes 6 signals from btc_history.csv → signal_history.csv + current_signals.json
│   ├── backtest.py            # labels good entries, computes precision/recall/F1, derives weights.json
│   ├── score.py               # applies weights to current_signals.json → current_score.json
│   └── build_dashboard.py     # renders Jinja2 template → docs/index.html
├── templates/
│   └── dashboard.html.j2      # Jinja2 template: score, signal table, Chart.js chart, methodology details
├── tests/
│   ├── test_compute_signals.py
│   ├── test_backtest.py
│   └── test_score.py
├── docs/
│   ├── .nojekyll              # prevents GitHub Pages from running Jekyll
│   └── index.html             # generated output served by GitHub Pages
└── requirements.txt
```

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pytest.ini`

- [ ] **Step 1: Create requirements.txt**

```
pandas>=2.0
numpy>=1.24
requests>=2.31
jinja2>=3.1
pytest>=7.4
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.env
venv/
.venv/
```

- [ ] **Step 3: Create pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 5: Create initial directory structure**

```bash
mkdir -p data scripts templates tests docs .github/workflows
touch docs/.nojekyll
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore pytest.ini docs/.nojekyll
git commit -m "chore: project setup"
```

---

## Task 2: Data Fetching (`scripts/fetch_data.py`)

**Files:**
- Create: `scripts/fetch_data.py`

No tests for this module — it calls live APIs. Validate by running it and checking the output CSV.

- [ ] **Step 1: Create `scripts/fetch_data.py`**

```python
import requests
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def fetch_btc_price_history() -> pd.DataFrame:
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": "max", "interval": "daily"}
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    prices = pd.DataFrame(data["prices"], columns=["ts_ms", "price"])
    mcaps = pd.DataFrame(data["market_caps"], columns=["ts_ms", "market_cap"])
    df = prices.merge(mcaps, on="ts_ms")
    df["date"] = pd.to_datetime(df["ts_ms"], unit="ms").dt.date
    return df[["date", "price", "market_cap"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def fetch_coinmetrics_data() -> pd.DataFrame:
    url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    params = {
        "assets": "btc",
        "metrics": "CapRealUSD,RevUSD",
        "frequency": "1d",
        "start_time": "2013-01-01",
        "page_size": 10000,
    }
    records = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        records.extend(payload["data"])
        next_token = payload.get("next_page_token")
        if not next_token:
            break
        params["next_page_token"] = next_token
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["time"]).dt.date
    df = df.rename(columns={"CapRealUSD": "realized_cap", "RevUSD": "miner_revenue"})
    df["realized_cap"] = pd.to_numeric(df["realized_cap"], errors="coerce")
    df["miner_revenue"] = pd.to_numeric(df["miner_revenue"], errors="coerce")
    return df[["date", "realized_cap", "miner_revenue"]].sort_values("date").reset_index(drop=True)


def fetch_fear_greed_history() -> pd.DataFrame:
    url = "https://api.alternative.me/fng/"
    resp = requests.get(url, params={"limit": 0, "format": "json"}, timeout=30)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["data"])
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.date
    df["fear_greed"] = pd.to_numeric(df["value"])
    return df[["date", "fear_greed"]].sort_values("date").reset_index(drop=True)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Fetching BTC price + market cap from CoinGecko...")
    price_df = fetch_btc_price_history()
    print(f"  {len(price_df)} rows")

    print("Fetching realized cap + miner revenue from CoinMetrics...")
    onchain_df = fetch_coinmetrics_data()
    print(f"  {len(onchain_df)} rows")

    print("Fetching Fear & Greed history from alternative.me...")
    fg_df = fetch_fear_greed_history()
    print(f"  {len(fg_df)} rows")

    merged = (
        price_df
        .merge(onchain_df, on="date", how="left")
        .merge(fg_df, on="date", how="left")
    )
    merged.to_csv(DATA_DIR / "btc_history.csv", index=False)
    print(f"Saved {len(merged)} rows to data/btc_history.csv")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it to validate**

```bash
python scripts/fetch_data.py
```

Expected output:
```
Fetching BTC price + market cap from CoinGecko...
  4000+ rows
Fetching realized cap + miner revenue from CoinMetrics...
  3000+ rows
Fetching Fear & Greed history from alternative.me...
  1500+ rows
Saved 4000+ rows to data/btc_history.csv
```

- [ ] **Step 3: Verify the CSV looks correct**

```bash
python -c "import pandas as pd; df = pd.read_csv('data/btc_history.csv'); print(df.tail()); print(df.dtypes)"
```

Expected: last rows show recent dates, non-null price/market_cap, some NaN for older dates where realized_cap/fear_greed weren't available.

- [ ] **Step 4: Commit**

```bash
git add scripts/fetch_data.py data/btc_history.csv
git commit -m "feat: add data fetching script"
```

---

## Task 3: Signal Computation (`scripts/compute_signals.py`)

**Files:**
- Create: `scripts/compute_signals.py`
- Create: `tests/test_compute_signals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_compute_signals.py
import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from compute_signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_puell_multiple,
    compute_pi_cycle_ratio,
    signal_score,
)


def make_df(n=1500, price=50000.0, realized_cap=None, miner_revenue=1e6):
    dates = pd.date_range("2019-01-01", periods=n).date
    prices = np.full(n, price)
    mcaps = prices * 19_000_000
    rcaps = np.full(n, realized_cap if realized_cap is not None else mcaps[0] * 0.8)
    revenues = np.full(n, miner_revenue)
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "market_cap": mcaps,
        "realized_cap": rcaps,
        "miner_revenue": revenues,
        "fear_greed": np.full(n, 50),
    })


def test_signal_score_buy_zone():
    assert signal_score(0.5, buy_threshold=1.0, avoid_threshold=3.0) == 100


def test_signal_score_avoid_zone():
    assert signal_score(4.0, buy_threshold=1.0, avoid_threshold=3.0) == 0


def test_signal_score_neutral_zone():
    assert signal_score(2.0, buy_threshold=1.0, avoid_threshold=3.0) == 50


def test_mvrv_zscore_constant_prices_returns_zero():
    df = make_df(n=500)
    zscore = compute_mvrv_zscore(df)
    # constant market_cap - realized_cap → std = 0 → zscore = 0
    assert zscore.dropna().abs().max() == pytest.approx(0.0, abs=1e-9)


def test_200w_ma_ratio_equals_one_when_price_is_constant():
    df = make_df(n=1500)
    ratio = compute_200w_ma_ratio(df)
    # After warmup, constant price → ratio == 1.0
    valid = ratio.dropna()
    assert valid.iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_puell_multiple_equals_one_when_revenue_is_constant():
    df = make_df(n=800, miner_revenue=1e6)
    puell = compute_puell_multiple(df)
    valid = puell.dropna()
    assert valid.iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_pi_cycle_ratio_equals_one_when_price_is_constant():
    df = make_df(n=800)
    ratio = compute_pi_cycle_ratio(df)
    valid = ratio.dropna()
    assert valid.iloc[-1] == pytest.approx(0.5, abs=1e-6)
    # 111DMA / (2 × 350DMA) = price / (2 × price) = 0.5 when price is constant
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_compute_signals.py -v
```

Expected: `ImportError: cannot import name 'compute_mvrv_zscore'`

- [ ] **Step 3: Create `scripts/compute_signals.py`**

```python
import json
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

SIGNAL_NAMES = ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]


def compute_mvrv_zscore(df: pd.DataFrame) -> pd.Series:
    diff = df["market_cap"] - df["realized_cap"]
    std = diff.std()
    if std == 0:
        return pd.Series(np.zeros(len(df)), index=df.index)
    return (diff - diff.mean()) / std


def compute_200w_ma_ratio(df: pd.DataFrame) -> pd.Series:
    ma = df["price"].rolling(window=1400, min_periods=200).mean()
    return df["price"] / ma


def compute_monthly_rsi(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    daily_idx = pd.to_datetime(df["date"])
    monthly = df.set_index(daily_idx)["price"].resample("ME").last()
    delta = monthly.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.reindex(daily_idx, method="ffill").values


def compute_pi_cycle_ratio(df: pd.DataFrame) -> pd.Series:
    ma_111 = df["price"].rolling(111).mean()
    ma_350_x2 = df["price"].rolling(350).mean() * 2
    return ma_111 / ma_350_x2


def compute_puell_multiple(df: pd.DataFrame) -> pd.Series:
    ma_365 = df["miner_revenue"].rolling(365).mean()
    return df["miner_revenue"] / ma_365


def signal_score(value: float, buy_threshold: float, avoid_threshold: float) -> int:
    """Map value to 100 (buy), 50 (neutral), or 0 (avoid). Higher value = worse."""
    if value <= buy_threshold:
        return 100
    if value >= avoid_threshold:
        return 0
    return 50


def score_series(series: pd.Series, buy_threshold: float, avoid_threshold: float) -> pd.Series:
    return series.apply(
        lambda v: signal_score(v, buy_threshold, avoid_threshold) if pd.notna(v) else 50
    )


def compute_all_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"date": df["date"]})

    out["mvrv_zscore_raw"] = compute_mvrv_zscore(df)
    out["mvrv_zscore"] = score_series(out["mvrv_zscore_raw"], 1.0, 3.0)

    out["ma_200w_ratio_raw"] = compute_200w_ma_ratio(df)
    out["ma_200w"] = score_series(out["ma_200w_ratio_raw"], 1.0, 1.2)

    rsi = compute_monthly_rsi(df)
    out["monthly_rsi_raw"] = rsi
    out["monthly_rsi"] = pd.Series(rsi).apply(
        lambda v: signal_score(v, 40.0, 70.0) if pd.notna(v) else 50
    )

    out["pi_cycle_ratio_raw"] = compute_pi_cycle_ratio(df)
    out["pi_cycle"] = score_series(out["pi_cycle_ratio_raw"], 0.9, 1.0)

    out["puell_raw"] = compute_puell_multiple(df)
    out["puell"] = score_series(out["puell_raw"], 0.5, 1.5)

    out["fear_greed_raw"] = df["fear_greed"]
    out["fear_greed"] = score_series(out["fear_greed_raw"], 25.0, 50.0)

    return out


def main():
    df = pd.read_csv(DATA_DIR / "btc_history.csv")
    df["date"] = pd.to_datetime(df["date"]).dt.date

    signals = compute_all_signals(df)
    signals.to_csv(DATA_DIR / "signal_history.csv", index=False)

    latest = signals.iloc[-1]
    current = {
        "date": str(latest["date"]),
        "signals": {
            "mvrv_zscore": {"raw": latest["mvrv_zscore_raw"], "score": int(latest["mvrv_zscore"])},
            "ma_200w":     {"raw": latest["ma_200w_ratio_raw"], "score": int(latest["ma_200w"])},
            "monthly_rsi": {"raw": latest["monthly_rsi_raw"], "score": int(latest["monthly_rsi"])},
            "pi_cycle":    {"raw": latest["pi_cycle_ratio_raw"], "score": int(latest["pi_cycle"])},
            "puell":       {"raw": latest["puell_raw"], "score": int(latest["puell"])},
            "fear_greed":  {"raw": latest["fear_greed_raw"], "score": int(latest["fear_greed"])},
        },
    }
    (DATA_DIR / "current_signals.json").write_text(json.dumps(current, indent=2, default=str))
    print(f"Signals computed for {current['date']}")
    for name, data in current["signals"].items():
        print(f"  {name}: raw={data['raw']:.3f}  score={data['score']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_compute_signals.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run the script against real data**

```bash
python scripts/compute_signals.py
```

Expected: prints signal readings for today, saves `data/signal_history.csv` and `data/current_signals.json`.

- [ ] **Step 6: Commit**

```bash
git add scripts/compute_signals.py tests/test_compute_signals.py data/signal_history.csv data/current_signals.json
git commit -m "feat: add signal computation"
```

---

## Task 4: Backtesting (`scripts/backtest.py`)

**Files:**
- Create: `scripts/backtest.py`
- Create: `tests/test_backtest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backtest.py
import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from backtest import label_good_entries, compute_signal_stats, derive_weights, SIGNAL_NAMES


def make_price_df(prices, start="2013-01-01"):
    dates = pd.date_range(start, periods=len(prices)).date
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "cycle_range_40pct": [p * 1.5 for p in prices],  # all entries qualify
    })


def make_signals_df(n, buy_days=None):
    df = pd.DataFrame({"date": pd.date_range("2013-01-01", periods=n).date})
    for name in SIGNAL_NAMES:
        df[name] = 50  # neutral by default
    if buy_days:
        for day in buy_days:
            for name in SIGNAL_NAMES:
                df.loc[day, name] = 100
    return df


def test_label_good_entries_returns_false_when_return_below_threshold():
    # flat price → 0% return → not a good entry
    prices = [100.0] * 2000
    df = make_price_df(prices)
    result = label_good_entries(df)
    assert result.sum() == 0


def test_label_good_entries_returns_true_when_return_exceeds_threshold():
    # price doubles after 548 days → 100% return > 50% threshold
    n = 1200
    prices = [100.0] * 548 + [200.0] * (n - 548)
    df = make_price_df(prices)
    result = label_good_entries(df)
    assert result.iloc[0] == True


def test_derive_weights_sum_to_one():
    stats = {name: {"f1": 0.5} for name in SIGNAL_NAMES}
    weights = derive_weights(stats)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


def test_derive_weights_higher_f1_gets_higher_weight():
    stats = {name: {"f1": 0.1} for name in SIGNAL_NAMES}
    stats["mvrv_zscore"]["f1"] = 0.9
    weights = derive_weights(stats)
    assert weights["mvrv_zscore"] > weights["ma_200w"]


def test_compute_signal_stats_perfect_signal():
    n = 2000
    signals_df = make_signals_df(n, buy_days=list(range(100, 200)))
    good_entries = pd.Series([False] * n)
    good_entries.iloc[100:200] = True
    stats = compute_signal_stats(signals_df, good_entries)
    assert stats["mvrv_zscore"]["precision"] == pytest.approx(1.0)
    assert stats["mvrv_zscore"]["recall"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_backtest.py -v
```

Expected: `ImportError: cannot import name 'label_good_entries'`

- [ ] **Step 3: Create `scripts/backtest.py`**

```python
import json
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

SIGNAL_NAMES = ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]

# Approximate halving dates + far-future cap for the current cycle
HALVING_DATES = [
    "2009-01-03",
    "2012-11-28",
    "2016-07-09",
    "2020-05-11",
    "2024-04-19",
    "2030-01-01",
]

HOLDING_DAYS = 548        # ~18 months
MIN_RETURN = 0.50         # 50%
CYCLE_BOTTOM_PCT = 0.40   # bottom 40% of cycle range


def get_cycle_ranges(df: pd.DataFrame) -> pd.DataFrame:
    halvings = pd.to_datetime(HALVING_DATES)
    df = df.copy()
    dates_ts = pd.to_datetime(df["date"])
    df["cycle"] = pd.cut(dates_ts, bins=halvings, labels=range(len(halvings) - 1), right=False)

    completed_cycles = list(range(len(halvings) - 2))  # all but the current one
    cycle_stats = (
        df[df["cycle"].isin(completed_cycles)]
        .groupby("cycle")["price"]
        .agg(cycle_low="min", cycle_high="max")
    )
    df = df.join(cycle_stats, on="cycle")

    # For the current (incomplete) cycle, use running max / running min
    current = len(halvings) - 2
    mask = df["cycle"] == current
    df.loc[mask, "cycle_high"] = df.loc[mask, "price"].expanding().max()
    df.loc[mask, "cycle_low"] = df.loc[mask, "price"].expanding().min()

    df["cycle_range_40pct"] = df["cycle_low"] + CYCLE_BOTTOM_PCT * (df["cycle_high"] - df["cycle_low"])
    return df


def label_good_entries(df: pd.DataFrame) -> pd.Series:
    prices = df["price"].values
    thresholds = df["cycle_range_40pct"].values
    n = len(prices)
    good = np.zeros(n, dtype=bool)
    for i in range(n - HOLDING_DAYS):
        if prices[i] <= 0:
            continue
        fwd_return = (prices[i + HOLDING_DAYS] - prices[i]) / prices[i]
        if fwd_return >= MIN_RETURN and prices[i] <= thresholds[i]:
            good[i] = True
    return pd.Series(good, index=df.index)


def compute_signal_stats(signals_df: pd.DataFrame, good_entries: pd.Series) -> dict:
    stats = {}
    for name in SIGNAL_NAMES:
        buy = signals_df[name] == 100
        tp = (buy & good_entries).sum()
        fp = (buy & ~good_entries).sum()
        fn = (~buy & good_entries).sum()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        stats[name] = {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
        }
    return stats


def derive_weights(stats: dict) -> dict:
    total = sum(stats[s]["f1"] for s in SIGNAL_NAMES)
    if total == 0:
        equal = round(1.0 / len(SIGNAL_NAMES), 4)
        return {s: equal for s in SIGNAL_NAMES}
    return {s: round(stats[s]["f1"] / total, 4) for s in SIGNAL_NAMES}


def main():
    price_df = pd.read_csv(DATA_DIR / "btc_history.csv")
    price_df["date"] = pd.to_datetime(price_df["date"]).dt.date

    signals_df = pd.read_csv(DATA_DIR / "signal_history.csv")
    signals_df["date"] = pd.to_datetime(signals_df["date"]).dt.date

    print("Labelling good entry days...")
    price_with_cycles = get_cycle_ranges(price_df)
    good_entries = label_good_entries(price_with_cycles)
    print(f"  {good_entries.sum()} good-entry days out of {len(good_entries)}")

    merged = price_df[["date"]].merge(signals_df[["date"] + SIGNAL_NAMES], on="date", how="left")

    print("Computing signal precision / recall...")
    stats = compute_signal_stats(merged, good_entries)
    weights = derive_weights(stats)

    output = {
        "generated_at": str(pd.Timestamp.now().date()),
        "good_entry_definition": {
            "min_18mo_return": MIN_RETURN,
            "cycle_bottom_pct": CYCLE_BOTTOM_PCT,
        },
        "signals": {
            name: {"weight": weights[name], **stats[name]}
            for name in SIGNAL_NAMES
        },
    }
    (DATA_DIR / "weights.json").write_text(json.dumps(output, indent=2))
    print("\nWeights saved to data/weights.json:")
    for name, d in output["signals"].items():
        print(f"  {name}: weight={d['weight']:.3f}  precision={d['precision']:.3f}  recall={d['recall']:.3f}  f1={d['f1']:.3f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_backtest.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run the backtest against real data**

```bash
python scripts/backtest.py
```

Expected: prints weights table, saves `data/weights.json`.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest.py tests/test_backtest.py data/weights.json
git commit -m "feat: add backtesting and weight derivation"
```

---

## Task 5: Scoring (`scripts/score.py`)

**Files:**
- Create: `scripts/score.py`
- Create: `tests/test_score.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_score.py
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict, SIGNAL_DISPLAY

EQUAL_WEIGHTS = {
    "signals": {name: {"weight": 1/6} for name in SIGNAL_DISPLAY}
}


def test_get_verdict_strong_buy():
    assert get_verdict(80) == "STRONG BUY"


def test_get_verdict_accumulate():
    assert get_verdict(60) == "ACCUMULATE"


def test_get_verdict_wait():
    assert get_verdict(40) == "WAIT"


def test_get_verdict_avoid():
    assert get_verdict(10) == "AVOID"


def test_get_verdict_boundary_75():
    assert get_verdict(75) == "STRONG BUY"


def test_get_verdict_boundary_50():
    assert get_verdict(50) == "ACCUMULATE"


def test_compute_score_all_buy():
    signals = {name: {"score": 100} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(100.0, abs=0.1)


def test_compute_score_all_avoid():
    signals = {name: {"score": 0} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(0.0, abs=0.1)


def test_compute_score_mixed():
    signals = {name: {"score": 100 if i % 2 == 0 else 0} for i, name in enumerate(SIGNAL_DISPLAY)}
    score = compute_score(signals, EQUAL_WEIGHTS)
    assert 40 < score < 60  # roughly 50
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_score.py -v
```

Expected: `ImportError: cannot import name 'compute_score'`

- [ ] **Step 3: Create `scripts/score.py`**

```python
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

SIGNAL_DISPLAY = {
    "mvrv_zscore": "MVRV Z-Score",
    "ma_200w":     "200-Week MA",
    "monthly_rsi": "Monthly RSI",
    "pi_cycle":    "Pi Cycle",
    "puell":       "Puell Multiple",
    "fear_greed":  "Fear & Greed",
}


def get_verdict(score: float) -> str:
    if score >= 75:
        return "STRONG BUY"
    if score >= 50:
        return "ACCUMULATE"
    if score >= 25:
        return "WAIT"
    return "AVOID"


def compute_score(signals: dict, weights: dict) -> float:
    total_weight = sum(weights["signals"][name]["weight"] for name in signals)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(
        signals[name]["score"] * weights["signals"][name]["weight"]
        for name in signals
    )
    return round(weighted_sum / total_weight, 1)


def main():
    current = json.loads((DATA_DIR / "current_signals.json").read_text())
    weights = json.loads((DATA_DIR / "weights.json").read_text())

    composite = compute_score(current["signals"], weights)
    verdict = get_verdict(composite)

    output = {
        "date": current["date"],
        "composite_score": composite,
        "verdict": verdict,
        "signals": {
            name: {
                "display_name": SIGNAL_DISPLAY[name],
                "raw": data["raw"],
                "score": data["score"],
                "status": "buy" if data["score"] == 100 else ("avoid" if data["score"] == 0 else "neutral"),
            }
            for name, data in current["signals"].items()
        },
        "weights": {name: weights["signals"][name]["weight"] for name in weights["signals"]},
    }

    (DATA_DIR / "current_score.json").write_text(json.dumps(output, indent=2, default=str))
    print(f"Score: {composite}/100 — {verdict}")
    for name, d in output["signals"].items():
        print(f"  {d['display_name']}: {d['status'].upper()}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_score.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Run the script**

```bash
python scripts/score.py
```

Expected: prints today's composite score and verdict.

- [ ] **Step 6: Commit**

```bash
git add scripts/score.py tests/test_score.py data/current_score.json
git commit -m "feat: add composite scoring"
```

---

## Task 6: Dashboard Template (`templates/dashboard.html.j2`)

**Files:**
- Create: `templates/dashboard.html.j2`

No tests — validated visually in Task 7.

- [ ] **Step 1: Create `templates/dashboard.html.j2`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FBTC Market Timing</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #0d0d0d; color: #d0d0d0; max-width: 860px; margin: 0 auto; padding: 2rem 1.5rem; }
    header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2rem; }
    header h1 { font-size: 1.25rem; font-weight: 600; color: #f0f0f0; }
    .meta { font-size: 0.85rem; color: #666; }
    .score-card { background: #161616; border-radius: 12px; padding: 2.5rem; text-align: center; margin-bottom: 2rem; }
    .score-number { font-size: 4.5rem; font-weight: 700; line-height: 1; color: {{ score_color }}; }
    .score-label { font-size: 0.9rem; color: #555; margin-top: 0.4rem; }
    .verdict { font-size: 1.6rem; font-weight: 600; margin-top: 0.75rem; color: {{ score_color }}; letter-spacing: 0.05em; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; }
    th { text-align: left; font-size: 0.75rem; font-weight: 500; color: #555; text-transform: uppercase; letter-spacing: 0.06em; padding: 0.6rem 0.75rem; border-bottom: 1px solid #222; }
    td { padding: 0.85rem 0.75rem; border-bottom: 1px solid #1a1a1a; font-size: 0.9rem; }
    .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 0.5rem; vertical-align: middle; }
    .dot-buy     { background: #00c853; }
    .dot-neutral { background: #ffd740; }
    .dot-avoid   { background: #ff5252; }
    .chart-wrap { margin-bottom: 2rem; }
    details { border: 1px solid #222; border-radius: 8px; padding: 1.25rem; }
    summary { cursor: pointer; font-size: 0.9rem; color: #888; user-select: none; }
    summary:hover { color: #bbb; }
    .meth-table { margin-top: 1.25rem; }
    .meth-table td, .meth-table th { font-size: 0.8rem; }
    .def-note { font-size: 0.8rem; color: #555; margin-top: 1rem; line-height: 1.5; }
  </style>
</head>
<body>

  <header>
    <h1>FBTC Market Timing</h1>
    <div class="meta">BTC ${{ "{:,.0f}".format(btc_price) }}&ensp;·&ensp;Updated {{ updated_date }}</div>
  </header>

  <div class="score-card">
    <div class="score-number">{{ composite_score }}</div>
    <div class="score-label">out of 100</div>
    <div class="verdict">{{ verdict }}</div>
  </div>

  <table>
    <thead>
      <tr><th>Signal</th><th>Reading</th><th>Status</th></tr>
    </thead>
    <tbody>
      {% for name, sig in signals.items() %}
      <tr>
        <td>{{ sig.display_name }}</td>
        <td>{{ sig.reading_formatted }}</td>
        <td><span class="dot dot-{{ sig.status }}"></span>{{ sig.status_label }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="chart-wrap">
    <canvas id="chart" height="120"></canvas>
  </div>

  <details>
    <summary>Methodology ›</summary>
    <table class="meth-table">
      <thead>
        <tr><th>Signal</th><th>Weight</th><th>Precision</th><th>Recall</th><th>F1</th></tr>
      </thead>
      <tbody>
        {% for name, m in methodology.items() %}
        <tr>
          <td>{{ m.display_name }}</td>
          <td>{{ "%.0f%%"|format(m.weight * 100) }}</td>
          <td>{{ "%.0f%%"|format(m.precision * 100) }}</td>
          <td>{{ "%.0f%%"|format(m.recall * 100) }}</td>
          <td>{{ "%.2f"|format(m.f1) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="def-note">
      Good entry: 18-month forward return ≥ 50% and entry price within bottom 40% of the Bitcoin cycle range.
      Weights are derived from the F1 score of each signal against historical good-entry days (2013–present).
    </p>
  </details>

  <script>
    const d = {{ chart_data_json }};
    new Chart(document.getElementById('chart'), {
      type: 'line',
      data: {
        labels: d.dates,
        datasets: [
          {
            label: 'BTC Price (USD)',
            data: d.prices,
            yAxisID: 'yPrice',
            borderColor: '#f7931a',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1,
          },
          {
            label: 'Composite Score',
            data: d.scores,
            yAxisID: 'yScore',
            borderColor: '#69f0ae',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1,
          }
        ]
      },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: '#888', font: { size: 11 } } },
        },
        scales: {
          x: {
            ticks: { color: '#555', maxTicksLimit: 8, font: { size: 10 } },
            grid: { color: '#1a1a1a' },
          },
          yPrice: {
            type: 'logarithmic',
            position: 'left',
            ticks: { color: '#f7931a', font: { size: 10 } },
            grid: { color: '#1a1a1a' },
          },
          yScore: {
            position: 'right',
            min: 0,
            max: 100,
            ticks: { color: '#69f0ae', font: { size: 10 } },
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
  </script>

</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/dashboard.html.j2
git commit -m "feat: add dashboard Jinja2 template"
```

---

## Task 7: Dashboard Builder (`scripts/build_dashboard.py`)

**Files:**
- Create: `scripts/build_dashboard.py`

- [ ] **Step 1: Create `scripts/build_dashboard.py`**

```python
import json
import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
DOCS_DIR = Path(__file__).parent.parent / "docs"

SIGNAL_DISPLAY = {
    "mvrv_zscore": "MVRV Z-Score",
    "ma_200w":     "200-Week MA",
    "monthly_rsi": "Monthly RSI",
    "pi_cycle":    "Pi Cycle",
    "puell":       "Puell Multiple",
    "fear_greed":  "Fear & Greed",
}

STATUS_LABELS = {"buy": "Buy Zone", "neutral": "Neutral", "avoid": "Avoid"}


def format_reading(name: str, raw) -> str:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "N/A"
    raw = float(raw)
    if name == "mvrv_zscore":
        return f"{raw:.2f}"
    if name == "ma_200w":
        pct = (raw - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}% vs 200WMA"
    if name == "monthly_rsi":
        return f"{raw:.0f}"
    if name == "pi_cycle":
        pct = (raw - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"111DMA {sign}{pct:.1f}% vs 2×350DMA"
    if name == "puell":
        return f"{raw:.2f}"
    if name == "fear_greed":
        return f"{raw:.0f} / 100"
    return f"{raw:.3f}"


def get_score_color(score: float) -> str:
    if score >= 75:
        return "#00c853"
    if score >= 50:
        return "#69f0ae"
    if score >= 25:
        return "#ffd740"
    return "#ff5252"


def compute_historical_scores(signals_df: pd.DataFrame, weights: dict) -> pd.Series:
    signal_names = list(SIGNAL_DISPLAY.keys())
    w = [weights["signals"][s]["weight"] for s in signal_names]
    total_w = sum(w)
    scores = signals_df[signal_names].values @ np.array(w) / total_w
    return pd.Series(scores, index=signals_df.index)


def build_chart_data(price_df: pd.DataFrame, signals_df: pd.DataFrame, weights: dict) -> dict:
    score_series = compute_historical_scores(signals_df, weights)
    signals_df = signals_df.copy()
    signals_df["composite_score"] = score_series

    merged = price_df[["date", "price"]].merge(signals_df[["date", "composite_score"]], on="date", how="inner")
    merged = merged.dropna()
    merged["date"] = pd.to_datetime(merged["date"])
    weekly = merged.set_index("date").resample("W").last().reset_index()
    weekly = weekly.dropna()

    return {
        "dates":  weekly["date"].dt.strftime("%Y-%m-%d").tolist(),
        "prices": weekly["price"].round(0).tolist(),
        "scores": weekly["composite_score"].round(1).tolist(),
    }


def main():
    current_score = json.loads((DATA_DIR / "current_score.json").read_text())
    weights = json.loads((DATA_DIR / "weights.json").read_text())
    price_df = pd.read_csv(DATA_DIR / "btc_history.csv")
    price_df["date"] = pd.to_datetime(price_df["date"]).dt.date
    signals_df = pd.read_csv(DATA_DIR / "signal_history.csv")
    signals_df["date"] = pd.to_datetime(signals_df["date"]).dt.date

    chart_data = build_chart_data(price_df, signals_df, weights)

    signals = {}
    for name, data in current_score["signals"].items():
        signals[name] = {
            "display_name": data["display_name"],
            "reading_formatted": format_reading(name, data["raw"]),
            "status": data["status"],
            "status_label": STATUS_LABELS[data["status"]],
        }

    methodology = {
        name: {
            "display_name": SIGNAL_DISPLAY[name],
            "weight":    weights["signals"][name]["weight"],
            "precision": weights["signals"][name]["precision"],
            "recall":    weights["signals"][name]["recall"],
            "f1":        weights["signals"][name]["f1"],
        }
        for name in SIGNAL_DISPLAY
    }

    btc_price = price_df.iloc[-1]["price"]

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        btc_price=btc_price,
        updated_date=current_score["date"],
        composite_score=current_score["composite_score"],
        verdict=current_score["verdict"],
        score_color=get_score_color(current_score["composite_score"]),
        signals=signals,
        chart_data_json=json.dumps(chart_data),
        methodology=methodology,
    )

    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard written to docs/index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the builder**

```bash
python scripts/build_dashboard.py
```

Expected: `Dashboard written to docs/index.html (XX,XXX bytes)`

- [ ] **Step 3: Open the dashboard in a browser to verify it renders correctly**

Open `docs/index.html` in a browser. Confirm:
- Score number and verdict are visible and color-coded
- Signal table shows 6 rows with readings and colored dots
- Chart renders with two lines (BTC price on log scale, composite score 0–100)
- Methodology section is collapsed and expands on click

- [ ] **Step 4: Commit**

```bash
git add scripts/build_dashboard.py docs/index.html
git commit -m "feat: add dashboard builder"
```

---

## Task 8: GitHub Actions Workflows

**Files:**
- Create: `.github/workflows/daily.yml`
- Create: `.github/workflows/backtest.yml`

- [ ] **Step 1: Create `.github/workflows/daily.yml`**

```yaml
name: Daily Dashboard Update

on:
  schedule:
    - cron: '0 12 * * *'   # 8 am ET (UTC-4 summer / UTC-5 winter)
  workflow_dispatch:         # allow manual trigger

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - run: pip install -r requirements.txt

      - run: python scripts/fetch_data.py

      - run: python scripts/compute_signals.py

      - run: python scripts/score.py

      - run: python scripts/build_dashboard.py

      - name: Commit and push updates
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ docs/index.html
          git diff --cached --quiet || git commit -m "chore: daily update $(date -u +%Y-%m-%d)"
          git push
```

- [ ] **Step 2: Create `.github/workflows/backtest.yml`**

```yaml
name: Re-derive Signal Weights

on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  backtest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - run: pip install -r requirements.txt

      - run: python scripts/fetch_data.py

      - run: python scripts/compute_signals.py

      - run: python scripts/backtest.py

      - name: Commit updated weights
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/weights.json
          git diff --cached --quiet || git commit -m "feat: update signal weights $(date -u +%Y-%m-%d)"
          git push
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily.yml .github/workflows/backtest.yml
git commit -m "feat: add GitHub Actions workflows"
```

---

## Task 9: GitHub Pages Setup & End-to-End Validation

**Files:**
- Verify: `docs/.nojekyll` (created in Task 1)

- [ ] **Step 1: Push everything to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Enable GitHub Pages**

Go to `https://github.com/MeYoGui/fbtc-timing/settings/pages`:
- Source: **Deploy from a branch**
- Branch: `main`, folder: `/docs`
- Click **Save**

- [ ] **Step 3: Trigger the daily workflow manually to verify the pipeline works end-to-end**

Go to `https://github.com/MeYoGui/fbtc-timing/actions/workflows/daily.yml` → **Run workflow** → **Run workflow**.

Wait for it to complete (≈ 2 minutes). Confirm all steps pass (green checkmarks).

- [ ] **Step 4: Verify the live dashboard**

Open `https://meyogui.github.io/fbtc-timing` (may take 1–2 minutes for Pages to deploy after the workflow commit).

Confirm:
- Score and verdict are visible
- All 6 signals show readings
- Chart renders with BTC price and composite score history
- Methodology section collapses/expands

- [ ] **Step 5: Run the full local test suite one final time**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Final commit**

```bash
git add .
git diff --cached --quiet || git commit -m "chore: final cleanup"
git push
```

---

## Self-Review Checklist

| Spec requirement | Task |
|---|---|
| Static web dashboard on GitHub Pages | Task 7 + Task 9 |
| Daily GitHub Actions cron | Task 8 |
| 6 signals: MVRV, 200WMA, RSI, Pi Cycle, Puell, Fear&Greed | Task 3 |
| Free APIs, no keys | Task 2 (CoinGecko, CoinMetrics, alternative.me) |
| Backtesting: 18-month ≥ 50% return + bottom 40% cycle | Task 4 |
| Weights from F1 score | Task 4 |
| Composite score 0–100 + 4 verdicts | Task 5 |
| Weights hidden in expandable Methodology section | Task 6 |
| Manual workflow_dispatch to re-run backtest | Task 8 |
| Historical chart (BTC price + composite score) | Task 6 + Task 7 |
