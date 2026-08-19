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


from experiment import walk_forward_fixed
from validate_composite import walk_forward
from assets import bitcoin


def _synthetic_market(n=4000, spike_at=None):
    """Price series spanning 2012-2023 with cycle-ish waves. Optionally a 10x
    spike after index spike_at to move the eventual cycle high.

    Formula uses faster growth (exp/500) and shorter sine period (freq=180) so
    that rows near cycle-2 index 2345 satisfy: price > base_cycle2_threshold AND
    fwd_return >= 0.5 (forward window ends at ~2893, before spike_at=3052).
    When the spike lands at the last day of cycle 2 (index 3052), the completed
    cycle's eventual high rises 10x, pushing cycle_range_40pct above those rows'
    prices and flipping their good_entry label False->True — WITHOUT changing their
    forward return (r+548 < 3052). This is the threshold-driven label leak.
    """
    dates = pd.date_range("2012-01-01", periods=n, freq="D")
    t = np.arange(n)
    price = 100 * np.exp(t / 500) * (1.0 + 0.5 * np.sin(t / 180))
    if spike_at is not None:
        price = price.copy()
        price[spike_at:] *= 10
    price_df = pd.DataFrame({"date": dates, "price": price})
    rng = np.random.default_rng(7)
    signals_df = pd.DataFrame({
        "date": dates,
        "sig_a": rng.choice([0, 50, 100], size=n).astype(float),
        "sig_b": rng.choice([0, 50, 100], size=n).astype(float),
    })
    return price_df, signals_df


class _Cfg:
    good_entry = staticmethod(bitcoin.good_entry)
    weight_overrides = None


def test_walk_forward_fixed_is_causal_where_legacy_is_not():
    """Changing prices after index k must not change OOS scores at indices < k.

    Calibration arithmetic (do not change without re-verifying):
      spike_at = 3052  — last day of halving cycle 2 (2016-07-09 to 2020-05-11)
      first_flip = 2345  — earliest good_entry label that flips (threshold-driven:
                           price[2345] > base_cycle2_threshold but price[2345] <=
                           new 10x threshold; fwd_return unchanged since 2345+548=2893 < 3052)
      contaminated walk-forward windows: t=2900 and t=2990 (both satisfy
           first_flip < t-HOLDING_DAYS AND t < spike_at, i.e. 2345 < t-548 AND t < 3052)
      k = 3050  — comparison cutoff: first_flip+548 < contaminated_t < k < spike_at
                  so legacy[:k] differs (contamination at 2900,2990) while
                  fixed[:k] is identical (all windows t<k use only prices[:t] < spike)
    """
    spike_at = 3052
    k = 3050
    names = ["sig_a", "sig_b"]
    base_p, base_s = _synthetic_market()
    spike_p, _ = _synthetic_market(spike_at=spike_at)

    fixed_base = walk_forward_fixed(base_p, base_s, _Cfg, names)
    fixed_spike = walk_forward_fixed(spike_p, base_s, _Cfg, names)
    pd.testing.assert_series_equal(fixed_base.iloc[:k], fixed_spike.iloc[:k])

    legacy_base, _ = walk_forward(base_p, base_s, _Cfg, names)
    legacy_spike, _ = walk_forward(spike_p, base_s, _Cfg, names)
    assert not legacy_base.iloc[:k].equals(legacy_spike.iloc[:k]), (
        "legacy walk_forward unexpectedly causal — synthetic spike too weak, "
        "or the leak was already fixed upstream"
    )


def test_family_equal_weights_sum_to_one_and_split_within_family():
    from experiment import FAMILIES, family_equal_weights
    names = [m for members in FAMILIES.values() for m in members]
    w = family_equal_weights(names)
    assert set(w) == set(names)
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)
    # 4 families -> each family totals 0.25; trend has 3 members
    assert w["mvrv_zscore"] == pytest.approx(0.25, abs=1e-3)
    assert w["ma_200w"] == pytest.approx(0.25 / 3, abs=1e-3)
    assert w["puell"] == pytest.approx(0.25, abs=1e-3)
    assert w["fear_greed"] == pytest.approx(0.25, abs=1e-3)


def test_family_equal_weights_rejects_unknown_signal():
    from experiment import family_equal_weights
    with pytest.raises(AssertionError):
        family_equal_weights(["mvrv_zscore", "not_a_signal"])


def test_build_signal_history_variant_flags():
    from experiment import build_signal_history
    from assets import bitcoin
    n = 2500
    dates = pd.date_range("2013-01-01", periods=n, freq="D")
    rng = np.random.default_rng(11)
    price = 100 * np.exp(np.arange(n) / 900)
    df = pd.DataFrame({
        "date": dates, "price": price,
        "market_cap": price * 1e7,
        "mvrv": rng.normal(2.0, 0.8, size=n),
        "miner_revenue": rng.uniform(1e6, 5e6, size=n),
        "fear_greed": rng.uniform(0, 100, size=n),
    })
    specs = bitcoin.CONFIG.signals

    ternary = build_signal_history(df, specs, causal_z=False, continuous=False)
    assert set(ternary["mvrv_zscore"].dropna().unique()) <= {0, 50, 100}

    cont = build_signal_history(df, specs, causal_z=False, continuous=True)
    mid = cont["mvrv_zscore"].dropna()
    assert ((0 <= mid) & (mid <= 100)).all()
    assert len(set(mid.unique()) - {0.0, 50.0, 100.0}) > 0  # actually interpolates

    causal = build_signal_history(df, specs, causal_z=True, continuous=False)
    # expanding z with min_periods=365: first 364 raws NaN -> neutral 50
    assert causal["mvrv_zscore_raw"].iloc[:364].isna().all()
    assert (causal["mvrv_zscore"].iloc[:364] == 50).all()
    # non-mvrv signals identical across the causal_z flag
    pd.testing.assert_series_equal(causal["ma_200w"], ternary["ma_200w"])
