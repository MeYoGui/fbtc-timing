# Kairos Sell Signal & Spectrum UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a calibrated sell/take-profit signal and replace the buy-only zone strip with a symmetric bidirectional spectrum gauge answering "should I buy or sell?"

**Architecture:** Each signal gains a `sell_thresh`; a sell backtest runs `good_exit()` against history to derive sell weights; a `spectrum_pos` value (0–100, centred at 50=HOLD) is computed as `50 + (buy − effective_sell) / 2` and drives the new UI. The template replaces only the score card section; everything else (chip row, signal table, chart, methodology) is untouched.

**Tech Stack:** Python 3.11, pandas, numpy, Jinja2, vanilla JS, GitHub Actions, pywebpush

**Visual references:**
- `docs/superpowers/kairos-full-page-reference.png` — full page mockup
- `docs/superpowers/kairos-spectrum-mockup-reference.png` — spectrum gauge detail

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `assets/base.py` | Modify | Add `sell_thresh` to SignalSpec, `good_exit` + `sell_weight_overrides` to AssetConfig |
| `assets/bitcoin.py` | Modify | Add `sell_thresh` per signal, add `good_exit()` |
| `assets/eth.py` | Modify | Add `sell_thresh` per signal, add `good_exit()` |
| `scripts/compute_signals.py` | Modify | Add `sell_signal_score()`, write sell scores to CSV and JSON |
| `scripts/backtest.py` | Modify | Add `_backtest_sell_asset()`, write `{asset}_sell_weights.json` |
| `scripts/score.py` | Modify | Add `get_sell_verdict()`, `compute_spectrum_pos()`, write sell fields to score JSON |
| `scripts/build_dashboard.py` | Modify | Pass `spectrum_pos`, `spectrum_verdict`, `sell_composite`, `sell_verdict` to template |
| `templates/dashboard.html.j2` | Modify | Replace zone strip with spectrum gauge; update chip/asset JS rendering |
| `scripts/send_push.py` | Modify | Use `spectrum_pos` verdict + flags in push format |
| `data/bitcoin_sell_weights.json` | Create (generated) | Sell signal weights for BTC — committed after first backtest run |
| `data/ethereum_sell_weights.json` | Create (generated) | Sell signal weights for ETH — committed after first backtest run |
| `tests/test_sell_signal.py` | Create | Tests for sell scoring, good_exit, spectrum formula |

---

## Task 1: Data Model — `assets/base.py`

**Files:**
- Modify: `assets/base.py`
- Test: `tests/test_sell_signal.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sell_signal.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.base import SignalSpec, AssetConfig
import pandas as pd

def _dummy_compute(df): return df["price"]
def _dummy_fetch(): return pd.DataFrame()
def _dummy_entry(df): return pd.Series(dtype=bool)
def _dummy_exit(df): return pd.Series(dtype=bool)

def test_signal_spec_has_sell_thresh():
    spec = SignalSpec(
        key="mvrv_zscore", display_name="MVRV", compute=_dummy_compute,
        invest_thresh=-0.5, avoid_thresh=1.5, sell_thresh=3.5,
        range_lo=-3.0, range_hi=4.0, fmt="{:.1f}",
    )
    assert spec.sell_thresh == 3.5

def test_asset_config_has_good_exit():
    cfg = AssetConfig(
        id="test", display_name="Test", short_label="T", accent_color="#fff",
        price_unit="$", fetch=_dummy_fetch, signals=[],
        good_entry=_dummy_entry, good_exit=_dummy_exit,
    )
    assert callable(cfg.good_exit)

def test_asset_config_sell_weight_overrides_defaults_none():
    cfg = AssetConfig(
        id="test", display_name="Test", short_label="T", accent_color="#fff",
        price_unit="$", fetch=_dummy_fetch, signals=[],
        good_entry=_dummy_entry, good_exit=_dummy_exit,
    )
    assert cfg.sell_weight_overrides is None
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_sell_signal.py -v
```
Expected: `TypeError` — SignalSpec / AssetConfig missing fields.

- [ ] **Step 3: Update `assets/base.py`**

Replace the entire file with:

```python
"""Typed config interface every asset must satisfy."""
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd


@dataclass
class SignalSpec:
    """Binds a shared signal compute-function to one asset's thresholds + display meta."""
    key: str
    display_name: str
    compute: Callable[[pd.DataFrame], pd.Series]
    invest_thresh: float
    avoid_thresh: float
    sell_thresh: float        # raw value ABOVE which signal says "sell" (score = 100)
    range_lo: float
    range_hi: float
    fmt: str


@dataclass
class AssetConfig:
    id: str
    display_name: str
    short_label: str
    accent_color: str
    price_unit: str
    fetch: Callable[[], pd.DataFrame]
    signals: list[SignalSpec]
    good_entry: Callable[[pd.DataFrame], pd.Series]
    good_exit: Callable[[pd.DataFrame], pd.Series]   # symmetric with good_entry
    weight_overrides: Optional[dict[str, float]] = None
    sell_weight_overrides: Optional[dict[str, float]] = None
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_sell_signal.py -v
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```
git add assets/base.py tests/test_sell_signal.py
git commit -m "feat: add sell_thresh to SignalSpec, good_exit to AssetConfig"
```

---

## Task 2: Bitcoin Sell Config — `assets/bitcoin.py`

**Files:**
- Modify: `assets/bitcoin.py`
- Test: `tests/test_sell_signal.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sell_signal.py`:

```python
import numpy as np

def _make_btc_df(n=1500, prices=None):
    """Minimal BTC-like DataFrame for testing good_exit."""
    import pandas as pd, numpy as np
    dates = pd.date_range("2015-01-01", periods=n)
    if prices is None:
        prices = np.linspace(1000, 70000, n)
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "market_cap": np.array(prices) * 19_000_000,
        "mvrv": np.full(n, 2.0),
        "miner_revenue": np.full(n, 1e7),
        "fear_greed": np.full(n, 50),
    })

