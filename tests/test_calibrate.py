import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from calibrate_eth_thresholds import anchored_threshold


def test_anchored_threshold_returns_correct_quantile():
    # Uniform 0..99; target_buy_rate=0.10 -> 10th percentile = 9.9
    series = pd.Series(range(100), dtype=float)
    result = anchored_threshold(series, target_buy_rate=0.10)
    assert abs(result - 9.9) < 0.5


def test_anchored_threshold_clamps_rate_below_45pct():
    # A target_buy_rate > 0.45 is clamped to 0.45 so invest_thresh never
    # exceeds the median (preserving lower=invest semantics).
    series = pd.Series(range(100), dtype=float)
    result_high = anchored_threshold(series, target_buy_rate=0.80)
    result_capped = anchored_threshold(series, target_buy_rate=0.45)
    assert result_high == result_capped


def test_anchored_threshold_ignores_nan():
    series = pd.Series([1.0, float("nan"), 3.0, 5.0])
    # rate=0.50 is clamped to 0.45; 45th pct of [1,3,5] with method="higher" = 3.0
    result = anchored_threshold(series, target_buy_rate=0.50)
    assert abs(result - 3.0) < 0.01
