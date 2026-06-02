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
