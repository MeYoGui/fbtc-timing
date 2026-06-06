# tests/test_sell_signal.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.base import SignalSpec, AssetConfig
import pandas as pd

def _dummy_compute(df): return df["price"]
def _dummy_fetch(): return pd.DataFrame()
def _dummy_entry(df): return pd.Series(dtype=bool)
def _dummy_exit(df): return pd.Series(dtype=bool)

def test_signal_spec_has_sell_thresh():
    spec = SignalSpec(
        key="mvrv_zscore", display_name="MVRV", compute=_dummy_compute,
        invest_thresh=-0.5, avoid_thresh=1.5, sell_thresh=3.5,
        range_lo=-3.0, range_hi=4.0, fmt="{:.1f}",
    )
    assert spec.sell_thresh == 3.5

def test_asset_config_has_good_exit():
    cfg = AssetConfig(
        id="test", display_name="Test", short_label="T", accent_color="#fff",
        price_unit="$", fetch=_dummy_fetch, signals=[],
        good_entry=_dummy_entry, good_exit=_dummy_exit,
    )
    assert callable(cfg.good_exit)

def test_asset_config_sell_weight_overrides_defaults_none():
    cfg = AssetConfig(
        id="test", display_name="Test", short_label="T", accent_color="#fff",
        price_unit="$", fetch=_dummy_fetch, signals=[],
        good_entry=_dummy_entry, good_exit=_dummy_exit,
    )
    assert cfg.sell_weight_overrides is None

import numpy as np

def _make_btc_df(n=1500, prices=None):
    """Minimal BTC-like DataFrame for testing good_exit."""
    import pandas as pd, numpy as np
    dates = pd.date_range("2015-01-01", periods=n)
    if prices is None:
        prices = np.linspace(1000, 70000, n)
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "market_cap": np.array(prices) * 19_000_000,
        "mvrv": np.full(n, 2.0),
        "miner_revenue": np.full(n, 1e7),
        "fear_greed": np.full(n, 50),
    })

def test_btc_good_exit_returns_bool_series():
    from assets.bitcoin import good_exit
    df = _make_btc_df()
    result = good_exit(df)
    assert result.dtype == bool
    assert len(result) == len(df)

def test_btc_good_exit_false_when_price_at_bottom():
    """Price near minimum — should NOT be a good exit."""
    from assets.bitcoin import good_exit
    prices = [5000.0] * 1500  # flat low price, no big drawdown possible
    df = _make_btc_df(prices=prices)
    result = good_exit(df)
    assert result.sum() == 0

def test_btc_config_has_sell_thresh():
    from assets.bitcoin import CONFIG
    for spec in CONFIG.signals:
        assert hasattr(spec, "sell_thresh"), f"{spec.key} missing sell_thresh"
        if spec.key != "pi_cycle":
            assert spec.sell_thresh > spec.avoid_thresh, (
                f"{spec.key}: sell_thresh {spec.sell_thresh} should be > avoid_thresh {spec.avoid_thresh}"
            )


def _make_eth_df(n=1500, prices=None):
    import pandas as pd, numpy as np
    dates = pd.date_range("2016-01-01", periods=n)
    if prices is None:
        prices = np.linspace(10, 4800, n)
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "market_cap": np.array(prices) * 120_000_000,
        "mvrv": np.full(n, 2.0),
        "btc_price": np.linspace(500, 60000, n),
        "fear_greed": np.full(n, 50),
    })

def test_eth_good_exit_returns_bool_series():
    from assets.eth import good_exit
    df = _make_eth_df()
    result = good_exit(df)
    assert result.dtype == bool
    assert len(result) == len(df)

def test_eth_good_exit_false_when_price_at_bottom():
    from assets.eth import good_exit
    prices = [100.0] * 1500
    df = _make_eth_df(prices=prices)
    result = good_exit(df)
    assert result.sum() == 0

def test_eth_config_has_sell_thresh():
    from assets.eth import CONFIG
    for spec in CONFIG.signals:
        assert hasattr(spec, "sell_thresh"), f"{spec.key} missing sell_thresh"


def test_sell_signal_score_above_thresh():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from compute_signals import sell_signal_score
    assert sell_signal_score(4.0, sell_thresh=3.5) == 100


def test_sell_signal_score_below_thresh():
    from compute_signals import sell_signal_score
    assert sell_signal_score(2.0, sell_thresh=3.5) == 0


def test_sell_signal_score_exactly_at_thresh():
    from compute_signals import sell_signal_score
    # strictly greater than — at threshold is NOT a sell signal
    assert sell_signal_score(3.5, sell_thresh=3.5) == 0


def test_compute_all_signals_includes_sell_columns():
    import pandas as pd, numpy as np, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from compute_signals import compute_all_signals
    from assets.bitcoin import CONFIG
    n = 1500
    dates = pd.date_range("2015-01-01", periods=n)
    df = pd.DataFrame({
        "date": dates,
        "price": np.linspace(1000, 70000, n),
        "market_cap": np.linspace(1e10, 1e12, n),
        "mvrv": np.full(n, 1.0),
        "miner_revenue": np.full(n, 1e7),
        "fear_greed": np.full(n, 50),
    })
    out = compute_all_signals(df, CONFIG.signals)
    for spec in CONFIG.signals:
        assert f"{spec.key}_sell" in out.columns, f"missing {spec.key}_sell column"
        assert set(out[f"{spec.key}_sell"].dropna().unique()).issubset({0, 100})
