"""Validate the COMPOSITE score (not just per-signal weights) over full history.

Produces, per asset:
  - in-sample report: forward-return by verdict band, INVEST precision, timing edge
  - walk-forward out-of-sample: weights derived only on past data, scored on later data
Writes data/{id}_validation.json and prints a PASS/REVIEW gate line.
Run manually / via workflow dispatch — NOT part of the daily CI job.

Caveat: the walk-forward derives WEIGHTS only from past data (causal), but the
signal FEATURES it reads from {id}_signal_history.csv were precomputed once over
full history (e.g. z-score mean/std span the whole series). So OOS metrics carry
a mild optimistic bias from feature-level look-ahead and should be read as an
upper-ish bound, not a pure held-out estimate.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from assets.registry import ASSETS
from backtest import compute_signal_stats, derive_weights

DATA_DIR = Path(__file__).parent.parent / "data"

HOLDING_DAYS = 548
INVEST_THRESHOLD = 60.0
WARMUP_DAYS = 365 * 4            # 200-week MA needs ~4 years before signals exist
STEP_DAYS = 90                   # walk-forward out-of-sample window size
BANDS = [("STRONG BUY", 80), ("BUY", 60), ("HOLD", 40), ("WAIT", 20), ("AVOID", 0)]


def composite_series(signals_df: pd.DataFrame, weights: dict, signal_names: list) -> pd.Series:
    w = np.array([weights["signals"][s]["weight"] for s in signal_names])
    total = w.sum()
    if total == 0:
        return pd.Series(np.zeros(len(signals_df)), index=signals_df.index)
    return pd.Series(signals_df[signal_names].values @ w / total, index=signals_df.index)


def forward_returns(prices: pd.Series, holding_days: int = HOLDING_DAYS) -> pd.Series:
    fwd = prices.shift(-holding_days)
    return (fwd - prices) / prices


def band_of(score: float) -> str:
    for name, lo in BANDS:
        if score >= lo:
            return name
    return "AVOID"


def band_report(composite: pd.Series, fwd: pd.Series) -> dict:
    df = pd.DataFrame({"composite": composite.values, "fwd": fwd.values}).dropna()
    df["band"] = df["composite"].apply(band_of)
    report = {}
    for name, _ in BANDS:
        sub = df[df["band"] == name]["fwd"]
        report[name] = {
            "days": int(len(sub)),
            "mean_fwd_return": round(float(sub.mean()), 4) if len(sub) else None,
            "median_fwd_return": round(float(sub.median()), 4) if len(sub) else None,
            "pct_positive": round(float((sub > 0).mean()), 4) if len(sub) else None,
        }
    return report


def invest_precision(composite: pd.Series, good_entries: pd.Series, thresh: float = INVEST_THRESHOLD) -> dict:
    # Positional alignment after reset_index requires equal length; assert it so a
    # future refactor passing a filtered subset fails loudly instead of silently.
    assert len(composite) == len(good_entries), "composite/good_entries length mismatch"
    invest = (composite >= thresh).reset_index(drop=True)
    good = good_entries.reset_index(drop=True).astype(bool)
    tp = int((invest & good).sum())
    fp = int((invest & ~good).sum())
    fn = int((~invest & good).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


def timing_edge(composite: pd.Series, fwd: pd.Series, thresh: float = INVEST_THRESHOLD) -> dict:
    df = pd.DataFrame({"c": composite.values, "fwd": fwd.values}).dropna()
    invest_days = df[df["c"] >= thresh]["fwd"]
    all_days = df["fwd"]
    invest_mean = float(invest_days.mean()) if len(invest_days) else None
    hold_mean = float(all_days.mean()) if len(all_days) else None
    edge = round(invest_mean - hold_mean, 4) if invest_mean is not None and hold_mean is not None else None
    return {
        "invest_mean_fwd_return": round(invest_mean, 4) if invest_mean is not None else None,
        "buy_and_hold_mean_fwd_return": round(hold_mean, 4) if hold_mean is not None else None,
        "edge": edge,
        "invest_days": int(len(invest_days)),
    }


def _good_aligned_to(merged: pd.DataFrame, price_df: pd.DataFrame, good: pd.Series) -> pd.Series:
    """Align a good-entry Series (indexed like price_df) to merged rows by date."""
    by_date = pd.Series(good.values, index=pd.to_datetime(price_df["date"]).values)
    aligned = by_date.reindex(pd.to_datetime(merged["date"]).values)
    return pd.Series(aligned.values, index=merged.index).fillna(False).astype(bool)


def walk_forward(price_df: pd.DataFrame, signals_df: pd.DataFrame, cfg, signal_names: list,
                 step_days: int = STEP_DAYS) -> tuple:
    """Expanding-window OOS: at each step derive weights from data strictly older
    than the forward window, then score the next `step_days` out-of-sample.

    Causality: at decision time t we score window [t, t+step). Training uses rows
    [0, cutoff) with cutoff = t - HOLDING_DAYS, so the newest training label (row
    cutoff-1) depends on price[(cutoff-1)+HOLDING_DAYS] = price[t-1] — strictly
    before t. No future price leaks into the weights used to score from t onward."""
    merged = price_df[["date", "price"]].merge(signals_df, on="date", how="inner").reset_index(drop=True)
    good = _good_aligned_to(merged, price_df, cfg.good_entry(price_df))

    n = len(merged)
    oos = pd.Series(np.nan, index=merged.index)
    t = WARMUP_DAYS
    while t < n - HOLDING_DAYS:
        cutoff = t - HOLDING_DAYS                      # labels knowable only up to here
        if cutoff >= WARMUP_DAYS // 2:
            train = merged.iloc[:cutoff]
            train_good = good.iloc[:cutoff]
            stats = compute_signal_stats(train, train_good, signal_names)
            weights = derive_weights(stats, signal_names, getattr(cfg, "weight_overrides", None))
            # Slim weights dict in the shape composite_series expects ({"signals":
            # {key: {"weight": w}}}); stats fields aren't needed for OOS scoring.
            wdict = {"signals": {s: {"weight": weights[s]} for s in signal_names}}
            window = merged.iloc[t:t + step_days]
            oos.iloc[t:t + step_days] = composite_series(window, wdict, signal_names).values
        t += step_days
    return oos, good


def validate_asset(cfg) -> dict:
    hist = DATA_DIR / f"{cfg.id}_history.csv"
    sig = DATA_DIR / f"{cfg.id}_signal_history.csv"
    wts = DATA_DIR / f"{cfg.id}_weights.json"
    if not all(p.exists() for p in (hist, sig, wts)):
        print(f"  skip {cfg.id}: missing history/signal/weights files", file=sys.stderr)
        return None

    price_df = pd.read_csv(hist); price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(sig); signals_df["date"] = pd.to_datetime(signals_df["date"])
    weights = json.loads(wts.read_text())
    signal_names = [s.key for s in cfg.signals]

    merged = price_df[["date", "price"]].merge(signals_df, on="date", how="inner").reset_index(drop=True)
    comp = composite_series(merged, weights, signal_names)
    fwd = forward_returns(merged["price"])
    good = _good_aligned_to(merged, price_df, cfg.good_entry(price_df))

    in_sample = {
        "bands": band_report(comp, fwd),
        "invest_precision": invest_precision(comp, good),
        "timing_edge": timing_edge(comp, fwd),
    }
    oos_comp, oos_good = walk_forward(price_df, signals_df, cfg, signal_names)
    # Restrict OOS precision/recall to the actually-scored rows: warm-up and the
    # trailing gap have no composite, and counting them as non-invest would inflate
    # false negatives and understate recall. (Precision is unaffected either way.)
    scored = oos_comp.notna()
    out_of_sample = {
        "bands": band_report(oos_comp, fwd),
        "invest_precision": invest_precision(oos_comp[scored], oos_good[scored]),
        "timing_edge": timing_edge(oos_comp, fwd),
    }

    report = {"asset": cfg.id, "in_sample": in_sample, "out_of_sample": out_of_sample}
    (DATA_DIR / f"{cfg.id}_validation.json").write_text(json.dumps(report, indent=2))

    oos_edge = out_of_sample["timing_edge"]["edge"]
    oos_prec = out_of_sample["invest_precision"]["precision"]
    gate = "PASS" if (oos_edge is not None and oos_edge > 0 and oos_prec > 0) else "REVIEW"
    print(f"  {cfg.id}: OOS edge={oos_edge} precision={oos_prec} -> {gate}")
    return report


def main():
    for cfg in ASSETS:
        print(f"Validating composite for {cfg.display_name}...")
        validate_asset(cfg)


if __name__ == "__main__":
    main()
