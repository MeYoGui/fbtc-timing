# Multi-Asset Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Bitcoin-only pipeline into a config-driven, multi-asset-ready architecture and introduce the score-chip UI, with Bitcoin's behaviour byte-identical and the dashboard ready for a second asset to be added as a single config file.

**Architecture:** A new `assets/` package holds per-asset configs (`bitcoin.py`) built from a shared signal-function library (`signals.py`) and typed dataclasses (`base.py`), registered in `registry.py`. The five pipeline scripts become loops over the registry, writing per-asset `{id}_*` data files. `build_dashboard.py` emits one JSON blob per asset; the template renders a shell and a `renderAsset()` JS function does all dashboard rendering client-side, driven by a score-chip switcher.

**Tech Stack:** Python 3.11 / pandas (pipeline), Jinja2 (template shell), vanilla JS + Chart.js (client-side render), pytest (tests).

**Reference:** The locked UI is `specs/2026-06-02-multi-asset-ui-reference.png`. The design is `specs/2026-06-02-multi-asset-framework-design.md`.

---

## File Map

| File | Responsibility |
|---|---|
| `assets/__init__.py` | Package marker |
| `assets/base.py` | `AssetConfig`, `SignalSpec` dataclasses |
| `assets/signals.py` | Shared signal compute functions (one job: raw-value math) |
| `assets/bitcoin.py` | Bitcoin config: data fetch, signal specs, halving good-entry, weight overrides |
| `assets/registry.py` | `ASSETS` ordered list |
| `scripts/fetch_data.py` | Loop registry → `data/{id}_history.csv` |
| `scripts/compute_signals.py` | Loop → `data/{id}_signal_history.csv` + `data/{id}_current_signals.json` |
| `scripts/score.py` | Loop → `data/{id}_score.json` |
| `scripts/backtest.py` | Loop → `data/{id}_weights.json` |
| `scripts/build_dashboard.py` | Assemble all assets → embed JSON in `docs/index.html` |
| `scripts/replay.py` | Updated data filenames |
| `templates/dashboard.html.j2` | Shell + chip switcher + `renderAsset()` JS |
| `tests/test_framework.py` | Parity + config + registry tests |

**Convention:** asset `id` = `"bitcoin"`. All per-asset data files are `data/bitcoin_*`. The dashboard DOM/JSON keys use the same `id`.

---

## Task 1: Golden-master parity test (pin current Bitcoin behaviour)

This test captures Bitcoin's current composite/verdict/signal-scores so every later refactor step is proven non-breaking. It reads the committed `current_signals.json` + `weights.json` through `score.compute_score`, which is deterministic and independent of live data.

**Files:**
- Create: `tests/test_framework.py`

- [ ] **Step 1: Write the parity test**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict

DATA = Path(__file__).parent.parent / "data"

# Golden values snapshotted from data/current_score.json on 2026-05-31.
# These pin Bitcoin's scoring behaviour across the multi-asset refactor.
GOLDEN_COMPOSITE = 54.5
GOLDEN_VERDICT = "CLOSE"
GOLDEN_SIGNAL_SCORES = {
    "mvrv_zscore": 50,
    "ma_200w": 50,
    "monthly_rsi": 50,
    "pi_cycle": 100,
    "puell": 50,
    "fear_greed": 50,
}


def _load(name_candidates):
    """Read the first data file that exists from a list of candidate names."""
    for name in name_candidates:
        p = DATA / name
        if p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError(f"none of {name_candidates} found in {DATA}")


def test_bitcoin_scoring_parity():
    # current_signals.json is renamed to bitcoin_current_signals.json in Task 6;
    # accept either so this test passes before and after the rename.
    current = _load(["bitcoin_current_signals.json", "current_signals.json"])
    weights = _load(["bitcoin_weights.json", "weights.json"])

    composite = compute_score(current["signals"], weights)
    assert composite == GOLDEN_COMPOSITE
    assert get_verdict(composite) == GOLDEN_VERDICT
    for key, expected in GOLDEN_SIGNAL_SCORES.items():
        assert current["signals"][key]["score"] == expected, key
```

- [ ] **Step 2: Run it to confirm it passes against current data**

Run: `python -m pytest tests/test_framework.py -v`
Expected: PASS (reads the current `current_signals.json` + `weights.json`).

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: 40 passed (39 existing + 1 new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_framework.py
git commit -m "test: pin Bitcoin scoring parity before multi-asset refactor"
```

---

## Task 2: `assets/base.py` — dataclasses

**Files:**
- Create: `assets/__init__.py`
- Create: `assets/base.py`
- Modify: `tests/test_framework.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_framework.py`:

```python
# ── assets/base.py ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.base import AssetConfig, SignalSpec


def _dummy_spec():
    return SignalSpec(
        key="x", display_name="X", compute=lambda df: df["x"],
        invest_thresh=1.0, avoid_thresh=2.0,
        range_lo=0.0, range_hi=3.0, fmt="{:.1f}",
    )


def test_signalspec_fields():
    s = _dummy_spec()
    assert s.key == "x"
    assert s.invest_thresh < s.avoid_thresh
    assert callable(s.compute)


def test_assetconfig_requires_core_fields():
    cfg = AssetConfig(
        id="dummy", display_name="Dummy", short_label="D", accent_color="#fff",
        price_unit="$", fetch=lambda: None, signals=[_dummy_spec()],
        good_entry=lambda df: None,
    )
    assert cfg.id == "dummy"
    assert cfg.weight_overrides is None
    assert len(cfg.signals) == 1
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_framework.py -k "spec or assetconfig" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'assets'`.

- [ ] **Step 3: Create the package and dataclasses**

Create `assets/__init__.py` (empty file).

Create `assets/base.py`:

```python
"""Typed config interface every asset must satisfy."""
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd


@dataclass
class SignalSpec:
    """Binds a shared signal compute-function to one asset's thresholds + display meta.

    Scoring direction is encoded by the ordering of invest_thresh vs avoid_thresh
    (all current signals are "lower raw value = more invest").
    """
    key: str                                   # "mvrv_zscore" — column + JSON key
    display_name: str                          # "MVRV Z-Score"
    compute: Callable[[pd.DataFrame], pd.Series]  # raw-value series from assets.signals
    invest_thresh: float
    avoid_thresh: float
    range_lo: float
    range_hi: float
    fmt: str                                   # "{:.1f}" — display format for bar labels


@dataclass
class AssetConfig:
    id: str                # "bitcoin" — used in filenames, JSON keys, DOM ids
    display_name: str      # "Bitcoin"
    short_label: str       # "₿ Bitcoin" (chip label)
    accent_color: str      # "#f7931a"
    price_unit: str        # "$" — header price prefix
    fetch: Callable[[], pd.DataFrame]               # returns history DataFrame (has "date")
    signals: list                                   # list[SignalSpec], ordered for display
    good_entry: Callable[[pd.DataFrame], pd.Series]  # backtest target (bool Series)
    weight_overrides: Optional[dict] = None          # e.g. {"mvrv_zscore": 2.0} precision multiplier
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `python -m pytest tests/test_framework.py -k "spec or assetconfig" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/__init__.py assets/base.py tests/test_framework.py
git commit -m "feat: add assets package with AssetConfig and SignalSpec dataclasses"
```

---

## Task 3: `assets/signals.py` — shared signal library

Move the six signal compute-functions out of `compute_signals.py` into a shared library, and re-export them from `compute_signals.py` so existing imports/tests keep working.

**Files:**
- Create: `assets/signals.py`
- Modify: `scripts/compute_signals.py`

- [ ] **Step 1: Create the shared library**

Create `assets/signals.py` with the five computed signals plus the pass-through, copied **verbatim** from the current `scripts/compute_signals.py` bodies:

```python
"""Shared signal compute-functions. Each returns a raw-value pandas Series
aligned to the input DataFrame's index. Asset-agnostic — thresholds live in
each asset's SignalSpec, not here."""
import numpy as np
import pandas as pd


