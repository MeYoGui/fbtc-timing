import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_monthly_rsi_cadence_is_monthly_others_daily():
    from assets.bitcoin import CONFIG as BTC
    from assets.eth import CONFIG as ETH
    for cfg in (BTC, ETH):
        rsi = next(s for s in cfg.signals if s.key == "monthly_rsi")
        assert rsi.cadence == "monthly"
        others = [s for s in cfg.signals if s.key != "monthly_rsi"]
        assert all(s.cadence == "daily" for s in others), cfg.id


import numpy as np
import pandas as pd
from compute_signals import last_change_date


def _dates(n, start="2026-01-01"):
    return pd.Series(pd.date_range(start, periods=n))


def test_last_change_daily_moving_returns_last_date():
    d = _dates(5)
    raw = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4])
    assert last_change_date(d, raw) == d.iloc[-1].date()


def test_last_change_monthly_ffill_returns_month_boundary():
    # value steps once at index 31 (a new month), then holds flat to the end
    d = _dates(60)
    raw = pd.Series([10.0] * 31 + [12.0] * 29)
    assert last_change_date(d, raw) == d.iloc[31].date()


def test_last_change_trailing_nan_returns_last_real_change():
    # daily-moving then 2 lagging NaN days at the end
    d = _dates(5)
    raw = pd.Series([1.0, 1.1, 1.2, np.nan, np.nan])
    assert last_change_date(d, raw) == d.iloc[2].date()


def test_last_change_all_nan_returns_none():
    d = _dates(3)
    raw = pd.Series([np.nan, np.nan, np.nan])
    assert last_change_date(d, raw) is None


def test_last_change_single_distinct_value_returns_first_date():
    d = _dates(4)
    raw = pd.Series([5.0, 5.0, 5.0, 5.0])
    assert last_change_date(d, raw) == d.iloc[0].date()
