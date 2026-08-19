import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.signals import compute_mayer_multiple, compute_eth_btc_ratio_z


def test_mayer_multiple_is_one_at_its_200d_average():
    df = pd.DataFrame({"price": [100.0] * 200})
    result = compute_mayer_multiple(df)
    assert result.iloc[-1] == 1.0          # 100 / 200d-MA(100) = 1.0
    assert pd.isna(result.iloc[0])         # fewer than 200 periods -> NaN


def test_mayer_multiple_above_one_when_price_over_average():
    prices = [100.0] * 199 + [200.0]
    df = pd.DataFrame({"price": prices})
    result = compute_mayer_multiple(df)
    # MA of last 200 = (199*100 + 200)/200 = 100.5 ; 200/100.5 ~= 1.9900
    assert round(float(result.iloc[-1]), 4) == 1.99


def test_eth_btc_ratio_z_centers_and_scales():
    df = pd.DataFrame({"price": [1.0, 2.0, 3.0], "btc_price": [1.0, 1.0, 1.0]})
    z = compute_eth_btc_ratio_z(df)
    # ratio = [1,2,3]; mean=2, std(ddof=1)=1 -> z = [-1, 0, 1]
    assert list(np.round(z.values, 4)) == [-1.0, 0.0, 1.0]


def test_eth_btc_ratio_z_handles_zero_variance():
    df = pd.DataFrame({"price": [2.0, 2.0], "btc_price": [1.0, 1.0]})
    z = compute_eth_btc_ratio_z(df)
    assert list(z.values) == [0.0, 0.0]


def test_eth_btc_ratio_z_handles_nonfinite_ratio():
    # A zero in btc_price makes the ratio non-finite -> std is NaN.
    # The guard should still return all zeros, not all NaN.
    df = pd.DataFrame({"price": [1.0, 2.0, 3.0], "btc_price": [1.0, 0.0, 1.0]})
    z = compute_eth_btc_ratio_z(df)
    assert list(z.values) == [0.0, 0.0, 0.0]


def test_expanding_zscore_is_truncation_invariant():
    """Value at row i must not change when future rows are removed — the
    property the full-history z-score violates."""
    from assets.signals import compute_mvrv_zscore_expanding
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"mvrv": rng.normal(2.0, 0.8, size=1200)})
    full = compute_mvrv_zscore_expanding(df, min_periods=100)
    trunc = compute_mvrv_zscore_expanding(df.iloc[:600].copy(), min_periods=100)
    pd.testing.assert_series_equal(full.iloc[:600], trunc)


def test_expanding_zscore_warmup_is_nan():
    from assets.signals import compute_mvrv_zscore_expanding
    df = pd.DataFrame({"mvrv": np.linspace(1.0, 3.0, 200)})
    z = compute_mvrv_zscore_expanding(df, min_periods=100)
    assert z.iloc[:99].isna().all()
    assert z.iloc[99:].notna().all()


def test_expanding_zscore_known_value():
    from assets.signals import compute_mvrv_zscore_expanding
    df = pd.DataFrame({"mvrv": [1.0, 2.0, 3.0, 6.0]})
    z = compute_mvrv_zscore_expanding(df, min_periods=3)
    # at row 3: history [1,2,3,6] -> mean 3.0, std (sample) ~2.1602
    assert z.iloc[3] == pytest.approx((6.0 - 3.0) / 2.160246899469287)
