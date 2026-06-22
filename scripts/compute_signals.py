import json
import math
import pandas as pd
from datetime import date
from pathlib import Path
from typing import Optional
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.base import AssetConfig
from assets.signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_monthly_rsi,
    compute_pi_cycle_ratio,
    compute_puell_multiple,
    compute_fear_greed,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def last_change_date(dates: pd.Series, raw: pd.Series) -> Optional[date]:
    """Date the non-NaN raw value last changed (last day it differed from the
    previous kept value). A single distinct value -> its first date. Empty -> None.

    One rule covers all cadence cases: a monthly signal forward-filled to daily
    lands on its last month boundary; an API-lagged signal (trailing NaN) lands
    on its last real datapoint; a normally-moving daily signal lands on today."""
    s = pd.Series(raw).reset_index(drop=True)
    d = pd.Series(pd.to_datetime(dates)).reset_index(drop=True)
    mask = s.notna()
    s = s[mask].reset_index(drop=True)
    d = d[mask].reset_index(drop=True)
    if len(s) == 0:
        return None
    changed = s.ne(s.shift())          # index 0 is always True (shift -> NaN)
    last_idx = changed[changed].index[-1]
    return d.iloc[last_idx].date()


def _sanitize_float(v):
    """Convert NaN/inf to None so json.dumps produces valid JSON null."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else f
    except (TypeError, ValueError):
        return None


SIGNAL_NAMES = ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]


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


def sell_signal_score(value: float, sell_thresh: float) -> int:
    """100 if raw value strictly exceeds sell_thresh, else 0."""
    return 100 if value > sell_thresh else 0


from assets.registry import ASSETS


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
        """Return (raw, score, sell_score) from the last row where raw is not NaN.
        Falls back to (NaN, 50, 0) if the column is entirely NaN.
        Handles API lag: some sources (MVRV, Puell) publish 1-2 days late."""
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
        as_of = last_change_date(signals["date"], signals[f"{spec.key}_raw"])
        current["signals"][spec.key] = {
            "raw": _sanitize_float(raw),
            "score": score,
            "sell_score": sell_score,
            "as_of": as_of.isoformat() if as_of is not None else None,
        }

    (DATA_DIR / f"{cfg.id}_current_signals.json").write_text(json.dumps(current, indent=2))
    print(f"  {cfg.id}: signals for {current['date']}")


def main():
    for cfg in ASSETS:
        print(f"Computing signals for {cfg.display_name}...")
        _process_asset(cfg)


if __name__ == "__main__":
    main()
