import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets import eth


def test_good_entry_flags_deep_drawdown_with_strong_recovery():
    # 51 days at ATH=100, then a 60%-drawdown day (40 <= 45 threshold),
    # then a 548-day ramp up to 200 so the 18-month forward return is huge.
    prices = [100.0] * 51 + [40.0] + list(np.linspace(41.0, 200.0, 548))
    df = pd.DataFrame({"price": prices})
    assert len(df) == 600

    good = eth.good_entry(df)

    assert bool(good.iloc[51]) is True          # the drawdown day qualifies
    assert int(good.sum()) == 1                  # nothing else does
    assert good.dtype == bool


def test_good_entry_rejects_shallow_drawdown():
    # Price only 20% below ATH (80 > 45 threshold) -> never a good entry.
    prices = [100.0] * 51 + [80.0] + list(np.linspace(81.0, 300.0, 548))
    df = pd.DataFrame({"price": prices})
    good = eth.good_entry(df)
    assert int(good.sum()) == 0


def test_good_entry_threshold_located_near_45pct_of_ath():
    # Threshold = ATH*(1-0.55) ~= 45 (ATH=100). A price just inside (44, a 56%
    # drawdown) qualifies; just outside (46, a 54% drawdown) is rejected. Pins
    # the threshold's location and direction without relying on exact-float
    # equality (1-0.55 is 0.4499... so testing price==45 would be fragile).
    base = [100.0] * 51
    ramp = list(np.linspace(0.0, 160.0, 548))  # guarantees a strong forward return
    inside = eth.good_entry(pd.DataFrame({"price": base + [44.0] + [r + 44.0 for r in ramp]}))
    outside = eth.good_entry(pd.DataFrame({"price": base + [46.0] + [r + 46.0 for r in ramp]}))
    assert bool(inside.iloc[51]) is True
    assert bool(outside.iloc[51]) is False


def test_pivot_coinmetrics_joins_eth_and_btc_by_date():
    records = [
        {"asset": "eth", "time": "2020-01-01T00:00:00.000000000Z",
         "PriceUSD": "130.0", "CapMrktCurUSD": "14000000000", "CapMVRVCur": "1.5"},
        {"asset": "btc", "time": "2020-01-01T00:00:00.000000000Z",
         "PriceUSD": "7200.0", "CapMrktCurUSD": "130000000000", "CapMVRVCur": "2.0"},
        {"asset": "eth", "time": "2020-01-02T00:00:00.000000000Z",
         "PriceUSD": "135.0", "CapMrktCurUSD": "14500000000", "CapMVRVCur": "1.6"},
        {"asset": "btc", "time": "2020-01-02T00:00:00.000000000Z",
         "PriceUSD": "6900.0", "CapMrktCurUSD": "125000000000", "CapMVRVCur": "1.9"},
    ]
    df = eth._pivot_coinmetrics(records)

    assert list(df.columns) == ["date", "price", "market_cap", "mvrv", "btc_price"]
    assert len(df) == 2
    first = df.iloc[0]
    assert first["price"] == 130.0
    assert first["btc_price"] == 7200.0
    assert first["mvrv"] == 1.5
    assert df["date"].is_monotonic_increasing
