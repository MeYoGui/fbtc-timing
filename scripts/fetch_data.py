import requests
import pandas as pd
import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def fetch_coinmetrics_data() -> pd.DataFrame:
    """Fetch price, market cap, and MVRV ratio from CoinMetrics community API."""
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


def fetch_miner_revenue_history() -> pd.DataFrame:
    """Fetch all-time daily miner revenue from blockchain.info charts API."""
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


def fetch_fear_greed_history() -> pd.DataFrame:
    """Fetch all-time Fear & Greed Index from alternative.me."""
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


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Fetching price, market cap, MVRV from CoinMetrics...")
    cm_df = fetch_coinmetrics_data()
    print(f"  {len(cm_df)} rows")

    print("Fetching miner revenue from blockchain.info...")
    miner_df = fetch_miner_revenue_history()
    print(f"  {len(miner_df)} rows")

    print("Fetching Fear & Greed history from alternative.me...")
    fg_df = fetch_fear_greed_history()
    print(f"  {len(fg_df)} rows")

    merged = (
        cm_df
        .merge(miner_df, on="date", how="left")
        .merge(fg_df, on="date", how="left")
    )
    merged.to_csv(DATA_DIR / "btc_history.csv", index=False)
    print(f"Saved {len(merged)} rows to data/btc_history.csv")


if __name__ == "__main__":
    main()
