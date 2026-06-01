import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_dashboard import compute_signal_bar

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