def compute_mvrv_zscore(df: pd.DataFrame) -> pd.Series:
    """Z-score of the MVRV ratio (market cap / realized cap) over its full history."""
    mvrv = df["mvrv"]
    std = mvrv.std()
    if std == 0:
        return pd.Series(np.zeros(len(df)), index=df.index)
    return (mvrv - mvrv.mean()) / std


def compute_200w_ma_ratio(df: pd.DataFrame) -> pd.Series:
    ma = df["price"].rolling(window=1400, min_periods=200).mean()
    return df["price"] / ma


def compute_monthly_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    daily_idx = pd.to_datetime(df["date"])
    monthly = df.set_index(daily_idx)["price"].resample("ME").last()
    delta = monthly.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return pd.Series(rsi.reindex(daily_idx, method="ffill").values, index=df.index)


def compute_pi_cycle_ratio(df: pd.DataFrame) -> pd.Series:
    ma_111 = df["price"].rolling(111).mean()
    ma_350_x2 = df["price"].rolling(350).mean() * 2
    return ma_111 / ma_350_x2


def compute_puell_multiple(df: pd.DataFrame) -> pd.Series:
    ma_365 = df["miner_revenue"].rolling(365).mean()
    return df["miner_revenue"] / ma_365


def compute_fear_greed(df: pd.DataFrame) -> pd.Series:
    """Pass-through: fear & greed is already a 0-100 reading in the history."""
    return df["fear_greed"]
```

Note: `compute_monthly_rsi` now returns a `pd.Series` (was an `np.ndarray`). This is compatible with `score_series` and existing usage; the test only checks values.

- [ ] **Step 2: Re-export from compute_signals.py**

In `scripts/compute_signals.py`, **delete** the five local `compute_*` function definitions (`compute_mvrv_zscore`, `compute_200w_ma_ratio`, `compute_monthly_rsi`, `compute_pi_cycle_ratio`, `compute_puell_multiple`) and replace them with an import at the top of the file (after the existing imports):

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_monthly_rsi,
    compute_pi_cycle_ratio,
    compute_puell_multiple,
    compute_fear_greed,
)
```

Keep `signal_score`, `score_series`, `compute_all_signals`, `_sanitize_float`, `SIGNAL_NAMES`, and `main` as they are. In `compute_all_signals`, the line `rsi = compute_monthly_rsi(df)` now yields a Series; change the two lines that consumed the ndarray:

```python
    out["monthly_rsi_raw"] = compute_monthly_rsi(df)
    out["monthly_rsi"] = score_series(out["monthly_rsi_raw"], 40.0, 70.0)
```

(replacing the previous `rsi = compute_monthly_rsi(df)` / `pd.Series(rsi, index=df.index).apply(...)` block).

- [ ] **Step 3: Run the existing signal tests + parity**

Run: `python -m pytest tests/test_compute_signals.py tests/test_framework.py -v`
Expected: PASS (test imports `compute_*` and `signal_score` from `compute_signals`, which still resolve via re-export).

- [ ] **Step 4: Run full suite**

Run: `python -m pytest -q`
Expected: 42 passed.

- [ ] **Step 5: Commit**

```bash
git add assets/signals.py scripts/compute_signals.py
git commit -m "refactor: extract shared signal library to assets/signals.py"
```

---

## Task 4: `assets/bitcoin.py` + `assets/registry.py` — Bitcoin config

