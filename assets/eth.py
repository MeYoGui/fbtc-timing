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

# ── data fetch (keyless: CoinMetrics community + alternative.me) ───────────────

def _pivot_coinmetrics(records: list) -> pd.DataFrame:
    """Pivot raw multi-asset CoinMetrics records into one row per date with
    ETH price/market cap/MVRV plus BTC price (for the ETH/BTC ratio signal)."""
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df["PriceUSD"] = pd.to_numeric(df["PriceUSD"], errors="coerce")
    df["CapMrktCurUSD"] = pd.to_numeric(df["CapMrktCurUSD"], errors="coerce")
    df["CapMVRVCur"] = pd.to_numeric(df["CapMVRVCur"], errors="coerce")

    eth_rows = df[df["asset"] == "eth"].set_index("date")
    btc_rows = df[df["asset"] == "btc"].set_index("date")

    out = pd.DataFrame({
        "price": eth_rows["PriceUSD"],
        "market_cap": eth_rows["CapMrktCurUSD"],
        "mvrv": eth_rows["CapMVRVCur"],
        "btc_price": btc_rows["PriceUSD"],
    })
    out = out[out["price"].notna()]   # keep only ETH-anchored dates (drop BTC-only days)
    return out.reset_index().sort_values("date").reset_index(drop=True)


def _fetch_coinmetrics() -> pd.DataFrame:
    url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    params = {
        "assets": "eth,btc",
        "metrics": "PriceUSD,CapMrktCurUSD,CapMVRVCur",
        "frequency": "1d",
        "start_time": "2015-01-01",
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
    return _pivot_coinmetrics(records)


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
    """Full Ethereum history: price, market cap, MVRV, BTC price, fear & greed."""
    cm = _fetch_coinmetrics()
    fg = _fetch_fear_greed()
    return cm.merge(fg, on="date", how="left")


# ── good-entry definition ─────────────────────────────────────────────────────
# ETH has no halving cycle, so "good entry" = deep drawdown from the running
# all-time high AND a strong 18-month forward return. Both tunable.
DRAWDOWN = 0.55       # drawdown from running ATH must be >= 55% (price <= ATH * 0.45)
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


# ── config ────────────────────────────────────────────────────────────────────

CONFIG = AssetConfig(
    id="ethereum",
    display_name="Ethereum",
    short_label="Ξ Ethereum",
    accent_color="#627eea",
    price_unit="$",
    fetch=fetch,
    good_entry=good_entry,
    weight_overrides=None,   # start neutral; calibration/validation decides any boost
    signals=[
        # Calibrated 2026-06-04: BTC-anchored per-signal quantiles (K=2.0 looseness)
        # -> composite STRONG BUY ~3.5% (target 3-5%). See scripts/calibrate_eth_thresholds.py.
        SignalSpec("mvrv_zscore", "MVRV Z-Score", compute_mvrv_zscore,
                   invest_thresh=-1.3209, avoid_thresh=3.5901,
                   range_lo=-3.0, range_hi=5.0, fmt="{:.1f}"),
        SignalSpec("ma_200w", "200-Week MA", compute_200w_ma_ratio,
                   invest_thresh=0.8669, avoid_thresh=0.9567,
                   range_lo=0.5, range_hi=3.0, fmt="{:.1f}×"),
        SignalSpec("monthly_rsi", "Monthly RSI", compute_monthly_rsi,
                   invest_thresh=40.0, avoid_thresh=70.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
        SignalSpec("eth_btc_ratio", "ETH/BTC Ratio", compute_eth_btc_ratio_z,
                   invest_thresh=-1.0799, avoid_thresh=0.8833,
                   range_lo=-2.0, range_hi=3.0, fmt="{:.1f}"),
        SignalSpec("mayer_multiple", "Mayer Multiple", compute_mayer_multiple,
                   invest_thresh=0.6451, avoid_thresh=1.4605,
                   range_lo=0.0, range_hi=4.0, fmt="{:.1f}×"),
        SignalSpec("fear_greed", "Fear & Greed", compute_fear_greed,
                   invest_thresh=25.0, avoid_thresh=50.0,
                   range_lo=0.0, range_hi=100.0, fmt="{:.0f}"),
    ],
)