def test_btc_good_exit_returns_bool_series():
    from assets.bitcoin import good_exit
    df = _make_btc_df()
    result = good_exit(df)
    assert result.dtype == bool
    assert len(result) == len(df)

def test_btc_good_exit_false_when_price_at_bottom():
    """Price near minimum — should NOT be a good exit."""
    from assets.bitcoin import good_exit
    prices = [5000.0] * 1500  # flat low price, no big drawdown possible
    df = _make_btc_df(prices=prices)
    result = good_exit(df)
    assert result.sum() == 0

def test_btc_config_has_sell_thresh():
    from assets.bitcoin import CONFIG
    for spec in CONFIG.signals:
        assert hasattr(spec, "sell_thresh"), f"{spec.key} missing sell_thresh"
        assert spec.sell_thresh > spec.avoid_thresh, (
            f"{spec.key}: sell_thresh {spec.sell_thresh} should be > avoid_thresh {spec.avoid_thresh}"
        )
```

- [ ] **Step 2: Run to confirm failures**

```
pytest tests/test_sell_signal.py::test_btc_good_exit_returns_bool_series -v
```
Expected: `ImportError` — `good_exit` not defined in `assets/bitcoin.py`.

- [ ] **Step 3: Add `good_exit()` and `sell_thresh` to `assets/bitcoin.py`**

Add these constants after the existing `CYCLE_BOTTOM_PCT` line:

```python
CYCLE_TOP_PCT = 0.60     # price >= cycle_low + 60% of cycle range = top 40%
EXIT_HOLDING_DAYS = 548  # same 18-month window as good_entry
MIN_DRAWDOWN = 0.50      # forward price must fall >= 50% from this point
```

Add this function after `good_entry()`:

```python
def good_exit(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: price in top 40% of cycle range + ≥50% forward drawdown."""
    enriched = _get_cycle_ranges(df)
    prices = enriched["price"].values
    cycle_top_thresh = (
        enriched["cycle_low"] + CYCLE_TOP_PCT * (enriched["cycle_high"] - enriched["cycle_low"])
    ).values
    n = len(prices)
    exits = np.zeros(n, dtype=bool)
    for i in range(n - EXIT_HOLDING_DAYS):
        if prices[i] <= 0:
            continue
        fwd_drawdown = (prices[i] - prices[i + EXIT_HOLDING_DAYS]) / prices[i]
        if fwd_drawdown >= MIN_DRAWDOWN and prices[i] >= cycle_top_thresh[i]:
            exits[i] = True
    return pd.Series(exits, index=df.index)
```

Update `CONFIG` — add `good_exit=good_exit` and `sell_thresh` to every `SignalSpec`:

```python
CONFIG = AssetConfig(
    id="bitcoin",
    display_name="Bitcoin",
    short_label="₿ Bitcoin",
    accent_color="#f7931a",
    price_unit="$",
    fetch=fetch,
    good_entry=good_entry,
    good_exit=good_exit,
    weight_overrides={"mvrv_zscore": 2.0},
    signals=[
        SignalSpec("mvrv_zscore", "MVRV Z-Score", compute_mvrv_zscore,
                   invest_thresh=-0.5, avoid_thresh=1.5, sell_thresh=3.5,
                   range_lo=-3.0, range_hi=4.0, fmt="{:.1f}"),
        SignalSpec("ma_200w", "200-Week MA", compute_200w_ma_ratio,
                   invest_thresh=1.0, avoid_thresh=1.2, sell_thresh=2.5,
                   range_lo=0.5, range_hi=3.0, fmt="{:.1f}×"),
        SignalSpec("monthly_rsi", "Monthly RSI", compute_monthly_rsi,
                   invest_thresh=40.0, avoid_thresh=70.0, sell_thresh=78.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
        SignalSpec("pi_cycle", "Pi Cycle", compute_pi_cycle_ratio,
                   invest_thresh=0.9, avoid_thresh=1.0, sell_thresh=1.0,
                   range_lo=0.0, range_hi=1.5, fmt="{:.1f}"),
        SignalSpec("puell", "Puell Multiple", compute_puell_multiple,
                   invest_thresh=0.5, avoid_thresh=1.5, sell_thresh=3.0,
                   range_lo=0.0, range_hi=4.0, fmt="{:.1f}"),
        SignalSpec("fear_greed", "Fear & Greed", compute_fear_greed,
                   invest_thresh=25.0, avoid_thresh=50.0, sell_thresh=78.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
    ],
)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_sell_signal.py -v -k "btc"
```
Expected: all 3 BTC tests pass.

- [ ] **Step 5: Commit**

```
git add assets/bitcoin.py tests/test_sell_signal.py
git commit -m "feat: add good_exit and sell_thresh to Bitcoin config"
```

---

## Task 3: Ethereum Sell Config — `assets/eth.py`

**Files:**
- Modify: `assets/eth.py`
- Test: `tests/test_sell_signal.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sell_signal.py`:

```python
def _make_eth_df(n=1500, prices=None):
    import pandas as pd, numpy as np
    dates = pd.date_range("2016-01-01", periods=n)
    if prices is None:
        prices = np.linspace(10, 4800, n)
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "market_cap": np.array(prices) * 120_000_000,
        "mvrv": np.full(n, 2.0),
        "btc_price": np.linspace(500, 60000, n),
        "fear_greed": np.full(n, 50),
    })

def test_eth_good_exit_returns_bool_series():
    from assets.eth import good_exit
    df = _make_eth_df()
    result = good_exit(df)
    assert result.dtype == bool
    assert len(result) == len(df)

def test_eth_good_exit_false_when_price_at_bottom():
    from assets.eth import good_exit
    prices = [100.0] * 1500
    df = _make_eth_df(prices=prices)
    result = good_exit(df)
    assert result.sum() == 0

def test_eth_config_has_sell_thresh():
    from assets.eth import CONFIG
    for spec in CONFIG.signals:
        assert hasattr(spec, "sell_thresh"), f"{spec.key} missing sell_thresh"
```

- [ ] **Step 2: Run to confirm failures**

```
pytest tests/test_sell_signal.py::test_eth_good_exit_returns_bool_series -v
```
Expected: `ImportError`.

- [ ] **Step 3: Add `good_exit()` and `sell_thresh` to `assets/eth.py`**

Add constants after the existing `MIN_RETURN` line:

```python
CYCLE_TOP_PCT = 0.75     # price >= expanding_low + 75% of expanding range = top 25%
EXIT_HOLDING_DAYS = 548
MIN_DRAWDOWN = 0.50
```

Add this function after `good_entry()`:

```python
def good_exit(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: price in top 25% of expanding range + ≥50% forward drawdown.

    Uses expanding().max() / expanding().min() as causal cycle high/low — avoids
    the permanently-high bar of a fixed ATH in stagnating markets.
    """
    prices = df["price"].values
    expanding_high = df["price"].expanding().max().values
    expanding_low  = df["price"].expanding().min().values
    top_thresh = expanding_low + CYCLE_TOP_PCT * (expanding_high - expanding_low)
    n = len(prices)
    exits = np.zeros(n, dtype=bool)
    for i in range(n - EXIT_HOLDING_DAYS):
        if prices[i] <= 0:
            continue
        fwd_drawdown = (prices[i] - prices[i + EXIT_HOLDING_DAYS]) / prices[i]
        if fwd_drawdown >= MIN_DRAWDOWN and prices[i] >= top_thresh[i]:
            exits[i] = True
    return pd.Series(exits, index=df.index)
```

Update `CONFIG` — add `good_exit=good_exit` and `sell_thresh` to every `SignalSpec`:

```python
CONFIG = AssetConfig(
    id="ethereum",
    display_name="Ethereum",
    short_label="Ξ Ethereum",
    accent_color="#627eea",
    price_unit="$",
    fetch=fetch,
    good_entry=good_entry,
    good_exit=good_exit,
    weight_overrides=None,
    signals=[
        SignalSpec("mvrv_zscore", "MVRV Z-Score", compute_mvrv_zscore,
                   invest_thresh=-1.3209, avoid_thresh=3.5901, sell_thresh=3.0,
                   range_lo=-3.0, range_hi=5.0, fmt="{:.1f}"),
        SignalSpec("ma_200w", "200-Week MA", compute_200w_ma_ratio,
                   invest_thresh=0.8669, avoid_thresh=0.9567, sell_thresh=2.0,
                   range_lo=0.5, range_hi=3.0, fmt="{:.1f}×"),
        SignalSpec("monthly_rsi", "Monthly RSI", compute_monthly_rsi,
                   invest_thresh=40.0, avoid_thresh=70.0, sell_thresh=78.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
        SignalSpec("eth_btc_ratio", "ETH/BTC Ratio", compute_eth_btc_ratio_z,
                   invest_thresh=-1.0799, avoid_thresh=0.8833, sell_thresh=1.5,
                   range_lo=-2.0, range_hi=3.0, fmt="{:.1f}"),
        SignalSpec("mayer_multiple", "Mayer Multiple", compute_mayer_multiple,
                   invest_thresh=0.6451, avoid_thresh=1.4605, sell_thresh=2.4,
                   range_lo=0.0, range_hi=4.0, fmt="{:.1f}×"),
        SignalSpec("fear_greed", "Fear & Greed", compute_fear_greed,
                   invest_thresh=25.0, avoid_thresh=50.0, sell_thresh=78.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
    ],
)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_sell_signal.py -v
```
Expected: all tests pass (including BTC tests from Task 2).

- [ ] **Step 5: Commit**

```
git add assets/eth.py tests/test_sell_signal.py
git commit -m "feat: add good_exit and sell_thresh to Ethereum config"
```

---

## Task 4: Sell Score Computation — `scripts/compute_signals.py`

**Files:**
- Modify: `scripts/compute_signals.py`
- Test: `tests/test_sell_signal.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sell_signal.py`:

```python
def test_sell_signal_score_above_thresh():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from compute_signals import sell_signal_score
    assert sell_signal_score(4.0, sell_thresh=3.5) == 100

def test_sell_signal_score_below_thresh():
    from compute_signals import sell_signal_score
    assert sell_signal_score(2.0, sell_thresh=3.5) == 0

def test_sell_signal_score_exactly_at_thresh():
    from compute_signals import sell_signal_score
    # strictly greater than — at threshold is NOT a sell signal
    assert sell_signal_score(3.5, sell_thresh=3.5) == 0

def test_compute_all_signals_includes_sell_columns():
    import pandas as pd, numpy as np, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from compute_signals import compute_all_signals
    from assets.bitcoin import CONFIG
    n = 1500
    dates = pd.date_range("2015-01-01", periods=n)
    df = pd.DataFrame({
        "date": dates,
        "price": np.linspace(1000, 70000, n),
        "market_cap": np.linspace(1e10, 1e12, n),
        "mvrv": np.full(n, 1.0),
        "miner_revenue": np.full(n, 1e7),
        "fear_greed": np.full(n, 50),
    })
    out = compute_all_signals(df, CONFIG.signals)
    for spec in CONFIG.signals:
        assert f"{spec.key}_sell" in out.columns, f"missing {spec.key}_sell column"
        assert set(out[f"{spec.key}_sell"].dropna().unique()).issubset({0, 100})
```

- [ ] **Step 2: Run to confirm failures**

```
pytest tests/test_sell_signal.py -v -k "sell_signal_score or sell_columns"
```
Expected: `ImportError` — `sell_signal_score` not defined.

- [ ] **Step 3: Add `sell_signal_score` and update `compute_all_signals`**

Add after the `score_series` function:

```python
def sell_signal_score(value: float, sell_thresh: float) -> int:
    """100 if raw value strictly exceeds sell_thresh, else 0."""
    return 100 if value > sell_thresh else 0
```

Update `compute_all_signals`:

```python
def compute_all_signals(df: pd.DataFrame, signals: list) -> pd.DataFrame:
    """Build {key}_raw, {key} buy-score, and {key}_sell sell-score columns per SignalSpec."""
    out = pd.DataFrame({"date": df["date"]})
    for spec in signals:
        raw = spec.compute(df)
        out[f"{spec.key}_raw"] = raw
        out[spec.key] = score_series(raw, spec.invest_thresh, spec.avoid_thresh)
        out[f"{spec.key}_sell"] = raw.apply(
            lambda v: sell_signal_score(v, spec.sell_thresh) if pd.notna(v) else 0
        )
    return out
```

Update `_last_valid` and `_process_asset` to capture sell scores:

```python
def _process_asset(cfg: AssetConfig) -> None:
    hist_path = DATA_DIR / f"{cfg.id}_history.csv"
    if not hist_path.exists():
        print(f"  skip {cfg.id}: {hist_path.name} missing", file=sys.stderr)
        return
    df = pd.read_csv(hist_path)
    df["date"] = pd.to_datetime(df["date"])

    signals = compute_all_signals(df, cfg.signals)
    signals.to_csv(DATA_DIR / f"{cfg.id}_signal_history.csv", index=False)

    def _last_valid(raw_col: str, score_col: str, sell_col: str) -> tuple:
        valid = signals[raw_col].notna()
        if not valid.any():
            return float("nan"), 50, 0
        row = signals[valid].iloc[-1]
        return row[raw_col], int(row[score_col]), int(row[sell_col])

    latest = signals.iloc[-1]
    current = {"date": str(latest["date"].date()), "signals": {}}
    for spec in cfg.signals:
        raw, score, sell_score = _last_valid(
            f"{spec.key}_raw", spec.key, f"{spec.key}_sell"
        )
        current["signals"][spec.key] = {
            "raw": _sanitize_float(raw),
            "score": score,
            "sell_score": sell_score,
        }

    (DATA_DIR / f"{cfg.id}_current_signals.json").write_text(json.dumps(current, indent=2))
    print(f"  {cfg.id}: signals for {current['date']}")
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add scripts/compute_signals.py tests/test_sell_signal.py
git commit -m "feat: add sell_signal_score and sell columns to compute_signals"
```

---

## Task 5: Sell Backtest — `scripts/backtest.py`

**Files:**
- Modify: `scripts/backtest.py`
- Test: `tests/test_sell_signal.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sell_signal.py`:

```python
def test_backtest_sell_derive_weights_sum_to_one():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from backtest import derive_weights
    import pandas as pd, numpy as np
    signal_names = ["mvrv_zscore", "ma_200w", "monthly_rsi"]
    stats = {name: {"precision": 0.5} for name in signal_names}
    weights = derive_weights(stats, signal_names)
    assert abs(sum(weights.values()) - 1.0) < 1e-3

def test_backtest_sell_fg_zeroed_when_precision_low():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from backtest import derive_weights
    signal_names = ["mvrv_zscore", "fear_greed"]
    # fear_greed precision < 0.30 → should be zeroed before weighting
    stats = {"mvrv_zscore": {"precision": 0.6}, "fear_greed": {"precision": 0.20}}
    weights = derive_weights(stats, signal_names, sell_side=True)
    assert weights["fear_greed"] == 0.0
    assert abs(weights["mvrv_zscore"] - 1.0) < 1e-3
```

- [ ] **Step 2: Run to confirm failures**

```
pytest tests/test_sell_signal.py -v -k "backtest_sell"
```
Expected: `TypeError` — `derive_weights` doesn't accept `sell_side`.

- [ ] **Step 3: Update `scripts/backtest.py`**

Add `sell_side=False` parameter to `derive_weights`:

```python
def derive_weights(stats: dict, signal_names=SIGNAL_NAMES,
                   weight_overrides=None, sell_side=False) -> dict:
    """Weight by precision; zero out Fear & Greed on sell side if precision < 0.30."""
    raw = {s: stats[s]["precision"] for s in signal_names}
    if sell_side and "fear_greed" in raw and raw["fear_greed"] < 0.30:
        raw["fear_greed"] = 0.0
    for key, mult in (weight_overrides or {}).items():
        if key in raw:
            raw[key] = raw[key] * mult
    total = sum(raw.values())
    if total == 0:
        equal = round(1.0 / len(signal_names), 4)
        return {s: equal for s in signal_names}
    return {s: round(raw[s] / total, 4) for s in signal_names}
```

Add `_backtest_sell_asset` after `_backtest_asset`:

```python
def _backtest_sell_asset(cfg) -> None:
    """Mirror of _backtest_asset using good_exit() as target and {key}_sell columns."""
    hist_path = DATA_DIR / f"{cfg.id}_history.csv"
    sig_path = DATA_DIR / f"{cfg.id}_signal_history.csv"
    if not hist_path.exists() or not sig_path.exists():
        print(f"  skip {cfg.id} sell: history/signal file missing", file=sys.stderr)
        return
    price_df = pd.read_csv(hist_path)
    price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(sig_path)
    signals_df["date"] = pd.to_datetime(signals_df["date"])

    signal_names = [s.key for s in cfg.signals]
    sell_col_names = [f"{s.key}_sell" for s in cfg.signals]

    # Rename sell columns to plain names for compute_signal_stats reuse
    sell_df = signals_df[["date"] + sell_col_names].rename(
        columns={f"{k}_sell": k for k in signal_names}
    )

    good = cfg.good_exit(price_df)
    merged = price_df[["date"]].merge(sell_df, on="date", how="left")
    stats = compute_signal_stats(merged, good, signal_names)
    weights = derive_weights(stats, signal_names, cfg.sell_weight_overrides, sell_side=True)

    output = {
        "generated_at": str(pd.Timestamp.now().date()),
        "good_exit_definition": {"min_drawdown": 0.50, "holding_days": 548},
        "signals": {name: {"weight": weights[name], **stats[name]} for name in signal_names},
    }
    (DATA_DIR / f"{cfg.id}_sell_weights.json").write_text(json.dumps(output, indent=2))
    print(f"  {cfg.id} sell: {int(good.sum())} good-exit days; sell weights written")
```

Update `main()`:

```python
def main():
    for cfg in ASSETS:
        print(f"Backtesting {cfg.display_name} (buy)...")
        _backtest_asset(cfg)
        print(f"Backtesting {cfg.display_name} (sell)...")
        _backtest_sell_asset(cfg)
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add scripts/backtest.py tests/test_sell_signal.py
git commit -m "feat: add sell backtest with good_exit and sell weights"
```

---

## Task 6: Sell Composite + Spectrum Position — `scripts/score.py`

**Files:**
- Modify: `scripts/score.py`
- Test: `tests/test_sell_signal.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sell_signal.py`:

```python
def test_get_sell_verdict():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from score import get_sell_verdict
    assert get_sell_verdict(10)  == "LOW"
    assert get_sell_verdict(25)  == "ELEVATED"
    assert get_sell_verdict(50)  == "HIGH"
    assert get_sell_verdict(75)  == "STRONG SELL"
    assert get_sell_verdict(100) == "STRONG SELL"

def test_compute_spectrum_pos_neutral():
    from score import compute_spectrum_pos
    # sell_composite < 25 → effective_sell = 0
    # spectrum_pos = 50 + (50 - 0) / 2 = 75
    assert compute_spectrum_pos(buy=50.0, sell=10.0) == 75.0

def test_compute_spectrum_pos_active_sell():
    from score import compute_spectrum_pos
    # sell_composite >= 25 → used directly
    # spectrum_pos = clamp(50 + (20 - 60) / 2, 0, 100) = clamp(30, 0, 100) = 30
    assert compute_spectrum_pos(buy=20.0, sell=60.0) == 30.0

def test_compute_spectrum_pos_clamped():
    from score import compute_spectrum_pos
    assert compute_spectrum_pos(buy=100.0, sell=0.0) == 100.0
    assert compute_spectrum_pos(buy=0.0, sell=100.0) == 0.0

def test_get_spectrum_verdict():
    from score import get_spectrum_verdict
    assert get_spectrum_verdict(10)  == "TAKE PROFIT"
    assert get_spectrum_verdict(20)  == "SELL"
    assert get_spectrum_verdict(40)  == "HOLD"
    assert get_spectrum_verdict(60)  == "BUY"
    assert get_spectrum_verdict(80)  == "STRONG BUY"
    assert get_spectrum_verdict(100) == "STRONG BUY"
```

- [ ] **Step 2: Run to confirm failures**

```
pytest tests/test_sell_signal.py -v -k "sell_verdict or spectrum"
```
Expected: `ImportError`.

- [ ] **Step 3: Add new functions to `scripts/score.py`**

Add these functions after `get_verdict`:

```python
def get_sell_verdict(sell_score: float) -> str:
    if sell_score >= 75: return "STRONG SELL"
    if sell_score >= 50: return "HIGH"
    if sell_score >= 25: return "ELEVATED"
    return "LOW"


def compute_spectrum_pos(buy: float, sell: float) -> float:
    """Spectrum position 0–100. 50 = HOLD. 100 = STRONG BUY. 0 = TAKE PROFIT.
    sell only pulls the pointer left when it is meaningfully active (>= 25)."""
    effective_sell = sell if sell >= 25 else 0.0
    raw = 50.0 + (buy - effective_sell) / 2.0
    return round(max(0.0, min(100.0, raw)), 1)


def get_spectrum_verdict(spectrum_pos: float) -> str:
    if spectrum_pos >= 80: return "STRONG BUY"
    if spectrum_pos >= 60: return "BUY"
    if spectrum_pos >= 40: return "HOLD"
    if spectrum_pos >= 20: return "SELL"
    return "TAKE PROFIT"
```

Update `_score_asset` to compute sell fields. Add after `composite = compute_score(...)`:

```python
    # ── sell composite ────────────────────────────────────────────────
    sell_weights_path = DATA_DIR / f"{cfg.id}_sell_weights.json"
    sell_composite = 0.0
    if sell_weights_path.exists():
        sell_weights = json.loads(sell_weights_path.read_text())
        sell_signals = {
            name: {"score": data.get("sell_score", 0)}
            for name, data in current["signals"].items()
        }
        sell_composite = round(compute_score(sell_signals, sell_weights), 1)
    else:
        print(f"  {cfg.id}: sell weights missing — run backtest first", file=sys.stderr)

    sell_verdict = get_sell_verdict(sell_composite)
    spectrum_pos = compute_spectrum_pos(composite, sell_composite)
    spectrum_verdict = get_spectrum_verdict(spectrum_pos)
```

Add these fields to the `output` dict in `_score_asset`:

```python
    output = {
        "date": current["date"],
        "composite_score": composite,
        "verdict": verdict,
        "sell_composite": sell_composite,
        "sell_verdict": sell_verdict,
        "spectrum_pos": spectrum_pos,
        "spectrum_verdict": spectrum_verdict,
        # ... existing signals, weights, signal_meta keys unchanged ...
    }
```

Keep all existing keys (`signals`, `weights`, `signal_meta`) exactly as they are.

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add scripts/score.py tests/test_sell_signal.py
git commit -m "feat: add sell composite, spectrum_pos, and spectrum_verdict to score.py"
```

---

## Task 7: Dashboard Builder — `scripts/build_dashboard.py`

**Files:**
- Modify: `scripts/build_dashboard.py`

- [ ] **Step 1: Update `get_score_color` to use spectrum verdicts**

Replace the existing function:

```python
def get_score_color(verdict: str) -> str:
    return {
        "STRONG BUY":  "#00e676",
        "BUY":         "#00c853",
        "HOLD":        "#ffd740",
        "SELL":        "#ff9800",
        "TAKE PROFIT": "#ff5252",
    }.get(verdict, "#ffd740")
```

- [ ] **Step 2: Update `_assemble_asset` to read and pass sell fields**

After `composite = current_score["composite_score"]` and `verdict = current_score["verdict"]`, add:

```python
    sell_composite   = current_score.get("sell_composite", 0.0)
    sell_verdict     = current_score.get("sell_verdict", "LOW")
    spectrum_pos     = current_score.get("spectrum_pos", round(50 + composite / 2, 1))
    spectrum_verdict = current_score.get("spectrum_verdict", verdict)
```

Replace the `distance_text` block:

```python
    if spectrum_pos >= 80:
        distance_text = "Strong Buy zone"
    elif spectrum_pos >= 60:
        distance_text = f"{80 - spectrum_pos:.1f} pts from Strong Buy"
    elif spectrum_pos > 40:
        distance_text = f"{60 - spectrum_pos:.1f} pts from Buy zone"
    elif spectrum_pos >= 20:
        distance_text = f"{spectrum_pos - 20:.1f} pts into Sell zone"
    else:
        distance_text = "Take profit zone"
```

Replace the `return` dict to use `spectrum_verdict` for `score_color` and add sell fields:

```python
    return {
        "id":               cfg.id,
        "display_name":     cfg.display_name,
        "short_label":      cfg.short_label,
        "accent_color":     cfg.accent_color,
        "price_unit":       cfg.price_unit,
        "price":            round(float(current_price)),
        "composite":        composite,          # buy score — used in buy score box
        "verdict":          verdict,            # buy verdict — used in buy score box
        "sell_composite":   sell_composite,
        "sell_verdict":     sell_verdict,
        "spectrum_pos":     spectrum_pos,
        "spectrum_verdict": spectrum_verdict,
        "score_color":      get_score_color(spectrum_verdict),
        "distance_text":    distance_text,
        "signals":          signals,
        "chart":            build_chart_data(price_df, signals_df, weights, signal_names),
        "trend":            build_trend_data(signals_df, weights, signal_names),
        "methodology":      methodology,
    }
```

- [ ] **Step 3: Update `_notify_entries` to include sell fields**

```python
def _notify_entries(assets: list) -> list:
    return [
        {
            "id":               a["id"],
            "display_name":     a["display_name"],
            "composite":        a["composite"],
            "sell_composite":   a["sell_composite"],
            "spectrum_pos":     a["spectrum_pos"],
            "spectrum_verdict": a["spectrum_verdict"],
            "delta_1d":         a["trend"]["day"]["delta"],
        }
        for a in assets
    ]
```

- [ ] **Step 4: Run existing dashboard tests**

```
pytest tests/test_build_dashboard.py -v
```
Expected: all pass (the test only checks that the builder runs without error).

- [ ] **Step 5: Commit**

```
git add scripts/build_dashboard.py
git commit -m "feat: pass spectrum_pos, sell_composite, sell_verdict to dashboard template"
```

---

## Task 8: Dashboard Template — `templates/dashboard.html.j2`

**Files:**
- Modify: `templates/dashboard.html.j2`

This task replaces the score card section only. All other HTML is unchanged.

- [ ] **Step 1: Add spectrum CSS**

Inside the `<style>` block, **remove** all lines from `.score-card` through `.distance { ... }` (the old zone strip styles), and **replace** with:

```css
    .score-card { background: #161616; border-radius: 12px; padding: 1.75rem 2rem 1.5rem; text-align: center; margin-bottom: 2rem; }
    .action-line { font-size: 2.6rem; font-weight: 800; letter-spacing: 0.04em; line-height: 1; margin-bottom: 0.2rem; }
    .action-sub  { font-size: 0.88rem; color: #666; margin-bottom: 1.6rem; }

    /* spectrum gauge — 5 equal zones, each flex:20 */
    .spectrum-wrap { max-width: 500px; margin: 0 auto; padding-top: 34px; position: relative; }
    .spectrum-zones { display: flex; height: 30px; border-radius: 7px; overflow: hidden; }
    .sz { display: flex; align-items: center; justify-content: center; flex: 20; font-size: 0.52rem; font-weight: 700; letter-spacing: 0.04em; text-align: center; line-height: 1.2; }
    .sz-tp   { background: #ff525230; color: #ff5252; }
    .sz-sell { background: #ff980028; color: #ff9800; }
    .sz-hold { background: #ffffff10; color: #555; }
    .sz-buy  { background: #00c85328; color: #00c853; }
    .sz-sbuy { background: #00e67630; color: #00e676; }
    .spec-cursor { position: absolute; top: 34px; height: 30px; width: 3px; background: #fff; border-radius: 2px; box-shadow: 0 0 10px rgba(255,255,255,0.9); transform: translateX(-50%); }
    .spec-cursor-label { position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); background: #fff; color: #000; font-size: 0.72rem; font-weight: 800; padding: 2px 7px; border-radius: 4px; white-space: nowrap; box-shadow: 0 0 8px rgba(255,255,255,0.3); }
    .spec-cursor-label::after { content:''; position:absolute; top:100%; left:50%; transform:translateX(-50%); border:4px solid transparent; border-top-color:#fff; }
    .spec-ticks { position: relative; height: 15px; margin-top: 5px; }
    .spec-ticks span { position: absolute; font-size: 0.65rem; transform: translateX(-50%); white-space: nowrap; }

    /* sell / buy score boxes */
    .score-row { display: flex; gap: 1px; margin-top: 1.25rem; }
    .score-half { flex: 1; padding: 0.75rem 1rem; }
    .score-half-l { border-radius: 8px 0 0 8px; background: #ff525210; border: 1px solid #ff525220; }
    .score-half-r { border-radius: 0 8px 8px 0; background: #00e67610; border: 1px solid #00e67620; }
    .sh-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; margin-bottom: 4px; }
    .sh-label-sell { color: #ff525299; }
    .sh-label-buy  { color: #00e67699; }
    .sh-score { font-size: 1.6rem; font-weight: 800; line-height: 1; }
    .sh-verdict { font-size: 0.68rem; color: #555; margin-top: 3px; }
    .distance { margin-top: 0.5rem; font-size: 0.85rem; color: #666; }
```

- [ ] **Step 2: Replace score card HTML**

Remove the old score card block (from `<div class="score-card">` to its closing `</div>`) and replace with:

```html
  <div class="score-card">
    <div class="action-line" id="spectrum-verdict"></div>
    <div class="action-sub" id="distance"></div>

    <div class="spectrum-wrap">
      <div class="spectrum-zones">
        <div class="sz sz-tp">TAKE<br>PROFIT</div>
        <div class="sz sz-sell">SELL</div>
        <div class="sz sz-hold">HOLD</div>
        <div class="sz sz-buy">BUY</div>
        <div class="sz sz-sbuy">STRONG<br>BUY</div>
      </div>
      <div class="spec-cursor" id="spec-cursor">
        <div class="spec-cursor-label" id="spec-cursor-label"></div>
      </div>
      <div class="spec-ticks">
        <span style="left:0;transform:none;color:#ff525266">0</span>
        <span style="left:20%;color:#ff980055">20</span>
        <span style="left:40%;color:#55555566">40</span>
        <span style="left:60%;color:#00c85355">60</span>
        <span style="left:80%;color:#00c85377">80</span>
        <span style="left:100%;transform:translateX(-100%);color:#00e67677">100</span>
      </div>
    </div>

    <div class="score-row">
      <div class="score-half score-half-l">
        <div class="sh-label sh-label-sell">Sell signal</div>
        <div class="sh-score" id="sell-score"></div>
        <div class="sh-verdict" id="sell-verdict"></div>
      </div>
      <div class="score-half score-half-r">
        <div class="sh-label sh-label-buy">Buy signal</div>
        <div class="sh-score" id="buy-score"></div>
        <div class="sh-verdict" id="buy-verdict"></div>
      </div>
    </div>

    <div id="trend-delta" class="trend-delta"></div>
    <div class="sparkline-wrap">
      <div id="sparkline" class="sparkline"></div>
      <div id="spark-lbl" class="spark-lbl"></div>
    </div>
  </div>
```

- [ ] **Step 3: Update the `zoneColor` JS function**

Replace the old `zoneColor`:

```js
    function zoneColor(s) {
      return s >= 80 ? '#00e676' : s >= 60 ? '#00c853' : s >= 40 ? '#ffd740' : s >= 20 ? '#ff9800' : '#ff5252';
    }
```

- [ ] **Step 4: Update `renderAsset` JS function**

Replace the old body of `renderAsset(a)`:

```js
    function renderAsset(a) {
      document.getElementById('meta').innerHTML = a.price_unit + a.price.toLocaleString() + '&ensp;·&ensp;Updated ' + UPDATED_AT;

      // spectrum verdict + cursor
      var sv = document.getElementById('spectrum-verdict');
      sv.textContent = a.spectrum_verdict;
      sv.style.color = a.score_color;
      document.getElementById('spec-cursor').style.left = a.spectrum_pos + '%';
      document.getElementById('spec-cursor-label').textContent = a.spectrum_pos.toFixed(1);
      document.getElementById('distance').innerHTML = '<strong style="color:' + a.score_color + '">' + a.distance_text + '</strong>';

      // sell / buy score boxes
      var sellScore = document.getElementById('sell-score');
      sellScore.textContent = a.sell_composite.toFixed(1);
      sellScore.style.color = a.sell_composite >= 25 ? '#ff9800' : '#ff5252';
      document.getElementById('sell-verdict').textContent = a.sell_verdict;

      var buyScore = document.getElementById('buy-score');
      buyScore.textContent = a.composite.toFixed(1);
      buyScore.style.color = zoneColor(a.composite);
      document.getElementById('buy-verdict').textContent = a.verdict;

      renderTable(a);
      renderChart(a);
      applyTrend(a);
    }
```

- [ ] **Step 5: Update `renderChips` to use spectrum_pos and spectrum_verdict**

Inside the `renderChips` function, change the line building each chip to use `a.spectrum_pos` and `a.spectrum_verdict`:

```js
        const col = zoneColor(a.spectrum_pos);
        // ... (sp, mx, mn, bars remain the same using a.trend.day.spark) ...
        return '<div class="chip' + (active ? ' active' : '') + '" style="' + (active ? 'border-color:' + a.accent_color : '') + '" onclick="setAsset(\'' + a.id + '\')">'
          + '<div class="chip-top"><span class="chip-name">' + a.short_label + '</span><span class="chip-verdict" style="color:' + col + '">' + a.spectrum_verdict + '</span></div>'
          + '<div class="chip-score" style="color:' + col + '">' + a.spectrum_pos.toFixed(1) + '</div>'
          + '<div class="chip-spark">' + bars + '</div></div>';
```

- [ ] **Step 6: Verify template builds without error**

```
python scripts/build_dashboard.py
```
Expected: `Dashboard written to docs/index.html (... bytes; N asset(s))`

If sell weights don't exist yet, it will print a warning but still build (spectrum_pos falls back gracefully). Run the backtest first if you want real sell scores:

```
python scripts/backtest.py
python scripts/score.py
python scripts/build_dashboard.py
```

- [ ] **Step 7: Open `docs/index.html` in a browser and verify**

Check against `docs/superpowers/kairos-full-page-reference.png`:
- Spectrum gauge visible with 5 equal zones
- Cursor positioned at spectrum_pos with floating score label
- Sell score box (left, red tint) and buy score box (right, green tint) below gauge
- Chips show spectrum_pos and spectrum_verdict
- Signal table, chart, methodology unchanged

- [ ] **Step 8: Commit**

```
git add templates/dashboard.html.j2
git commit -m "feat: replace zone strip with spectrum gauge in dashboard template"
```

---

## Task 9: Push Notifications — `scripts/send_push.py`

**Files:**
- Modify: `scripts/send_push.py`
- Test: `tests/test_push.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_push.py`:

```python
def test_format_digest_line_buy():
    from send_push import format_digest_line
    entry = {"display_name": "Bitcoin", "spectrum_pos": 69.7, "spectrum_verdict": "BUY", "delta_1d": 3.2}
    line = format_digest_line(entry)
    assert line == "Bitcoin 69.7 ↑ +3.2 — BUY"

def test_format_digest_line_take_profit_flag():
    from send_push import format_digest_line
    entry = {"display_name": "Ethereum", "spectrum_pos": 22.4, "spectrum_verdict": "TAKE PROFIT", "delta_1d": -4.1}
    line = format_digest_line(entry)
    assert "TAKE PROFIT ⚠️" in line

def test_format_digest_line_strong_buy_flag():
    from send_push import format_digest_line
    entry = {"display_name": "Bitcoin", "spectrum_pos": 83.1, "spectrum_verdict": "STRONG BUY", "delta_1d": 5.0}
    line = format_digest_line(entry)
    assert "STRONG BUY ✓" in line

def test_format_digest_line_sell_flag():
    from send_push import format_digest_line
    entry = {"display_name": "Bitcoin", "spectrum_pos": 30.0, "spectrum_verdict": "SELL", "delta_1d": -2.0}
    line = format_digest_line(entry)
    assert "SELL ⚠️" in line
```

- [ ] **Step 2: Run to confirm failures**

```
pytest tests/test_push.py -v -k "format_digest"
```
Expected: failures — `format_digest_line` uses old `composite` field.

- [ ] **Step 3: Update `format_digest_line` in `scripts/send_push.py`**

```python
def format_digest_line(entry: dict) -> str:
    """One line per ticker, e.g. 'Bitcoin 69.7 ↑ +3.2 — BUY'."""
    pos = entry["spectrum_pos"]
    verdict = entry["spectrum_verdict"]
    d = entry["delta_1d"]
    arrow = "↑" if d > 0.5 else "↓" if d < -0.5 else "→"
    flag = " ⚠️" if verdict in ("TAKE PROFIT", "SELL") else " ✓" if verdict == "STRONG BUY" else ""
    return f"{entry['display_name']} {pos:.1f} {arrow} {d:+.1f} — {verdict}{flag}"
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add scripts/send_push.py tests/test_push.py
git commit -m "feat: update push format to use spectrum_pos verdict with flags"
```

---

## Task 10: Generate Initial Sell Weights & End-to-End Smoke Test

**Files:**
- Create: `data/bitcoin_sell_weights.json` (generated, then committed)
- Create: `data/ethereum_sell_weights.json` (generated, then committed)

- [ ] **Step 1: Run the full pipeline**

```
python scripts/compute_signals.py
python scripts/backtest.py
python scripts/score.py
python scripts/build_dashboard.py
```

Expected output from backtest:
```
Backtesting Bitcoin (buy)...
  bitcoin: N good-entry days; weights written
Backtesting Bitcoin (sell)...
  bitcoin sell: M good-exit days; sell weights written
Backtesting Ethereum (buy)...
  ethereum: N good-entry days; weights written
Backtesting Ethereum (sell)...
  ethereum sell: M good-exit days; sell weights written
```

Expected output from score:
```
Scoring Bitcoin...
  bitcoin: XX.X/100 — BUY (sell: YY.Y, spectrum: ZZ.Z — BUY)
Scoring Ethereum...
  ethereum: XX.X/100 — HOLD (sell: YY.Y, spectrum: ZZ.Z — HOLD)
```

- [ ] **Step 2: Sanity-check sell weights JSON**

```
python -c "
import json
for asset in ['bitcoin', 'ethereum']:
    w = json.load(open(f'data/{asset}_sell_weights.json'))
    total = sum(s['weight'] for s in w['signals'].values())
    print(f'{asset}: {w[\"signals\"]}, total_weight={total:.4f}')
"
```
Expected: weights sum to ~1.0 for each asset; `good_exit_days` > 0.

- [ ] **Step 3: Open dashboard and verify spectrum**

Open `docs/index.html` in a browser. Verify:
- Spectrum pointer positioned correctly (BTC currently ~79, ETH lower)
- Sell score box shows a real value (not 0.0 unless market truly not overheated)
- Verdict at top matches spectrum zone
- Push format: run `python -c "import json; from scripts.send_push import format_digest_line; [print(format_digest_line(e)) for e in json.load(open('notify.json'))]"`

- [ ] **Step 4: Commit sell weights**

```
git add data/bitcoin_sell_weights.json data/ethereum_sell_weights.json
git commit -m "chore: add initial sell weights from good_exit backtest"
```

- [ ] **Step 5: Run full test suite**

```
pytest tests/ -v
```
Expected: all tests pass with no failures.

- [ ] **Step 6: Final commit**

```
git add -A
git status  # verify only expected files changed
git commit -m "feat: sell signal + spectrum UI complete — all tests passing"
```