Move all Bitcoin-specific knowledge into a config: the three data fetchers (from `fetch_data.py`), the six `SignalSpec`s (thresholds from `score.py`'s `SIGNAL_META` + `compute_signals.py`), the halving good-entry (from `backtest.py`), and the MVRV weight multiplier.

**Files:**
- Create: `assets/bitcoin.py`
- Create: `assets/registry.py`
- Modify: `tests/test_framework.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_framework.py`:

```python
# ── assets/bitcoin.py + registry ──────────────────────────────────────────────
from assets.registry import ASSETS
from assets import bitcoin


def test_registry_contains_bitcoin():
    assert any(a.id == "bitcoin" for a in ASSETS)


def test_bitcoin_has_six_signals():
    keys = [s.key for s in bitcoin.CONFIG.signals]
    assert keys == ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]


def test_bitcoin_thresholds_match_legacy():
    by_key = {s.key: s for s in bitcoin.CONFIG.signals}
    assert by_key["mvrv_zscore"].invest_thresh == -0.5
    assert by_key["mvrv_zscore"].avoid_thresh == 1.5
    assert by_key["fear_greed"].invest_thresh == 25.0
    assert by_key["fear_greed"].avoid_thresh == 50.0
    assert by_key["pi_cycle"].invest_thresh == 0.9
    assert by_key["pi_cycle"].avoid_thresh == 1.0


def test_bitcoin_weight_override_mvrv():
    assert bitcoin.CONFIG.weight_overrides == {"mvrv_zscore": 2.0}
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_framework.py -k "registry or bitcoin" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'assets.bitcoin'`.

- [ ] **Step 3: Create `assets/bitcoin.py`**

Create `assets/bitcoin.py`. The fetchers are copied **verbatim** from the current `scripts/fetch_data.py` (`fetch_coinmetrics_data`, `fetch_miner_revenue_history`, `fetch_fear_greed_history`) and the merge from its `main`. The halving logic (`HALVING_DATES`, `get_cycle_ranges`, constants, `label_good_entries`) is copied **verbatim** from the current `scripts/backtest.py`.

```python
"""Bitcoin asset config."""
import requests
import pandas as pd

from assets.base import AssetConfig, SignalSpec
from assets.signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_monthly_rsi,
    compute_pi_cycle_ratio,
    compute_puell_multiple,
    compute_fear_greed,
)

# ── data fetch (moved verbatim from scripts/fetch_data.py) ────────────────────

def _fetch_coinmetrics() -> pd.DataFrame:
    url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    params = {
        "assets": "btc",
        "metrics": "PriceUSD,CapMrktCurUSD,CapMVRVCur",
        "frequency": "1d",
        "start_time": "2010-01-01",
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
    df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df["price"] = pd.to_numeric(df["PriceUSD"], errors="coerce")
    df["market_cap"] = pd.to_numeric(df["CapMrktCurUSD"], errors="coerce")
    df["mvrv"] = pd.to_numeric(df["CapMVRVCur"], errors="coerce")
    return df[["date", "price", "market_cap", "mvrv"]].sort_values("date").reset_index(drop=True)


def _fetch_miner_revenue() -> pd.DataFrame:
    resp = requests.get(
        "https://api.blockchain.info/charts/miners-revenue",
        params={"timespan": "all", "format": "json", "sampled": "false"},
        timeout=60,
    )
    resp.raise_for_status()
    rows = resp.json()["values"]
    df = pd.DataFrame(rows).rename(columns={"x": "ts", "y": "miner_revenue"})
    df["date"] = pd.to_datetime(df["ts"], unit="s").astype("datetime64[ns]").dt.normalize()
    df["miner_revenue"] = pd.to_numeric(df["miner_revenue"], errors="coerce")
    return df[["date", "miner_revenue"]].sort_values("date").reset_index(drop=True)


def _fetch_fear_greed() -> pd.DataFrame:
    resp = requests.get(
        "https://api.alternative.me/fng/",
        params={"limit": 0, "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["data"])
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").astype("datetime64[ns]").dt.normalize()
    df["fear_greed"] = pd.to_numeric(df["value"])
    return df[["date", "fear_greed"]].sort_values("date").reset_index(drop=True)


def fetch() -> pd.DataFrame:
    """Full Bitcoin history: price, market cap, MVRV, miner revenue, fear & greed."""
    cm = _fetch_coinmetrics()
    miner = _fetch_miner_revenue()
    fg = _fetch_fear_greed()
    return cm.merge(miner, on="date", how="left").merge(fg, on="date", how="left")


# ── good-entry definition (moved verbatim from scripts/backtest.py) ───────────

HALVING_DATES = [
    "2009-01-03", "2012-11-28", "2016-07-09",
    "2020-05-11", "2024-04-19", "2030-01-01",
]
HOLDING_DAYS = 548
MIN_RETURN = 0.50
CYCLE_BOTTOM_PCT = 0.40


def _get_cycle_ranges(df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd
    halvings = pd.to_datetime(HALVING_DATES)
    df = df.copy()
    dates_ts = pd.to_datetime(df["date"])
    df["cycle"] = pd.cut(dates_ts, bins=halvings, labels=range(len(halvings) - 1), right=False)
    completed_cycles = list(range(len(halvings) - 2))
    cycle_stats = (
        df[df["cycle"].isin(completed_cycles)]
        .groupby("cycle")["price"]
        .agg(cycle_low="min", cycle_high="max")
    )
    df = df.join(cycle_stats, on="cycle")
    current = len(halvings) - 2
    mask = df["cycle"] == current
    df.loc[mask, "cycle_high"] = df.loc[mask, "price"].expanding().max()
    df.loc[mask, "cycle_low"] = df.loc[mask, "price"].expanding().min()
    df["cycle_range_40pct"] = df["cycle_low"] + CYCLE_BOTTOM_PCT * (df["cycle_high"] - df["cycle_low"])
    return df


def good_entry(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: halving-cycle-bottom + strong 18-month forward return."""
    import numpy as np
    enriched = _get_cycle_ranges(df)
    prices = enriched["price"].values
    thresholds = enriched["cycle_range_40pct"].values
    n = len(prices)
    good = np.zeros(n, dtype=bool)
    for i in range(n - HOLDING_DAYS):
        if prices[i] <= 0:
            continue
        fwd_return = (prices[i + HOLDING_DAYS] - prices[i]) / prices[i]
        if fwd_return >= MIN_RETURN and prices[i] <= thresholds[i]:
            good[i] = True
    return pd.Series(good, index=df.index)


# ── config ────────────────────────────────────────────────────────────────────

CONFIG = AssetConfig(
    id="bitcoin",
    display_name="Bitcoin",
    short_label="₿ Bitcoin",
    accent_color="#f7931a",
    price_unit="$",
    fetch=fetch,
    good_entry=good_entry,
    weight_overrides={"mvrv_zscore": 2.0},
    signals=[
        SignalSpec("mvrv_zscore", "MVRV Z-Score", compute_mvrv_zscore,
                   invest_thresh=-0.5, avoid_thresh=1.5, range_lo=-3.0, range_hi=4.0, fmt="{:.1f}"),
        SignalSpec("ma_200w", "200-Week MA", compute_200w_ma_ratio,
                   invest_thresh=1.0, avoid_thresh=1.2, range_lo=0.5, range_hi=3.0, fmt="{:.1f}×"),
        SignalSpec("monthly_rsi", "Monthly RSI", compute_monthly_rsi,
                   invest_thresh=40.0, avoid_thresh=70.0, range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
        SignalSpec("pi_cycle", "Pi Cycle", compute_pi_cycle_ratio,
                   invest_thresh=0.9, avoid_thresh=1.0, range_lo=0.0, range_hi=1.5, fmt="{:.1f}"),
        SignalSpec("puell", "Puell Multiple", compute_puell_multiple,
                   invest_thresh=0.5, avoid_thresh=1.5, range_lo=0.0, range_hi=4.0, fmt="{:.1f}"),
        SignalSpec("fear_greed", "Fear & Greed", compute_fear_greed,
                   invest_thresh=25.0, avoid_thresh=50.0, range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
    ],
)
```

- [ ] **Step 4: Create `assets/registry.py`**

```python
"""Ordered list of configured assets. Add new assets here."""
from assets import bitcoin

ASSETS = [bitcoin.CONFIG]
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_framework.py -v`
Expected: PASS (all framework tests).

- [ ] **Step 6: Run full suite**

Run: `python -m pytest -q`
Expected: 46 passed.

- [ ] **Step 7: Commit**

```bash
git add assets/bitcoin.py assets/registry.py tests/test_framework.py
git commit -m "feat: add Bitcoin asset config (fetch, signals, good-entry, weights)"
```

---

## Task 5: Generalize `fetch_data.py` + rename history file

**Files:**
- Modify: `scripts/fetch_data.py`
- Modify: `scripts/replay.py`
- Rename: `data/btc_history.csv` → `data/bitcoin_history.csv`

- [ ] **Step 1: Rename the data file (preserve history)**

```bash
git mv data/btc_history.csv data/bitcoin_history.csv
```

- [ ] **Step 2: Rewrite `scripts/fetch_data.py`**

Replace the entire file with the generic loop (the per-asset fetch logic now lives in each config):

```python
"""Fetch each configured asset's history into data/{id}_history.csv."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"


def main():
    DATA_DIR.mkdir(exist_ok=True)
    for cfg in ASSETS:
        print(f"Fetching {cfg.display_name} history...")
        try:
            df = cfg.fetch()
        except Exception as e:  # per-asset isolation: one feed failing won't block others
            print(f"  ERROR fetching {cfg.id}: {e}", file=sys.stderr)
            continue
        out = DATA_DIR / f"{cfg.id}_history.csv"
        df.to_csv(out, index=False)
        print(f"  saved {len(df)} rows to {out.name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update `replay.py` filenames**

In `scripts/replay.py`, replace both `data/btc_history.csv` references and the `BACKED_UP` list to use bitcoin-namespaced files:

```python
BACKED_UP = [
    DATA_DIR / "bitcoin_history.csv",
    DATA_DIR / "bitcoin_signal_history.csv",
    DATA_DIR / "bitcoin_current_signals.json",
    DATA_DIR / "bitcoin_score.json",
]
```

And in `main()` change the three `btc_history.csv` usages to `bitcoin_history.csv` (the `pd.read_csv`, the not-found check, and the `filtered.to_csv`).

- [ ] **Step 4: Verify fetch runs (network) OR skip if offline**

Run: `python scripts/fetch_data.py`
Expected: `saved N rows to bitcoin_history.csv`. (If offline, confirm the file still exists from the rename and move on.)

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: 46 passed (no test reads `btc_history.csv` directly).

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_data.py scripts/replay.py data/bitcoin_history.csv
git commit -m "refactor: generic fetch_data loop over registry; rename to bitcoin_history.csv"
```

---

## Task 6: Generalize `compute_signals.py` + rename signal files

**Files:**
- Modify: `scripts/compute_signals.py`
- Rename: `data/signal_history.csv` → `data/bitcoin_signal_history.csv`, `data/current_signals.json` → `data/bitcoin_current_signals.json`

- [ ] **Step 1: Rename data files**

```bash
git mv data/signal_history.csv data/bitcoin_signal_history.csv
git mv data/current_signals.json data/bitcoin_current_signals.json
```

- [ ] **Step 2: Rewrite `compute_signals.py` to be config-driven**

Keep the top-of-file imports (including the `from assets.signals import ...` re-export added in Task 3, and `signal_score`, `score_series`, `_sanitize_float`). Replace `compute_all_signals` and `main` with generic versions driven by each asset's `SignalSpec`s. Keep `signal_score`, `score_series`, `_sanitize_float`, `SIGNAL_NAMES` for back-compat with `test_compute_signals`.

Full new tail of the file (everything from `compute_all_signals` down):

```python
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"


def compute_all_signals(df, signals) -> pd.DataFrame:
    """Build a {key}_raw + {key} score column per SignalSpec."""
    out = pd.DataFrame({"date": df["date"]})
    for spec in signals:
        out[f"{spec.key}_raw"] = spec.compute(df)
        out[spec.key] = score_series(out[f"{spec.key}_raw"], spec.invest_thresh, spec.avoid_thresh)
    return out


def _process_asset(cfg) -> None:
    hist_path = DATA_DIR / f"{cfg.id}_history.csv"
    if not hist_path.exists():
        print(f"  skip {cfg.id}: {hist_path.name} missing", file=sys.stderr)
        return
    df = pd.read_csv(hist_path)
    df["date"] = pd.to_datetime(df["date"])

    signals = compute_all_signals(df, cfg.signals)
    signals.to_csv(DATA_DIR / f"{cfg.id}_signal_history.csv", index=False)

    def _last_valid(raw_col, score_col):
        valid = signals[raw_col].notna()
        if not valid.any():
            return float("nan"), 50
        row = signals[valid].iloc[-1]
        return row[raw_col], int(row[score_col])

    latest = signals.iloc[-1]
    current = {"date": str(latest["date"].date()), "signals": {}}
    for spec in cfg.signals:
        raw, score = _last_valid(f"{spec.key}_raw", spec.key)
        current["signals"][spec.key] = {"raw": _sanitize_float(raw), "score": score}

    (DATA_DIR / f"{cfg.id}_current_signals.json").write_text(json.dumps(current, indent=2))
    print(f"  {cfg.id}: signals for {current['date']}")


def main():
    for cfg in ASSETS:
        print(f"Computing signals for {cfg.display_name}...")
        _process_asset(cfg)


if __name__ == "__main__":
    main()
```

Remove the now-unused module-level `SIGNAL_NAMES`? **No** — keep the `SIGNAL_NAMES` constant near the top (it is imported by nothing critical but harmless; leave it to avoid churn). Ensure `import json` and `import math` (for `_sanitize_float`) remain at the top.

- [ ] **Step 3: Update the parity test to read the renamed file**

The parity test in Task 1 already accepts `bitcoin_current_signals.json`. Run it:

Run: `python -m pytest tests/test_framework.py::test_bitcoin_scoring_parity -v`
Expected: PASS (now reads `bitcoin_current_signals.json`).

- [ ] **Step 4: Regenerate signals from the renamed history and verify parity holds**

Run: `python scripts/compute_signals.py`
Expected: `bitcoin: signals for <date>`. Confirm `data/bitcoin_signal_history.csv` and `data/bitcoin_current_signals.json` are rewritten.

Run: `python -m pytest -q`
Expected: 46 passed (parity test confirms identical scores).

- [ ] **Step 5: Commit**

```bash
git add scripts/compute_signals.py data/bitcoin_signal_history.csv data/bitcoin_current_signals.json
git commit -m "refactor: config-driven compute_signals loop; rename to bitcoin_* files"
```

---

## Task 7: Generalize `score.py` + rename score file

**Files:**
- Modify: `scripts/score.py`
- Rename: `data/current_score.json` → `data/bitcoin_score.json`, `data/weights.json` → `data/bitcoin_weights.json`

- [ ] **Step 1: Rename data files**

```bash
git mv data/current_score.json data/bitcoin_score.json
git mv data/weights.json data/bitcoin_weights.json
```

- [ ] **Step 2: Rewrite `score.py` to be config-driven**

Keep `get_verdict`, `compute_score`, `_sanitize_float`, and a module-level `SIGNAL_DISPLAY` (for `test_score` back-compat). Replace the `SIGNAL_META` constant and `main()` so signal metadata is built per-asset from `SignalSpec`s.

Replace from `SIGNAL_DISPLAY` through end-of-file with:

```python
SIGNAL_DISPLAY = {
    "mvrv_zscore": "MVRV Z-Score",
    "ma_200w":     "200-Week MA",
    "monthly_rsi": "Monthly RSI",
    "pi_cycle":    "Pi Cycle",
    "puell":       "Puell Multiple",
    "fear_greed":  "Fear & Greed",
}  # retained for test back-compat; per-asset names come from SignalSpec.display_name


def get_verdict(score: float) -> str:
    if score >= 80:
        return "STRONG BUY"
    if score >= 72:
        return "INVEST"
    if score >= 50:
        return "CLOSE"
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


def _sanitize_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else f
    except (TypeError, ValueError):
        return None


def _signal_meta(cfg) -> dict:
    return {
        s.key: {
            "range_lo": s.range_lo, "range_hi": s.range_hi,
            "invest_thresh": s.invest_thresh, "avoid_thresh": s.avoid_thresh,
            "fmt": s.fmt,
        }
        for s in cfg.signals
    }


def _score_asset(cfg) -> None:
    current_path = DATA_DIR / f"{cfg.id}_current_signals.json"
    weights_path = DATA_DIR / f"{cfg.id}_weights.json"
    if not current_path.exists():
        print(f"  skip {cfg.id}: {current_path.name} missing", file=sys.stderr)
        return
    if not weights_path.exists():
        raise FileNotFoundError(
            f"{weights_path.name} not found — run 'python scripts/backtest.py' first."
        )
    current = json.loads(current_path.read_text())
    weights = json.loads(weights_path.read_text())
    names = {s.key: s.display_name for s in cfg.signals}

    composite = compute_score(current["signals"], weights)
    verdict = get_verdict(composite)
    output = {
        "date": current["date"],
        "composite_score": composite,
        "verdict": verdict,
        "signals": {
            name: {
                "display_name": names[name],
                "raw": _sanitize_float(data["raw"]),
                "score": data["score"],
                "status": "buy" if data["score"] == 100 else ("avoid" if data["score"] == 0 else "neutral"),
            }
            for name, data in current["signals"].items()
        },
        "weights": {name: weights["signals"][name]["weight"] for name in weights["signals"]},
        "signal_meta": _signal_meta(cfg),
    }
    (DATA_DIR / f"{cfg.id}_score.json").write_text(json.dumps(output, indent=2))
    print(f"  {cfg.id}: {composite}/100 — {verdict}")


def main():
    for cfg in ASSETS:
        print(f"Scoring {cfg.display_name}...")
        _score_asset(cfg)


if __name__ == "__main__":
    main()
```

Add the needed imports at the top of `score.py`: keep `import json`, `import math`, `from pathlib import Path`, add:

```python
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS
```

and keep `DATA_DIR = Path(__file__).parent.parent / "data"`.

- [ ] **Step 3: Regenerate score and verify parity**

Run: `python scripts/score.py`
Expected: `bitcoin: 54.5/100 — CLOSE`.

Run: `python -m pytest -q`
Expected: 46 passed (parity test now reads `bitcoin_current_signals.json` + `bitcoin_weights.json` and still sees 54.5/CLOSE).

- [ ] **Step 4: Commit**

```bash
git add scripts/score.py data/bitcoin_score.json data/bitcoin_weights.json
git commit -m "refactor: config-driven score loop; rename to bitcoin_score/weights"
```

---

## Task 8: Generalize `backtest.py`

Make the backtest loop over assets, using each config's `good_entry` and `weight_overrides`. Keep `label_good_entries`, `compute_signal_stats`, `derive_weights`, `SIGNAL_NAMES` importable for `test_backtest`. The MVRV 2× multiplier moves from a hardcoded default into Bitcoin's `weight_overrides`, so one existing test must be updated to pass the override explicitly.

**Files:**
- Modify: `scripts/backtest.py`
- Modify: `tests/test_backtest.py`

- [ ] **Step 1: Rewrite `backtest.py`**

Keep `label_good_entries`, `compute_signal_stats`, `derive_weights` as generic helpers (with back-compat defaults), drop the Bitcoin-specific `HALVING_DATES`/`get_cycle_ranges` (now in `assets/bitcoin.py`), and make `main()` loop. Full file:

```python
import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"

SIGNAL_NAMES = ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]

HOLDING_DAYS = 548
MIN_RETURN = 0.50


def label_good_entries(df: pd.DataFrame) -> pd.Series:
    """Generic: forward-return + a precomputed cheapness threshold column.

    df must contain 'price' and 'cycle_range_40pct'. Retained for test back-compat;
    asset-specific good-entry logic now lives in each asset's good_entry()."""
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


def compute_signal_stats(signals_df: pd.DataFrame, good_entries: pd.Series,
                         signal_names=SIGNAL_NAMES) -> dict:
    stats = {}
    for name in signal_names:
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


def derive_weights(stats: dict, signal_names=SIGNAL_NAMES, weight_overrides=None) -> dict:
    """Weight by precision; apply optional per-signal multipliers (e.g. MVRV 2×)."""
    raw = {s: stats[s]["precision"] for s in signal_names}
    for key, mult in (weight_overrides or {}).items():
        if key in raw:
            raw[key] = raw[key] * mult
    total = sum(raw.values())
    if total == 0:
        equal = round(1.0 / len(signal_names), 4)
        return {s: equal for s in signal_names}
    return {s: round(raw[s] / total, 4) for s in signal_names}


def _backtest_asset(cfg) -> None:
    hist_path = DATA_DIR / f"{cfg.id}_history.csv"
    sig_path = DATA_DIR / f"{cfg.id}_signal_history.csv"
    if not hist_path.exists() or not sig_path.exists():
        print(f"  skip {cfg.id}: history/signal file missing", file=sys.stderr)
        return
    price_df = pd.read_csv(hist_path)
    price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(sig_path)
    signals_df["date"] = pd.to_datetime(signals_df["date"])

    signal_names = [s.key for s in cfg.signals]
    good = cfg.good_entry(price_df)
    merged = price_df[["date"]].merge(signals_df[["date"] + signal_names], on="date", how="left")
    stats = compute_signal_stats(merged, good, signal_names)
    weights = derive_weights(stats, signal_names, cfg.weight_overrides)

    output = {
        "generated_at": str(pd.Timestamp.now().date()),
        "good_entry_definition": {"min_18mo_return": MIN_RETURN, "holding_days": HOLDING_DAYS},
        "signals": {name: {"weight": weights[name], **stats[name]} for name in signal_names},
    }
    (DATA_DIR / f"{cfg.id}_weights.json").write_text(json.dumps(output, indent=2))
    print(f"  {cfg.id}: {int(good.sum())} good-entry days; weights written")


def main():
    for cfg in ASSETS:
        print(f"Backtesting {cfg.display_name}...")
        _backtest_asset(cfg)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update the MVRV-multiplier test to pass the override**

The multiplier is now config-driven, not a `derive_weights` default. In `tests/test_backtest.py`, replace `test_derive_weights_mvrv_multiplier_applied` with:

```python
def test_derive_weights_mvrv_multiplier_applied():
    # mvrv_zscore's 2× multiplier now comes from the asset config's weight_overrides,
    # so equal-precision inputs give mvrv a higher weight only when the override is passed.
    stats = {name: {"precision": 0.5} for name in SIGNAL_NAMES}
    weights = derive_weights(stats, weight_overrides={"mvrv_zscore": 2.0})
    assert weights["mvrv_zscore"] > weights["ma_200w"]
```

The other backtest tests are unchanged: `derive_weights(stats)` with no override now returns equal weights for equal precision (still sums to 1.0, and `test_derive_weights_higher_precision_gets_higher_weight` still holds).

- [ ] **Step 3: Run backtest tests**

Run: `python -m pytest tests/test_backtest.py -v`
Expected: PASS — `label_good_entries`, `compute_signal_stats`, `derive_weights`, `SIGNAL_NAMES` all still importable; the updated MVRV test passes via the explicit override.

- [ ] **Step 4: Regenerate weights and confirm parity unaffected**

Run: `python scripts/backtest.py`
Expected: `bitcoin: N good-entry days; weights written`.

Run: `python scripts/score.py && python -m pytest -q`
Expected: 46 passed; `bitcoin: 54.5/100 — CLOSE` (weights regenerate to the same values; MVRV 2× preserved via `weight_overrides`).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest.py tests/test_backtest.py data/bitcoin_weights.json
git commit -m "refactor: config-driven backtest loop; Bitcoin halving logic moved to config"
```

---

## Task 9: `build_dashboard.py` — assemble per-asset data blobs

Transform `build_dashboard.py` so it produces, for **every** asset, a complete data blob the client can render from. Server-side it renders only the static shell; all dynamic content is embedded as JSON.

**Files:**
- Modify: `scripts/build_dashboard.py`

- [ ] **Step 1: Rewrite `build_dashboard.py`**

Reuse the existing helpers `get_score_color`, `compute_signal_bar`, `format_reading`, `compute_historical_scores`, `build_chart_data`, `build_trend_data`, `_score_to_verdict`, `_spark_label` (all already present). Replace `main()` and add an `_assemble_asset()` that returns the per-asset blob. Keep all existing helper functions unchanged.

```python
def _assemble_asset(cfg) -> dict:
    """Build the full client-render blob for one asset, or None if data is missing."""
    score_path = DATA_DIR / f"{cfg.id}_score.json"
    hist_path = DATA_DIR / f"{cfg.id}_history.csv"
    sig_path = DATA_DIR / f"{cfg.id}_signal_history.csv"
    weights_path = DATA_DIR / f"{cfg.id}_weights.json"
    if not all(p.exists() for p in (score_path, hist_path, sig_path, weights_path)):
        print(f"  skip {cfg.id}: missing data files", file=sys.stderr)
        return None

    current_score = json.loads(score_path.read_text())
    weights = json.loads(weights_path.read_text())
    price_df = pd.read_csv(hist_path)
    price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(sig_path)
    signals_df["date"] = pd.to_datetime(signals_df["date"])

    signal_meta = current_score["signal_meta"]
    signals = []
    for spec in cfg.signals:
        data = current_score["signals"][spec.key]
        signals.append({
            "key": spec.key,
            "display_name": data["display_name"],
            "reading": format_reading(spec.key, data["raw"]),
            "bar": compute_signal_bar(spec.key, data["raw"], data["score"], signal_meta[spec.key]),
        })

    composite = current_score["composite_score"]
    verdict = current_score["verdict"]
    if composite >= 80:
        distance_text = "You are in the Strong Buy zone"
    elif composite >= 72:
        distance_text = "You are in the Invest zone"
    else:
        distance_text = f"{72 - composite:.1f} pts from Invest zone"

    btc_price = price_df.dropna(subset=["price"])["price"].iloc[-1]

    methodology = [
        {
            "display_name": next(s.display_name for s in cfg.signals if s.key == name),
            "weight": weights["signals"][name]["weight"],
            "precision": weights["signals"][name]["precision"],
            "recall": weights["signals"][name]["recall"],
            "f1": weights["signals"][name]["f1"],
        }
        for name in (s.key for s in cfg.signals)
    ]

    return {
        "id": cfg.id,
        "display_name": cfg.display_name,
        "short_label": cfg.short_label,
        "accent_color": cfg.accent_color,
        "price_unit": cfg.price_unit,
        "price": round(float(btc_price)),
        "composite": composite,
        "verdict": verdict,
        "score_color": get_score_color(verdict),
        "distance_text": distance_text,
        "signals": signals,
        "chart": build_chart_data(price_df, signals_df, weights),
        "trend": build_trend_data(signals_df, weights),
        "methodology": methodology,
    }


def main():
    updated_at = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M %Z")
    assets = []
    for cfg in ASSETS:
        blob = _assemble_asset(cfg)
        if blob is not None:
            assets.append(blob)
    if not assets:
        raise RuntimeError("no assets could be assembled — aborting dashboard build")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        updated_at=updated_at,
        assets_json=json.dumps(assets),
        default_asset=assets[0]["id"],
    )
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard written to docs/index.html ({len(html):,} bytes; {len(assets)} asset(s))")


if __name__ == "__main__":
    main()
```

Add `from assets.registry import ASSETS` and `import sys` + the `sys.path.insert(...parent.parent...)` to the imports (alongside existing `datetime`, `ZoneInfo`, `json`, etc.). Remove the now-unused module-level `SIGNAL_DISPLAY` only if nothing else references it; otherwise leave it.

- [ ] **Step 2: Verify the build produces embedded JSON**

Run: `python scripts/build_dashboard.py`
Expected: `Dashboard written to docs/index.html (… ; 1 asset(s))`.

Run:
```bash
python -c "c=open('docs/index.html',encoding='utf-8').read(); assert '\"id\": \"bitcoin\"' in c or '\"id\":\"bitcoin\"' in c; assert 'accent_color' in c; print('OK blob embedded')"
```
Expected: `OK blob embedded`. (The page won't render correctly until Task 10's template — that's next.)

- [ ] **Step 3: Commit**

```bash
git add scripts/build_dashboard.py
git commit -m "refactor: build_dashboard assembles per-asset data blobs for client render"
```

---

## Task 10: Template — shell, chip switcher, and client-side `renderAsset()`

Replace the dynamic Jinja body with a static shell plus JS that renders the selected asset from the embedded `ASSETS` array, driven by the score-chip switcher. The score-card / zone-strip / sparkline / trend-toggle / signal-table CSS already exists in the template and is reused; only the rendering source changes (Jinja → JS).

**Files:**
- Modify: `templates/dashboard.html.j2`

- [ ] **Step 1a: Remove stale Jinja from the CSS**

The current `<style>` block hard-codes the selected score color via Jinja, which is no longer passed to the template (color is now set inline by JS per asset). Change these two lines:

```css
    .score-number { font-size: 4.5rem; font-weight: 700; line-height: 1; color: {{ score_color }}; }
    .verdict { font-size: 1.6rem; font-weight: 600; margin-top: 0.75rem; color: {{ score_color }}; letter-spacing: 0.05em; }
```

to static defaults (JS overrides the color at render time):

```css
    .score-number { font-size: 4.5rem; font-weight: 700; line-height: 1; color: #f0f0f0; }
    .verdict { font-size: 1.6rem; font-weight: 600; margin-top: 0.75rem; color: #f0f0f0; letter-spacing: 0.05em; }
```

After this, the template contains **no** `{{ ... }}` expressions except the three in the JS block added in Step 3 (`assets_json`, `updated_at`, `default_asset`).

- [ ] **Step 1b: Add chip CSS**

In the `<style>` block, after the existing `.trend-arrow` / `td.trend-col` rules (added in the trend feature), add:

```css
    /* ── asset score-chip switcher ── */
    .chip-row { display: flex; gap: 8px; margin-bottom: 1.2rem; }
    .chip { flex: 0 0 auto; min-width: 150px; background: #161616; border: 1.5px solid transparent; border-radius: 11px; padding: 11px 12px; cursor: pointer; transition: background .15s; text-align: left; }
    .chip:hover { background: #1a1a1a; }
    .chip.active { background: #1a1a1a; }
    .chip-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 4px; }
    .chip-name { font-size: 0.82rem; font-weight: 600; color: #bbb; }
    .chip-verdict { font-size: 0.6rem; font-weight: 700; letter-spacing: .03em; }
    .chip-score { font-size: 1.8rem; font-weight: 700; line-height: 1; }
    .chip-spark { display: flex; align-items: flex-end; gap: 2px; height: 16px; margin-top: 6px; }
    .chip-spark div { flex: 1; border-radius: 1px 1px 0 0; background: #333; }
    .chip-add { flex: 0 0 auto; min-width: 130px; background: transparent; border: 1.5px dashed #2a2a2a; border-radius: 11px; display: flex; align-items: center; justify-content: center; color: #3a3a3a; font-size: 0.8rem; font-weight: 600; }
```

- [ ] **Step 2: Replace the body markup**

Replace everything between `<body>` and the closing `</script></body></html>` with the static shell. The `<head>` (PWA tags, favicons, Chart.js, all existing CSS) is unchanged. Keep the `<canvas id="chart">` and `<details>` methodology block but with empty containers the JS fills.

```html
<body>
  <header>
    <h1><span>K</span><span>A</span><span>I</span><span>R</span><span>O</span><span>S</span></h1>
    <div class="meta" id="meta"></div>
  </header>

  <div class="chip-row" id="chip-row"></div>

  <div class="trend-toggle">
    <button id="tw-day"   onclick="setTrendWindow('day')">Day</button>
    <button id="tw-week"  onclick="setTrendWindow('week')">Week</button>
    <button id="tw-month" onclick="setTrendWindow('month')">Month</button>
  </div>

  <div class="score-card">
    <div class="score-number" id="score-number"></div>
    <div class="score-label">out of 100</div>
    <div class="verdict" id="verdict"></div>
    <div id="trend-delta" class="trend-delta"></div>
    <div class="zone-strip-wrap">
      <div class="zone-strip">
        <div class="zone z-avoid">AVOID</div>
        <div class="zone z-wait">WAIT</div>
        <div class="zone z-close">CLOSE</div>
        <div class="zone z-invest">INVEST</div>
        <div class="zone z-strong">STRONG BUY</div>
        <div class="z-cursor" id="zone-cursor" aria-hidden="true"></div>
      </div>
      <div class="strip-labels">
        <span class="strip-label edge-l" style="color:#ff5252">0</span>
        <span class="strip-label" style="left:25%; color:#ffd740">25</span>
        <span class="strip-label" style="left:50%; color:#ff9800">50</span>
        <span class="strip-label" style="left:72%; color:#00c853">72</span>
        <span class="strip-label" style="left:80%; color:#00e676">80</span>
        <span class="strip-label edge-r" style="left:100%; color:#555">100</span>
      </div>
      <div class="distance" id="distance"></div>
    </div>
    <div class="sparkline-wrap">
      <div id="sparkline" class="sparkline"></div>
      <div id="spark-lbl" class="spark-lbl"></div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Signal</th><th>Reading</th><th class="trend-col">▲▼</th>
        <th><span style="color:#ff525255">← Avoid</span> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <span style="color:#00c85355">Invest →</span></th>
      </tr>
    </thead>
    <tbody id="signal-tbody"></tbody>
  </table>

  <div class="chart-wrap"><canvas id="chart" height="120"></canvas></div>

  <details>
    <summary>Methodology ›</summary>
    <table class="meth-table">
      <thead><tr><th>Signal</th><th>Weight</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
      <tbody id="meth-tbody"></tbody>
    </table>
    <p class="def-note">
      Good entry: 18-month forward return ≥ 50% and entry price within bottom 40% of the cycle range.
      Weights are derived from the precision of each signal against historical good-entry days.
    </p>
  </details>
```

- [ ] **Step 3: Replace the JS block**

Remove the old Chart.js init block and the old trend `<script>` block. Add one combined script before `</body>` (the service-worker registration script stays as-is after it):

```html
  <script>
    const ASSETS = {{ assets_json }};
    const BY_ID = Object.fromEntries(ASSETS.map(a => [a.id, a]));
    const UPDATED_AT = {{ updated_at | tojson }};
    let currentId = (function () {
      try { const s = localStorage.getItem('kairos-asset'); if (s && BY_ID[s]) return s; } catch (e) {}
      return {{ default_asset | tojson }};
    })();
    let currentWindow = (function () {
      try { const w = localStorage.getItem('kairos-trend-window'); if (['day','week','month'].includes(w)) return w; } catch (e) {}
      return 'day';
    })();
    let chart = null;

    function zoneColor(s) {
      return s >= 80 ? '#00e676' : s >= 72 ? '#00c853' : s >= 50 ? '#ff9800' : s >= 25 ? '#ffd740' : '#ff5252';
    }

    function renderChips() {
      const row = document.getElementById('chip-row');
      row.innerHTML = ASSETS.map(function (a) {
        const col = zoneColor(a.composite);
        const sp = a.trend.day.spark;
        const mx = Math.max.apply(null, sp.map(p => p.score));
        const mn = Math.min.apply(null, sp.map(p => p.score)) - 3;
        const bars = sp.map(function (p, i) {
          const h = Math.max(Math.round(((p.score - mn) / (mx - mn)) * 100), 12);
          const last = i === sp.length - 1;
          return '<div style="height:' + h + '%;' + (last ? 'background:' + col + ';' : '') + '"></div>';
        }).join('');
        const active = a.id === currentId;
        return '<div class="chip' + (active ? ' active' : '') + '" style="' + (active ? 'border-color:' + a.accent_color : '') + '" onclick="setAsset(\'' + a.id + '\')">'
          + '<div class="chip-top"><span class="chip-name">' + a.short_label + '</span><span class="chip-verdict" style="color:' + col + '">' + a.verdict + '</span></div>'
          + '<div class="chip-score" style="color:' + col + '">' + Math.round(a.composite) + '</div>'
          + '<div class="chip-spark">' + bars + '</div></div>';
      }).join('') + '<div class="chip-add">+ more coming</div>';
    }

    function signalBarHTML(sig) {
      const b = sig.bar;
      if (!b.has_data) return '<span style="color:#444;font-size:0.8rem">No data</span>';
      return '<div class="sig-bar-wrap">'
        + '<span class="sig-status ' + b.status_class + '">' + b.status_text + '</span>'
        + '<div class="bar-outer"><div class="bar-track">'
        + '<div class="seg-avoid" style="width:' + b.avoid_pct + '%"></div>'
        + '<div class="seg-wait" style="width:' + b.wait_pct + '%"></div>'
        + '<div class="seg-invest" style="width:' + b.invest_pct + '%"></div></div>'
        + '<div class="thresh-line" style="left:' + b.thresh_avoid_pct + '%"></div>'
        + '<div class="thresh-line" style="left:' + b.thresh_invest_pct + '%"></div>'
        + '<div class="sig-cursor" style="left:' + b.cursor_pct + '%"></div></div>'
        + '<div class="bar-labels">'
        + '<span class="bar-label edge-l">' + b.edge_left + '</span>'
        + '<span class="bar-label" style="left:' + b.thresh_avoid_pct + '%;color:#555">' + b.thresh_avoid_lbl + '</span>'
        + '<span class="bar-label" style="left:' + b.thresh_invest_pct + '%;color:#555">' + b.thresh_invest_lbl + '</span>'
        + '<span class="bar-label edge-r" style="left:100%">' + b.edge_right + '</span></div></div>';
    }

    function renderTable(a) {
      document.getElementById('signal-tbody').innerHTML = a.signals.map(function (sig) {
        return '<tr><td>' + sig.display_name + '</td><td>' + sig.reading + '</td>'
          + '<td class="trend-col"><span class="trend-arrow" data-key="' + sig.key + '"></span></td>'
          + '<td>' + signalBarHTML(sig) + '</td></tr>';
      }).join('');
      document.getElementById('meth-tbody').innerHTML = a.methodology.map(function (m) {
        return '<tr><td>' + m.display_name + '</td><td>' + Math.round(m.weight * 100) + '%</td>'
          + '<td>' + Math.round(m.precision * 100) + '%</td><td>' + Math.round(m.recall * 100) + '%</td>'
          + '<td>' + m.f1.toFixed(2) + '</td></tr>';
      }).join('');
    }

    function renderChart(a) {
      const d = a.chart;
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('chart'), {
        type: 'line',
        data: { labels: d.dates, datasets: [
          { label: a.display_name + ' Price (USD)', data: d.prices, yAxisID: 'yPrice', borderColor: a.accent_color, borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
          { label: 'Composite Score', data: d.scores, yAxisID: 'yScore', borderColor: '#4dd0a7', borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        ]},
        options: {
          responsive: true, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#888', boxWidth: 12, font: { size: 11 } } } },
          scales: {
            x: { ticks: { color: '#555', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yPrice: { type: 'logarithmic', position: 'left', ticks: { color: '#555', font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yScore: { position: 'right', min: 0, max: 100, ticks: { color: '#555', font: { size: 10 } }, grid: { drawOnChartArea: false } },
          },
        },
      });
    }

    function applyTrend(a) {
      const t = a.trend[currentWindow];
      const sign = t.delta >= 0 ? '+' : '';
      const arr = t.delta > 0.5 ? '↑' : t.delta < -0.5 ? '↓' : '→';
      const col = t.delta > 0.5 ? '#00c853' : t.delta < -0.5 ? '#ff5252' : '#888';
      const lbl = { day: 'yesterday', week: 'last week', month: 'last month' }[currentWindow];
      const de = document.getElementById('trend-delta');
      de.textContent = arr + ' ' + sign + t.delta.toFixed(1) + ' pts vs ' + lbl;
      de.style.color = col;

      const scores = t.spark.map(p => p.score);
      const mx = Math.max.apply(null, scores), mn = Math.min.apply(null, scores) - 3;
      document.getElementById('sparkline').innerHTML = t.spark.map(function (p, i) {
        const h = Math.round(((p.score - mn) / (mx - mn)) * 30) + 4;
        const last = i === t.spark.length - 1;
        const op = (0.35 + 0.65 * (i / Math.max(1, t.spark.length - 1))).toFixed(2);
        return '<div class="spark-bar" style="width:' + (last ? 10 : 8) + 'px;height:' + h + 'px;background:' + (last ? zoneColor(p.score) : '#2a2a2a') + ';opacity:' + op + ';">'
          + '<div class="spark-tip">' + p.label + '<br><strong style="color:' + zoneColor(p.score) + '">' + p.score + ' — ' + p.verdict + '</strong></div></div>';
      }).join('');
      document.getElementById('spark-lbl').textContent = { day: 'last 7 days', week: 'last 7 weeks', month: 'last 7 months' }[currentWindow];

      const arrowChar = { '1': '↑', '0': '→', '-1': '↓' }, arrowCol = { '1': '#00c853', '0': '#ffd740', '-1': '#ff5252' };
      document.querySelectorAll('.trend-arrow[data-key]').forEach(function (el) {
        const v = String(t.arrows[el.getAttribute('data-key')]);
        el.textContent = arrowChar[v] || '→';
        el.style.color = arrowCol[v] || '#ffd740';
      });
      ['day', 'week', 'month'].forEach(function (k) {
        document.getElementById('tw-' + k).classList.toggle('active', k === currentWindow);
      });
    }

    function setTrendWindow(w) {
      currentWindow = w;
      try { localStorage.setItem('kairos-trend-window', w); } catch (e) {}
      applyTrend(BY_ID[currentId]);
    }
    window.setTrendWindow = setTrendWindow;

    function renderAsset(a) {
      document.getElementById('meta').innerHTML = a.price_unit + a.price.toLocaleString() + '&ensp;·&ensp;Updated ' + UPDATED_AT;
      const sn = document.getElementById('score-number');
      sn.textContent = a.composite; sn.style.color = a.score_color;
      const vd = document.getElementById('verdict');
      vd.textContent = a.verdict; vd.style.color = a.score_color;
      document.getElementById('zone-cursor').style.left = a.composite + '%';
      document.getElementById('distance').innerHTML = '<strong style="color:' + a.score_color + '">' + a.distance_text + '</strong>';
      renderTable(a);
      renderChart(a);
      applyTrend(a);
    }

    function setAsset(id) {
      currentId = id;
      try { localStorage.setItem('kairos-asset', id); } catch (e) {}
      renderChips();
      renderAsset(BY_ID[id]);
    }
    window.setAsset = setAsset;

    renderChips();
    renderAsset(BY_ID[currentId]);
  </script>
```

Arrow mapping is explicit: each `.trend-arrow` span carries `data-key="<signal key>"` (set in `renderTable` from `sig.key`), and `applyTrend` looks up `t.arrows[key]` by that attribute — no reliance on positional order.

- [ ] **Step 4: Build and verify in browser via Playwright**

Run: `python scripts/build_dashboard.py`

Start a server in the background: `python -m http.server 8765 --directory docs --bind 127.0.0.1`

Navigate to `http://127.0.0.1:8765/index.html` and verify:
1. No console errors.
2. One **Bitcoin** chip (55 / CLOSE, orange border) + a dimmed **"+ more coming"** chip.
3. Score card shows 54.5 / CLOSE; zone cursor near 54.5%; distance text present.
4. Six signal rows with range bars + direction arrows.
5. Trend toggle (Day/Week/Month) updates delta + sparkline.
6. Chart renders BTC price + composite score.

Match against `specs/2026-06-02-multi-asset-ui-reference.png`.

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: score-chip multi-asset UI with client-side renderAsset"
```

---

## Task 11: Second-config smoke test, workflows check, and final verification

**Files:**
- Modify: `tests/test_framework.py`
- Verify: `.github/workflows/daily.yml`, `.github/workflows/backtest.yml`

- [ ] **Step 1: Add a registry-extensibility test**

This proves "a new asset is just a config" without committing a real second asset. Append to `tests/test_framework.py`:

```python
def test_adding_a_config_appears_in_registry(monkeypatch):
    """A second AssetConfig appended to ASSETS is picked up generically."""
    import assets.registry as reg
    from assets.base import AssetConfig
    from assets import bitcoin
    extra = AssetConfig(
        id="testcoin", display_name="TestCoin", short_label="T", accent_color="#abc",
        price_unit="$", fetch=bitcoin.fetch, signals=bitcoin.CONFIG.signals,
        good_entry=bitcoin.good_entry, weight_overrides=None,
    )
    monkeypatch.setattr(reg, "ASSETS", reg.ASSETS + [extra])
    assert [a.id for a in reg.ASSETS] == ["bitcoin", "testcoin"]
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: 47 passed.

- [ ] **Step 3: Check the workflows need no change**

Read `.github/workflows/daily.yml` and `.github/workflows/backtest.yml`. They invoke the scripts by name (`python scripts/fetch_data.py`, etc.) and `git add data/ docs/index.html`. Since scripts keep their names and now loop internally, and `git add data/` captures the renamed `bitcoin_*` files, **no workflow change is required**. Confirm `daily.yml`'s `git add` line is `git add data/ docs/index.html` (directory-level, so new filenames are included). If it lists specific old filenames, update them to `data/`.

- [ ] **Step 4: Full pipeline end-to-end**

Run:
```bash
python scripts/compute_signals.py && python scripts/score.py && python scripts/backtest.py && python scripts/build_dashboard.py
```
Expected: each prints its `bitcoin: …` line; `docs/index.html` rebuilt; parity test still green.

Run: `python -m pytest -q`
Expected: 47 passed.

- [ ] **Step 5: Commit and push**

```bash
git add tests/test_framework.py .github/workflows/
git commit -m "test: registry extensibility; confirm workflows unchanged for multi-asset"
git push
```

After push, wait ~2 minutes for GitHub Pages, then verify `https://meyogui.github.io/fbtc-timing/` renders the Bitcoin chip + dashboard.

---

## Notes for the implementer

- **Parity is the safety net.** `tests/test_framework.py::test_bitcoin_scoring_parity` must stay green at every commit. If it goes red, a refactor changed Bitcoin's behaviour — stop and fix before continuing.
- **Re-export, don't break.** Tasks 3/8 keep `compute_*`, `signal_score`, `label_good_entries`, `compute_signal_stats`, `derive_weights`, `SIGNAL_NAMES`, `SIGNAL_DISPLAY`, `compute_score`, `get_verdict`, `compute_signal_bar`, `build_trend_data` importable from their original modules so the existing four test files keep passing untouched.
- **`git mv` for data files** preserves history and keeps the rename reviewable.
- **All numbers come from data**, not the mock — the gold mock values in the brainstorm are not used anywhere here (Bitcoin is the only asset).
