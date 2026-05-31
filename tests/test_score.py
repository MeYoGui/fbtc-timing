import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict, SIGNAL_DISPLAY

EQUAL_WEIGHTS = {
    "signals": {name: {"weight": 1/6} for name in SIGNAL_DISPLAY}
}


def test_get_verdict_strong_buy():
    assert get_verdict(80) == "STRONG BUY"


def test_get_verdict_accumulate():
    assert get_verdict(60) == "ACCUMULATE"


def test_get_verdict_wait():
    assert get_verdict(40) == "WAIT"


def test_get_verdict_avoid():
    assert get_verdict(10) == "AVOID"


def test_get_verdict_boundary_75():
    assert get_verdict(75) == "STRONG BUY"


def test_get_verdict_boundary_50():
    assert get_verdict(50) == "ACCUMULATE"


def test_compute_score_all_buy():
    signals = {name: {"score": 100} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(100.0, abs=0.1)


def test_compute_score_all_avoid():
    signals = {name: {"score": 0} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(0.0, abs=0.1)


def test_compute_score_mixed():
    signals = {name: {"score": 100 if i % 2 == 0 else 0} for i, name in enumerate(SIGNAL_DISPLAY)}
    score = compute_score(signals, EQUAL_WEIGHTS)
    assert 40 < score < 60  # roughly 50
