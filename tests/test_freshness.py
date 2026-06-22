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


from score import build_signal_entry, compute_score, SIGNAL_DISPLAY


def test_build_signal_entry_includes_cadence_and_as_of():
    entry = build_signal_entry(
        {"raw": 47.0, "score": 50, "sell_score": 0, "as_of": "2026-05-31"},
        display_name="Monthly RSI", cadence="monthly",
    )
    assert entry["cadence"] == "monthly"
    assert entry["as_of"] == "2026-05-31"
    assert entry["status"] == "neutral"
    assert entry["display_name"] == "Monthly RSI"
    assert entry["score"] == 50


def test_build_signal_entry_status_mapping():
    assert build_signal_entry({"raw": 0, "score": 100}, "x", "daily")["status"] == "buy"
    assert build_signal_entry({"raw": 0, "score": 0}, "x", "daily")["status"] == "avoid"
    assert build_signal_entry({"raw": 0, "score": 50}, "x", "daily")["status"] == "neutral"


def test_build_signal_entry_missing_as_of_is_none():
    entry = build_signal_entry({"raw": 1.0, "score": 100}, "x", "daily")
    assert entry["as_of"] is None
    assert entry["sell_score"] == 0


def test_compute_score_ignores_extra_signal_keys():
    """Regression guard: the math must not react to the new fields."""
    base = {name: {"score": 100} for name in SIGNAL_DISPLAY}
    extra = {name: {"score": 100, "cadence": "daily", "as_of": "2026-06-20", "raw": 1.2}
             for name in SIGNAL_DISPLAY}
    weights = {"signals": {name: {"weight": 1 / 6} for name in SIGNAL_DISPLAY}}
    assert compute_score(base, weights) == compute_score(extra, weights)


from build_dashboard import next_refresh_date, format_freshness


def test_next_refresh_mid_month_is_month_end():
    import datetime
    assert next_refresh_date("2026-06-21", "monthly") == datetime.date(2026, 6, 30)


def test_next_refresh_on_month_end_is_same_day():
    import datetime
    assert next_refresh_date("2026-06-30", "monthly") == datetime.date(2026, 6, 30)


def test_next_refresh_daily_is_none():
    assert next_refresh_date("2026-06-21", "daily") is None


def test_format_freshness_daily_current():
    assert format_freshness("daily", "2026-06-20", "2026-06-20") == "Daily · as of Jun 20"


def test_format_freshness_daily_lagging():
    assert format_freshness("daily", "2026-06-18", "2026-06-20") == "Daily · as of Jun 18"


def test_format_freshness_monthly():
    assert format_freshness("monthly", "2026-05-31", "2026-06-21") == \
        "Monthly · as of May 31 · next Jun 30"


def test_format_freshness_no_data_is_cadence_only():
    assert format_freshness("daily", None, "2026-06-20") == "Daily"
    assert format_freshness("monthly", None, "2026-06-20") == "Monthly"
