import json
import math
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_monthly_rsi,
    compute_pi_cycle_ratio,
    compute_puell_multiple,
    compute_fear_greed,
)

DATA_DIR = Path(__file__).parent.parent / "data"


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


from assets.registry import ASSETS


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
