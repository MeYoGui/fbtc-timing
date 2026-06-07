"""Bitcoin asset config."""
import requests
import numpy as np
import pandas as pd

from assets.base import AssetConfig, SignalSpec
from assets.signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_monthly_rsi,
    compute_pi_cycle_ratio,
    compute_puell_multiple,
    compute_fear_greed,
)

# ── data fetch (moved verbatim from scripts/fetch_data.py) ────────────────────

def _fetch_coinmetrics() -> pd.DataFrame:
    url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    params = {
        "assets": "btc",
        "metrics": "PriceUSD,CapMrktCurUSD,CapMVRVCur",
        "frequency": "1d",
        "start_time": "2010-01-01",
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
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df["price"] = pd.to_numeric(df["PriceUSD"], errors="coerce")
    df["market_cap"] = pd.to_numeric(df["CapMrktCurUSD"], errors="coerce")
    df["mvrv"] = pd.to_numeric(df["CapMVRVCur"], errors="coerce")
    return df[["date", "price", "market_cap", "mvrv"]].sort_values("date").reset_index(drop=True)


def _fetch_miner_revenue() -> pd.DataFrame:
    resp = requests.get(
        "https://api.blockchain.info/charts/miners-revenue",
        params={"timespan": "all", "format": "json", "sampled": "false"},
        timeout=60,
    )
    resp.raise_for_status()
    rows = resp.json()["values"]
    df = pd.DataFrame(rows).rename(columns={"x": "ts", "y": "miner_revenue"})
    df["date"] = pd.to_datetime(df["ts"], unit="s").astype("datetime64[ns]").dt.normalize()
    df["miner_revenue"] = pd.to_numeric(df["miner_revenue"], errors="coerce")
    return df[["date", "miner_revenue"]].sort_values("date").reset_index(drop=True)


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
    """Full Bitcoin history: price, market cap, MVRV, miner revenue, fear & greed."""
    cm = _fetch_coinmetrics()
    miner = _fetch_miner_revenue()
    fg = _fetch_fear_greed()
    return cm.merge(miner, on="date", how="left").merge(fg, on="date", how="left")


# ── good-entry definition (moved verbatim from scripts/backtest.py) ───────────

HALVING_DATES = [
    "2009-01-03", "2012-11-28", "2016-07-09",
    "2020-05-11", "2024-04-19", "2030-01-01",
]
HOLDING_DAYS = 548
MIN_RETURN = 0.50
CYCLE_BOTTOM_PCT = 0.40
CYCLE_TOP_PCT = 0.60     # price >= cycle_low + 60% of cycle range = top 40%
EXIT_HOLDING_DAYS = 548  # same 18-month window as good_entry
MIN_DRAWDOWN = 0.50      # forward price must fall >= 50% from this point


def _get_cycle_ranges(df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd
    halvings = pd.to_datetime(HALVING_DATES)
    df = df.copy()
    dates_ts = pd.to_datetime(df["date"])
    df["cycle"] = pd.cut(dates_ts, bins=halvings, labels=range(len(halvings) - 1), right=False)
    completed_cycles = list(range(len(halvings) - 2))
    cycle_stats = (
        df[df["cycle"].isin(completed_cycles)]
        .groupby("cycle")["price"]
        .agg(cycle_low="min", cycle_high="max")
    )
    df = df.join(cycle_stats, on="cycle")
    current = len(halvings) - 2
    mask = df["cycle"] == current
    df.loc[mask, "cycle_high"] = df.loc[mask, "price"].expanding().max()
    df.loc[mask, "cycle_low"] = df.loc[mask, "price"].expanding().min()
    df["cycle_range_40pct"] = df["cycle_low"] + CYCLE_BOTTOM_PCT * (df["cycle_high"] - df["cycle_low"])
    return df


def good_entry(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: halving-cycle-bottom + strong 18-month forward return."""
    import numpy as np
    enriched = _get_cycle_ranges(df)
    prices = enriched["price"].values
    thresholds = enriched["cycle_range_40pct"].values
    n = len(prices)
    good = np.zeros(n, dtype=bool)
    for i in range(n - HOLDING_DAYS):
        if prices[i] <= 0:
            continue
        fwd_return = (prices[i + HOLDING_DAYS] - prices[i]) / prices[i]
        if fwd_return >= MIN_RETURN and prices[i] <= thresholds[i]:
            good[i] = True
    return pd.Series(good, index=df.index)


def good_exit(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: price in top 40% of cycle range + >=50% forward drawdown."""
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


# ── config ────────────────────────────────────────────────────────────────────

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
    strong_buy_cutoff=85.0,
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
