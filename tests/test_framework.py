import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict

DATA = Path(__file__).parent.parent / "data"

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


def _load(name_candidates):
    """Read the first data file that exists from a list of candidate names."""
    for name in name_candidates:
        p = DATA / name
        if p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError(f"none of {name_candidates} found in {DATA}")


def test_bitcoin_scoring_parity():
    # current_signals.json is renamed to bitcoin_current_signals.json in Task 6;
    # accept either so this test passes before and after the rename.
    current = _load(["bitcoin_current_signals.json", "current_signals.json"])
    weights = _load(["bitcoin_weights.json", "weights.json"])

    composite = compute_score(current["signals"], weights)
    assert composite == GOLDEN_COMPOSITE
    assert get_verdict(composite) == GOLDEN_VERDICT
    for key, expected in GOLDEN_SIGNAL_SCORES.items():
        assert current["signals"][key]["score"] == expected, key
