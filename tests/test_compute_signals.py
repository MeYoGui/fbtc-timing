import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from compute_signals import (
    compute_mvrv_zscore,
    compute_200w_ma_ratio,
    compute_puell_multiple,
    compute_pi_cycle_ratio,
    signal_score,
)


def make_df(n=1500, price=50000.0, mvrv=2.0, miner_revenue=1e6):
    dates = pd.date_range("2019-01-01", periods=n)
    prices = np.full(n, price)
    mcaps = prices * 19_000_000
    mvrv_series = np.full(n, mvrv)
    revenues = np.full(n, miner_revenue)
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "market_cap": mcaps,
        "mvrv": mvrv_series,
        "miner_revenue": revenues,
        "fear_greed": np.full(n, 50),
    })


def test_signal_score_buy_zone():
    assert signal_score(0.5, buy_threshold=1.0, avoid_threshold=3.0) == 100


def test_signal_score_avoid_zone():
    assert signal_score(4.0, buy_threshold=1.0, avoid_threshold=3.0) == 0


def test_signal_score_neutral_zone():
    assert signal_score(2.0, buy_threshold=1.0, avoid_threshold=3.0) == 50


def test_mvrv_zscore_constant_returns_zero():
    df = make_df(n=500, mvrv=2.0)
    zscore = compute_mvrv_zscore(df)
    # constant mvrv → std = 0 → zscore = 0
    assert zscore.dropna().abs().max() == pytest.approx(0.0, abs=1e-9)


def test_200w_ma_ratio_equals_one_when_price_is_constant():
    df = make_df(n=1500)
    ratio = compute_200w_ma_ratio(df)
    valid = ratio.dropna()
    assert valid.iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_puell_multiple_equals_one_when_revenue_is_constant():
    df = make_df(n=800, miner_revenue=1e6)
    puell = compute_puell_multiple(df)
    valid = puell.dropna()
    assert valid.iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_pi_cycle_ratio_constant_price():
    df = make_df(n=800)
    ratio = compute_pi_cycle_ratio(df)
    valid = ratio.dropna()
    # 111DMA / (2 × 350DMA) = price / (2 × price) = 0.5 when price is constant
    assert valid.iloc[-1] == pytest.approx(0.5, abs=1e-6)
