import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from backtest import label_good_entries, compute_signal_stats, derive_weights, SIGNAL_NAMES


def make_price_df(prices, start="2013-01-01"):
    dates = pd.date_range(start, periods=len(prices))
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "cycle_range_40pct": [p * 1.5 for p in prices],  # all entries qualify
    })


def make_signals_df(n, buy_days=None):
    df = pd.DataFrame({"date": pd.date_range("2013-01-01", periods=n)})
    for name in SIGNAL_NAMES:
        df[name] = 50  # neutral by default
    if buy_days:
        for day in buy_days:
            for name in SIGNAL_NAMES:
                df.loc[day, name] = 100
    return df


def test_label_good_entries_returns_false_when_return_below_threshold():
    prices = [100.0] * 2000
    df = make_price_df(prices)
    result = label_good_entries(df)
    assert result.sum() == 0


def test_label_good_entries_returns_true_when_return_exceeds_threshold():
    n = 1200
    prices = [100.0] * 548 + [200.0] * (n - 548)
    df = make_price_df(prices)
    result = label_good_entries(df)
    assert result.iloc[0] == True


def test_derive_weights_sum_to_one():
    stats = {name: {"precision": 0.5} for name in SIGNAL_NAMES}
    weights = derive_weights(stats)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_derive_weights_higher_precision_gets_higher_weight():
    stats = {name: {"precision": 0.1} for name in SIGNAL_NAMES}
    stats["ma_200w"]["precision"] = 0.9
    weights = derive_weights(stats)
    assert weights["ma_200w"] > weights["pi_cycle"]


def test_derive_weights_mvrv_multiplier_applied():
    # mvrv_zscore gets 2× multiplier, so equal-precision inputs give mvrv a higher weight
    stats = {name: {"precision": 0.5} for name in SIGNAL_NAMES}
    weights = derive_weights(stats)
    assert weights["mvrv_zscore"] > weights["ma_200w"]


def test_compute_signal_stats_perfect_signal():
    n = 2000
    signals_df = make_signals_df(n, buy_days=list(range(100, 200)))
    good_entries = pd.Series([False] * n)
    good_entries.iloc[100:200] = True
    stats = compute_signal_stats(signals_df, good_entries)
    assert stats["mvrv_zscore"]["precision"] == pytest.approx(1.0)
    assert stats["mvrv_zscore"]["recall"] == pytest.approx(1.0)
