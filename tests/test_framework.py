import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict

# Golden values snapshotted from data/current_score.json on 2026-05-31.
# These pin Bitcoin's scoring behaviour across the multi-asset refactor.
GOLDEN_COMPOSITE = 54.5
GOLDEN_VERDICT = "CLOSE"
GOLDEN_SIGNAL_SCORES = {
    "mvrv_zscore": 50,
    "ma_200w": 50,
    "monthly_rsi": 50,
    "pi_cycle": 100,
    "puell": 50,
    "fear_greed": 50,
}

# 2026-05-31 reference weights (precision-derived, MVRV 2× applied). Pinned here so
# this regression test stays valid as the daily workflow refreshes live data files.
GOLDEN_WEIGHTS = {
    "signals": {
        "mvrv_zscore": {"weight": 0.3434},
        "ma_200w":     {"weight": 0.1717},
        "monthly_rsi": {"weight": 0.1717},
        "pi_cycle":    {"weight": 0.0903},
        "puell":       {"weight": 0.1602},
        "fear_greed":  {"weight": 0.0627},
    }
}


def test_bitcoin_scoring_parity():
    """Data-independent regression guard for Bitcoin's scoring math.

    Pins the 2026-05-31 signal scores + derived weights → composite 54.5 / CLOSE.
    Uses inline fixtures (not the mutable data files) so it survives daily refreshes."""
    signals = {key: {"score": score} for key, score in GOLDEN_SIGNAL_SCORES.items()}
    composite = compute_score(signals, GOLDEN_WEIGHTS)
    assert composite == GOLDEN_COMPOSITE
    assert get_verdict(composite) == GOLDEN_VERDICT


# ── assets/base.py ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.base import AssetConfig, SignalSpec


def _dummy_spec():
    return SignalSpec(
        key="x", display_name="X", compute=lambda df: df["x"],
        invest_thresh=1.0, avoid_thresh=2.0,
        range_lo=0.0, range_hi=3.0, fmt="{:.1f}",
    )


def test_signalspec_fields():
    s = _dummy_spec()
    assert s.key == "x"
    assert s.invest_thresh < s.avoid_thresh
    assert callable(s.compute)


def test_assetconfig_requires_core_fields():
    cfg = AssetConfig(
        id="dummy", display_name="Dummy", short_label="D", accent_color="#fff",
        price_unit="$", fetch=lambda: None, signals=[_dummy_spec()],
        good_entry=lambda df: None,
    )
    assert cfg.id == "dummy"
    assert cfg.weight_overrides is None
    assert len(cfg.signals) == 1


# ── assets/bitcoin.py + registry ──────────────────────────────────────────────
from assets.registry import ASSETS
from assets import bitcoin


def test_registry_contains_bitcoin():
    assert any(a.id == "bitcoin" for a in ASSETS)


def test_bitcoin_has_six_signals():
    keys = [s.key for s in bitcoin.CONFIG.signals]
    assert keys == ["mvrv_zscore", "ma_200w", "monthly_rsi", "pi_cycle", "puell", "fear_greed"]


def test_bitcoin_thresholds_match_legacy():
    by_key = {s.key: s for s in bitcoin.CONFIG.signals}
    assert by_key["mvrv_zscore"].invest_thresh == -0.5
    assert by_key["mvrv_zscore"].avoid_thresh == 1.5
    assert by_key["fear_greed"].invest_thresh == 25.0
    assert by_key["fear_greed"].avoid_thresh == 50.0
    assert by_key["pi_cycle"].invest_thresh == 0.9
    assert by_key["pi_cycle"].avoid_thresh == 1.0


def test_bitcoin_weight_override_mvrv():
    assert bitcoin.CONFIG.weight_overrides == {"mvrv_zscore": 2.0}


def test_adding_a_config_appears_in_registry(monkeypatch):
    """A second AssetConfig appended to ASSETS is picked up generically."""
    import assets.registry as reg
    from assets.base import AssetConfig
    from assets import bitcoin
    extra = AssetConfig(
        id="testcoin", display_name="TestCoin", short_label="T", accent_color="#abc",
        price_unit="$", fetch=bitcoin.fetch, signals=bitcoin.CONFIG.signals,
        good_entry=bitcoin.good_entry, weight_overrides=None,
    )
    monkeypatch.setattr(reg, "ASSETS", reg.ASSETS + [extra])
    assert [a.id for a in reg.ASSETS] == ["bitcoin", "testcoin"]
