"""Ethereum asset config."""
import numpy as np
import pandas as pd
import requests

from assets.base import AssetConfig, SignalSpec
from assets.signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_monthly_rsi,
    compute_eth_btc_ratio_z,
    compute_mayer_multiple,
    compute_fear_greed,
)

# ── good-entry definition ─────────────────────────────────────────────────────
# ETH has no halving cycle, so "good entry" = deep drawdown from the running
# all-time high AND a strong 18-month forward return. Both tunable.
DRAWDOWN = 0.55       # price must be >= 55% below its running ATH
HOLDING_DAYS = 548    # 18 months forward window (same as Bitcoin)
MIN_RETURN = 0.50     # >= 50% forward return to count as a good entry


def good_entry(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: deep drawdown from running ATH + strong forward return."""
    prices = df["price"].values
    running_ath = df["price"].expanding().max().values   # causal: no look-ahead
    thresholds = running_ath * (1.0 - DRAWDOWN)
    n = len(prices)
    good = np.zeros(n, dtype=bool)
    for i in range(n - HOLDING_DAYS):
        if prices[i] <= 0:
            continue
        fwd_return = (prices[i + HOLDING_DAYS] - prices[i]) / prices[i]
        if fwd_return >= MIN_RETURN and prices[i] <= thresholds[i]:
            good[i] = True
    return pd.Series(good, index=df.index)
