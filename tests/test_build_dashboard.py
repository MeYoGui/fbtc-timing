import pytest
import sys
import numpy as np
import pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_dashboard import compute_signal_bar
from build_dashboard import build_trend_data

MVRV_META = {
    "range_lo": -3.0, "range_hi": 4.0,
    "invest_thresh": -0.5, "avoid_thresh": 1.5,
    "fmt": "{:.1f}",
}

FEAR_META = {
    "range_lo": 0.0, "range_hi": 100.0,
    "invest_thresh": 25.0, "avoid_thresh": 50.0,
    "fmt": "{:.0f}",
}


def test_no_data_returns_has_data_false():
    result = compute_signal_bar("mvrv_zscore", None, 50, MVRV_META)
    assert result["has_data"] is False


def test_invest_zone_status():
    # raw=-1.0 is below invest_thresh=-0.5, score=100
    result = compute_signal_bar("mvrv_zscore", -1.0, 100, MVRV_META)
    assert result["has_data"] is True
    assert result["status_class"] == "st-invest"
    assert result["status_text"].startswith("INVEST")


def test_avoid_zone_status():
    # raw=2.0 is above avoid_thresh=1.5, score=0
    result = compute_signal_bar("mvrv_zscore", 2.0, 0, MVRV_META)
    assert result["status_class"] == "st-avoid"
    assert result["status_text"] == "AVOID"


def test_wait_zone_closer_to_invest():
    # raw=-0.25, invest_thresh=-0.5, avoid_thresh=1.5
    # dist_invest=0.25, dist_avoid=1.75 → closer to invest
    result = compute_signal_bar("mvrv_zscore", -0.25, 50, MVRV_META)
    assert result["status_class"] == "st-wait"
    assert "from invest" in result["status_text"]


def test_wait_zone_closer_to_avoid():
    # raw=1.4, dist_avoid=0.1, dist_invest=1.9 → closer to avoid
    result = compute_signal_bar("mvrv_zscore", 1.4, 50, MVRV_META)
    assert "from avoid" in result["status_text"]
    assert "⚠️" in result["status_text"]


def test_cursor_clamped_at_bounds():
    # raw beyond range_hi should clamp to 0%
    result = compute_signal_bar("mvrv_zscore", 10.0, 0, MVRV_META)
    assert result["cursor_pct"] == 0.0
    # raw beyond range_lo should clamp to 100%
    result = compute_signal_bar("mvrv_zscore", -10.0, 100, MVRV_META)
    assert result["cursor_pct"] == 100.0


def test_zone_widths_sum_to_100():
    result = compute_signal_bar("mvrv_zscore", -0.25, 50, MVRV_META)
    total = result["avoid_pct"] + result["wait_pct"] + result["invest_pct"]
    assert abs(total - 100.0) < 0.2  # floating point tolerance


def test_thresh_positions_ordered():
    result = compute_signal_bar("mvrv_zscore", -0.25, 50, MVRV_META)
    # avoid threshold is to the LEFT of invest threshold on the bar
    assert result["thresh_avoid_pct"] < result["thresh_invest_pct"]


def test_fear_greed_invest_labels():
    # F&G fmt is "{:.0f}", range_hi=100, range_lo=0
    result = compute_signal_bar("fear_greed", 23.0, 100, FEAR_META)
    assert result["edge_left"] == "100"
    assert result["edge_right"] == "0"
    assert result["thresh_avoid_lbl"] == "50"
    assert result["thresh_invest_lbl"] == "25"


# ── build_trend_data ─────────────────────────────────────────────────────────

_SIGNAL_NAMES = ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]

def _make_signals_df(n_days: int = 400, start_score: int = 40, end_score: int = 60):
    """Minimal signals_df with linearly changing integer scores over n_days."""
    dates = pd.date_range(end="2026-05-31", periods=n_days, freq="D")
    scores = np.linspace(start_score, end_score, n_days).round().astype(int)
    data: dict = {"date": dates}
    for sig in _SIGNAL_NAMES:
        data[f"{sig}_raw"] = np.ones(n_days)
        data[sig] = scores
    return pd.DataFrame(data)

_EQUAL_WEIGHTS = {
    "signals": {sig: {"weight": 1.0} for sig in _SIGNAL_NAMES}
}


def test_trend_data_returns_all_windows():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    assert set(result.keys()) == {"day", "week", "month"}


def test_trend_each_window_has_required_keys():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        assert "delta" in result[win]
        assert "spark" in result[win]
        assert "arrows" in result[win]


