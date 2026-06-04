import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import validate_composite as vc


def test_composite_series_weighted_average():
    signals_df = pd.DataFrame({"a": [100, 0], "b": [0, 100]})
    weights = {"signals": {"a": {"weight": 0.5}, "b": {"weight": 0.5}}}
    out = vc.composite_series(signals_df, weights, ["a", "b"])
    assert list(out.round(1)) == [50.0, 50.0]


def test_band_of_thresholds():
    assert vc.band_of(85) == "STRONG BUY"
    assert vc.band_of(75) == "INVEST"
    assert vc.band_of(60) == "CLOSE"
    assert vc.band_of(30) == "WAIT"
    assert vc.band_of(10) == "AVOID"


def test_forward_returns_shift():
    prices = pd.Series([100.0, 110.0, 120.0, 130.0])
    fwd = vc.forward_returns(prices, holding_days=2)
    # idx0: (120-100)/100 = 0.2 ; idx1: (130-110)/110 ~= 0.1818 ; idx2,3 NaN
    assert round(float(fwd.iloc[0]), 4) == 0.2
    assert pd.isna(fwd.iloc[2])


def test_invest_precision_counts():
    composite = pd.Series([80.0, 75.0, 60.0, 90.0])
    good = pd.Series([True, False, True, True])
    res = vc.invest_precision(composite, good, thresh=72.0)
    # invest days (>=72): idx0(T), idx1(F), idx3(T) -> tp=2, fp=1, fn=1
    assert res["tp"] == 2 and res["fp"] == 1 and res["fn"] == 1
    assert round(res["precision"], 4) == round(2 / 3, 4)


def test_timing_edge_positive_when_invest_days_outperform():
    composite = pd.Series([80.0, 40.0, 40.0, 40.0])
    fwd = pd.Series([1.0, 0.0, 0.0, 0.0])
    edge = vc.timing_edge(composite, fwd, thresh=72.0)
    assert edge["invest_mean_fwd_return"] == 1.0
    assert edge["buy_and_hold_mean_fwd_return"] == 0.25
    assert edge["edge"] == 0.75


def test_walk_forward_produces_some_out_of_sample_scores():
    # Synthetic asset spanning > warmup + window so at least one OOS step runs.
    n = vc.WARMUP_DAYS + vc.HOLDING_DAYS + 400
    dates = pd.date_range("2015-01-01", periods=n, freq="D")
    price_df = pd.DataFrame({"date": dates, "price": np.linspace(100.0, 500.0, n)})
    # Two score columns alternating buy/avoid so precision math is exercised.
    signals_df = pd.DataFrame({
        "date": dates,
        "s1": np.where(np.arange(n) % 2 == 0, 100, 0),
        "s2": np.where(np.arange(n) % 3 == 0, 100, 0),
    })

    class _Cfg:
        weight_overrides = None
        def good_entry(self, df):
            # cheap-and-rises proxy: first third are "good"
            g = np.zeros(len(df), dtype=bool)
            g[: len(df) // 3] = True
            return pd.Series(g, index=df.index)

    oos, good = vc.walk_forward(price_df, signals_df, _Cfg(), ["s1", "s2"])
    assert oos.notna().sum() > 0
    assert len(good) == len(oos)
