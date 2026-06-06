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
