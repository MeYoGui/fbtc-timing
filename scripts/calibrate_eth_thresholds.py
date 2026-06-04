"""Reproducible calibration of ETH per-signal thresholds.

Reads bitcoin_signal_history.csv to derive BTC per-signal buy/avoid rates,
then maps each ETH signal to a target quantile of ETH's own distribution.

Run: python scripts/calibrate_eth_thresholds.py
Not part of daily CI — run manually when recalibration is needed.

Calibration rule
----------------
K = 2.0 (invest-side looseness multiplier — found by sweep to hit 3-5% SB)

Shared signals (MVRV, 200W-MA):
    invest_thresh = ETH quantile at min(btc_buy_rate * K, 0.45)
    avoid_thresh  = ETH quantile at 1 - btc_avoid_rate

ETH-native signals (ETH/BTC ratio, Mayer Multiple):
    anchored to BTC Puell rate (clean bottom-detector, ~5%)
    invest_thresh = ETH quantile at min(puell_buy_rate * K, 0.45)
    avoid_thresh  = ETH quantile at 1 - puell_avoid_rate

Bounded oscillators (Monthly RSI, Fear & Greed):
    domain-standard levels (40/70, 25/50) — percentile-matching produces nonsense.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"
K = 2.0   # invest-side looseness multiplier (sweep showed K=2.0 -> SB=3.5%)


def anchored_threshold(series: pd.Series, target_buy_rate: float) -> float:
    """Return the quantile of `series` at `target_buy_rate`, capped at 0.45.

    The 0.45 cap ensures invest_thresh never reaches the median — keeping the
    lower-is-invest convention intact regardless of K.
    """
    p = float(np.clip(target_buy_rate, 0.001, 0.45))
    return float(np.nanquantile(series.dropna(), p, method="higher"))


def _rate100(df: pd.DataFrame, key: str) -> float:
    return float((df[key].dropna() == 100).mean())


def _rate0(df: pd.DataFrame, key: str) -> float:
    return float((df[key].dropna() == 0).mean())


def _q(series: pd.Series, p: float) -> float:
    return float(np.nanquantile(series.dropna(), np.clip(p, 0.001, 0.999)))


def _score_series(raw: pd.Series, inv: float, av: float) -> pd.Series:
    s = pd.Series(50.0, index=raw.index)
    s[raw <= inv] = 100
    s[raw >= av] = 0
    s[raw.isna()] = np.nan
    return s


def compute_thresholds(btc: pd.DataFrame, eth: pd.DataFrame, k: float = K) -> dict:
    """Compute calibrated ETH thresholds using BTC buy/avoid rates as anchors."""
    def er(key):
        return eth[key + "_raw"]

    btc_buy = {k_: _rate100(btc, k_) for k_ in ["mvrv_zscore", "ma_200w", "puell"]}
    btc_av  = {k_: _rate0(btc, k_)   for k_ in ["mvrv_zscore", "ma_200w", "puell"]}

    anchored = {
        "mvrv_zscore":   (btc_buy["mvrv_zscore"], btc_av["mvrv_zscore"]),
        "ma_200w":       (btc_buy["ma_200w"],     btc_av["ma_200w"]),
        "eth_btc_ratio": (btc_buy["puell"],        btc_av["puell"]),
        "mayer_multiple":(btc_buy["puell"],        btc_av["puell"]),
    }
    thr = {}
    for sig, (buy_rate, av_rate) in anchored.items():
        inv_thr = anchored_threshold(er(sig), buy_rate * k)
        av_thr  = _q(er(sig), 1 - av_rate)
        if inv_thr >= av_thr:
            av_thr = inv_thr + abs(inv_thr) * 0.05 + 0.001
        thr[sig] = (round(inv_thr, 4), round(av_thr, 4))

    thr["monthly_rsi"] = (40.0, 70.0)
    thr["fear_greed"]  = (25.0, 50.0)
    return thr


def report(thr: dict, eth: pd.DataFrame, weights: dict) -> None:
    en = ["mvrv_zscore", "ma_200w", "monthly_rsi",
          "eth_btc_ratio", "mayer_multiple", "fear_greed"]
    wv = np.array([weights["signals"][k]["weight"] for k in en])
    wv /= wv.sum()

    scores = {}
    print("\nPer-signal thresholds and buy-rates:")
    for sig in en:
        inv, av = thr[sig]
        raw = eth[sig + "_raw"]
        s = _score_series(raw, inv, av)
        scores[sig] = s
        buy = 100 * (s == 100).mean()
        print(f"  {sig:16s}  invest={inv:8.4f}  avoid={av:8.4f}  buy={buy:.1f}%")

    M = np.vstack([scores[s].values for s in en]).T
    comp = np.where(np.isnan(M).any(1), np.nan, M @ wv)
    sb = 100 * (pd.Series(comp).dropna() >= 80).mean()
    print(f"\nComposite STRONG BUY: {sb:.1f}%  (target 3-5%)")
    print("\nPaste into assets/eth.py CONFIG:")
    for sig in en:
        inv, av = thr[sig]
        print(f'  SignalSpec("{sig}", ..., invest_thresh={inv}, avoid_thresh={av}, ...),')


def main():
    btc_path = DATA_DIR / "bitcoin_signal_history.csv"
    eth_path = DATA_DIR / "ethereum_signal_history.csv"
    wts_path = DATA_DIR / "ethereum_weights.json"
    if not all(p.exists() for p in (btc_path, eth_path, wts_path)):
        print("ERROR: run fetch_data + compute_signals + backtest first", file=sys.stderr)
        sys.exit(1)

    btc = pd.read_csv(btc_path)
    eth = pd.read_csv(eth_path)
    weights = json.loads(wts_path.read_text())

    print(f"Calibrating ETH thresholds (K={K})...")
    thr = compute_thresholds(btc, eth, K)
    report(thr, eth, weights)


if __name__ == "__main__":
    main()