def test_trend_spark_has_seven_entries():
    result = build_trend_data(_make_signals_df(n_days=400), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        assert len(result[win]["spark"]) == 7


def test_trend_spark_entry_keys():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for entry in result["day"]["spark"]:
        assert "score" in entry
        assert "label" in entry
        assert "verdict" in entry


def test_trend_arrows_cover_all_signals():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        assert set(result[win]["arrows"].keys()) == set(_SIGNAL_NAMES)


def test_trend_arrow_values_are_valid():
    result = build_trend_data(_make_signals_df(), _EQUAL_WEIGHTS)
    for win in ("day", "week", "month"):
        for sig, val in result[win]["arrows"].items():
            assert val in (-1, 0, 1), f"{win}.{sig} arrow={val}"


def test_trend_uptrend_gives_positive_delta():
    # Scores rise 40→60 → today > yesterday
    result = build_trend_data(_make_signals_df(n_days=40, start_score=40, end_score=60), _EQUAL_WEIGHTS)
    assert result["day"]["delta"] > 0


def test_trend_downtrend_gives_negative_delta():
    # Scores fall 60→40 → today < yesterday
    result = build_trend_data(_make_signals_df(n_days=40, start_score=60, end_score=40), _EQUAL_WEIGHTS)
    assert result["day"]["delta"] < 0


def test_trend_no_prior_data_gives_zero_delta():
    # Only 1 row — no prior day to compare
    result = build_trend_data(_make_signals_df(n_days=1), _EQUAL_WEIGHTS)
    assert result["day"]["delta"] == 0.0
    assert all(v == 0 for v in result["day"]["arrows"].values())


# ── per-asset signal keys + new ETH readings ─────────────────────────────────
from build_dashboard import compute_historical_scores, format_reading


def test_compute_historical_scores_uses_passed_signal_names():
    signals_df = pd.DataFrame({
        "eth_btc_ratio":  [100, 0],
        "mayer_multiple": [0, 100],
    })
    weights = {"signals": {
        "eth_btc_ratio":  {"weight": 0.75},
        "mayer_multiple": {"weight": 0.25},
    }}
    names = ["eth_btc_ratio", "mayer_multiple"]
    result = compute_historical_scores(signals_df, weights, names)
    # row0: (100*.75 + 0*.25)/1.0 = 75 ; row1: (0*.75 + 100*.25)/1.0 = 25
    assert list(result.round(1)) == [75.0, 25.0]


def test_format_reading_handles_new_eth_signals():
    assert format_reading("mayer_multiple", 1.234) == "1.23× 200DMA"
    assert format_reading("eth_btc_ratio", -0.5) == "-0.50 z (ETH/BTC)"


# ── compute_price_change_24h ─────────────────────────────────────────────────
from build_dashboard import compute_price_change_24h


def test_price_change_24h_positive():
    df = pd.DataFrame({"price": [100.0, 102.5]})
    assert compute_price_change_24h(df) == 2.5


def test_price_change_24h_negative():
    df = pd.DataFrame({"price": [100.0, 95.0]})
    assert compute_price_change_24h(df) == -5.0


def test_price_change_24h_skips_trailing_nan():
    # Last valid pair is 100 -> 110 ; the NaN row must be ignored
    df = pd.DataFrame({"price": [100.0, 110.0, np.nan]})
    assert compute_price_change_24h(df) == 10.0


def test_price_change_24h_single_row_returns_zero():
    df = pd.DataFrame({"price": [100.0]})
    assert compute_price_change_24h(df) == 0.0


def test_price_change_24h_zero_prev_returns_zero():
    df = pd.DataFrame({"price": [0.0, 50.0]})
    assert compute_price_change_24h(df) == 0.0


# ── verdict_description ──────────────────────────────────────────────────────
from build_dashboard import verdict_description


def test_verdict_description_strong_buy():
    assert verdict_description("STRONG BUY") == (
        "Momentum and on-chain metrics suggest highly favorable entry conditions."
    )


def test_verdict_description_each_verdict_is_nonempty():
    for v in ("STRONG BUY", "BUY", "HOLD", "SELL", "TAKE PROFIT"):
        assert len(verdict_description(v)) > 0


def test_verdict_description_unknown_falls_back_to_hold_copy():
    assert verdict_description("???") == verdict_description("HOLD")


# ── _assemble_asset integration: new keys present ────────────────────────────
from build_dashboard import _assemble_asset
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS as ASSET_CONFIGS


def test_assembled_bitcoin_blob_has_new_keys():
    cfg = next(c for c in ASSET_CONFIGS if c.id == "bitcoin")
    blob = _assemble_asset(cfg)
    assert blob is not None, "bitcoin data files must be present to run this test"
    assert "price_change_24h" in blob
    assert isinstance(blob["price_change_24h"], float)
    assert "verdict_description" in blob
    assert len(blob["verdict_description"]) > 0
