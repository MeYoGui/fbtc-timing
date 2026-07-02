import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from experiment import edge_at_coverage, edge_by_cycle, precision_at_coverage


def test_precision_at_coverage_counts_good_entries_in_top_days():
    # top 50% of 4 scored days = 2 days (composite 100 and 90); one is a good entry
    oos = pd.Series([100.0, 90.0, 10.0, 20.0])
    good = pd.Series([True, False, True, False])
    out = precision_at_coverage(oos, good, pct=0.50)
    assert out["coverage_days"] == 2
    assert out["precision"] == pytest.approx(0.5)


def test_precision_at_coverage_ignores_nan_composite_rows():
    oos = pd.Series([np.nan, 100.0, 50.0])
    good = pd.Series([True, True, False])
    out = precision_at_coverage(oos, good, pct=0.50)
    assert out["coverage_days"] == 1        # 2 scored rows -> top 50% = 1
    assert out["precision"] == pytest.approx(1.0)


def test_edge_at_coverage_picks_top_composite_days():
    # 10 days; composite ranks day 9 highest; its fwd return is 1.0 vs mean 0.1
    oos = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
    fwd = pd.Series([0.0] * 9 + [1.0])
    out = edge_at_coverage(oos, fwd, pct=0.10)
    assert out["coverage_days"] == 1
    assert out["top_mean_fwd"] == 1.0
    assert out["edge"] == pytest.approx(1.0 - 0.1)


def test_edge_at_coverage_ignores_nan_rows():
    oos = pd.Series([np.nan, np.nan, 50.0, 100.0])
    fwd = pd.Series([9.9, 9.9, 0.0, 1.0])
    out = edge_at_coverage(oos, fwd, pct=0.50)
    # only 2 scored rows; top 50% = 1 day = the composite-100 day
    assert out["coverage_days"] == 1
    assert out["top_mean_fwd"] == 1.0


def test_edge_by_cycle_buckets_by_halving():
    dates = pd.Series(pd.to_datetime(["2013-06-01", "2013-07-01",
                                      "2017-06-01", "2017-07-01"]))
    oos = pd.Series([100.0, 0.0, 100.0, 0.0])
    fwd = pd.Series([0.5, 0.1, 0.2, 0.0])
    out = edge_by_cycle(oos, fwd, dates, pct=0.50)
    # one bucket per halving cycle present in the data
    assert set(out) == {"2012-11-28", "2016-07-09"}
    assert out["2012-11-28"]["edge"] == pytest.approx(0.5 - 0.3)
