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
    """Weight by precision; apply optional per-signal multipliers (e.g. MVRV 2x)."""
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
