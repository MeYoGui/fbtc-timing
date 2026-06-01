import json
import math
import numpy as np
import pandas as pd
from pathlib import Path

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

    # MVRV Z-Score: z-score of the MVRV ratio; thresholds calibrated to ratio space
    out["mvrv_zscore_raw"] = compute_mvrv_zscore(df)
    out["mvrv_zscore"] = score_series(out["mvrv_zscore_raw"], -0.5, 1.5)

    out["ma_200w_ratio_raw"] = compute_200w_ma_ratio(df)
    out["ma_200w"] = score_series(out["ma_200w_ratio_raw"], 1.0, 1.2)

    rsi = compute_monthly_rsi(df)
    out["monthly_rsi_raw"] = rsi
    out["monthly_rsi"] = pd.Series(rsi, index=df.index).apply(
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
    df["date"] = pd.to_datetime(df["date"])

    signals = compute_all_signals(df)
    signals.to_csv(DATA_DIR / "signal_history.csv", index=False)

    def _last_valid(raw_col: str, score_col: str) -> tuple:
        """Return (raw, score) from the last row where raw is not NaN.
        Falls back to (NaN, 50) if the column is entirely NaN.
        Handles API lag: some sources (MVRV, Puell) publish 1-2 days late."""
        valid = signals[raw_col].notna()
        if not valid.any():
            return float("nan"), 50
        row = signals[valid].iloc[-1]
        return row[raw_col], int(row[score_col])

    latest = signals.iloc[-1]
    mvrv_raw,    mvrv_score    = _last_valid("mvrv_zscore_raw",    "mvrv_zscore")
    ma200w_raw,  ma200w_score  = _last_valid("ma_200w_ratio_raw",  "ma_200w")
    rsi_raw,     rsi_score     = _last_valid("monthly_rsi_raw",    "monthly_rsi")
    pi_raw,      pi_score      = _last_valid("pi_cycle_ratio_raw", "pi_cycle")
    puell_raw,   puell_score   = _last_valid("puell_raw",          "puell")
    fg_raw,      fg_score      = _last_valid("fear_greed_raw",     "fear_greed")

    current = {
        "date": str(latest["date"].date()),
        "signals": {
            "mvrv_zscore": {"raw": _sanitize_float(mvrv_raw),   "score": mvrv_score},
            "ma_200w":     {"raw": _sanitize_float(ma200w_raw), "score": ma200w_score},
            "monthly_rsi": {"raw": _sanitize_float(rsi_raw),    "score": rsi_score},
            "pi_cycle":    {"raw": _sanitize_float(pi_raw),     "score": pi_score},
            "puell":       {"raw": _sanitize_float(puell_raw),  "score": puell_score},
            "fear_greed":  {"raw": _sanitize_float(fg_raw),     "score": fg_score},
        },
    }
    (DATA_DIR / "current_signals.json").write_text(json.dumps(current, indent=2))
    print(f"Signals computed for {current['date']}")
    for name, data in current["signals"].items():
        raw = data["raw"]
        raw_str = f"{raw:.3f}" if pd.notna(raw) else "NaN"
        print(f"  {name}: raw={raw_str}  score={data['score']}")


if __name__ == "__main__":
    main()
