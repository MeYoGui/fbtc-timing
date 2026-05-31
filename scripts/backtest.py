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


# MVRV Z-Score is a fundamental valuation metric with perfect historical precision.
# We apply a 2× multiplier so it anchors the composite score to on-chain value,
# preventing high-sentiment / low-precision signals from dominating.
MVRV_WEIGHT_MULTIPLIER = 2.0


def derive_weights(stats: dict) -> dict:
    # Weight by precision (not F1) so rare, accurate signals outrank noisy ones.
    raw = {s: stats[s]["precision"] for s in SIGNAL_NAMES}
    raw["mvrv_zscore"] = raw["mvrv_zscore"] * MVRV_WEIGHT_MULTIPLIER
    total = sum(raw.values())
    if total == 0:
        equal = round(1.0 / len(SIGNAL_NAMES), 4)
        return {s: equal for s in SIGNAL_NAMES}
    return {s: round(raw[s] / total, 4) for s in SIGNAL_NAMES}


def main():
    price_df = pd.read_csv(DATA_DIR / "btc_history.csv")
    price_df["date"] = pd.to_datetime(price_df["date"])

    signals_df = pd.read_csv(DATA_DIR / "signal_history.csv")
    signals_df["date"] = pd.to_datetime(signals_df["date"])

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
