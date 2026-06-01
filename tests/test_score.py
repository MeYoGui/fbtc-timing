import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from score import compute_score, get_verdict, SIGNAL_DISPLAY

EQUAL_WEIGHTS = {
    "signals": {name: {"weight": 1/6} for name in SIGNAL_DISPLAY}
}


def test_get_verdict_avoid():
    assert get_verdict(0) == "AVOID"
    assert get_verdict(24.9) == "AVOID"


def test_get_verdict_wait():
    assert get_verdict(25) == "WAIT"
    assert get_verdict(49.9) == "WAIT"


def test_get_verdict_close():
    assert get_verdict(50) == "CLOSE"
    assert get_verdict(71.9) == "CLOSE"


def test_get_verdict_invest():
    assert get_verdict(72) == "INVEST"
    assert get_verdict(79.9) == "INVEST"


def test_get_verdict_strong_buy():
    assert get_verdict(80) == "STRONG BUY"
    assert get_verdict(100) == "STRONG BUY"


def test_compute_score_all_buy():
    signals = {name: {"score": 100} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(100.0, abs=0.1)


def test_compute_score_all_avoid():
    signals = {name: {"score": 0} for name in SIGNAL_DISPLAY}
    assert compute_score(signals, EQUAL_WEIGHTS) == pytest.approx(0.0, abs=0.1)


def test_compute_score_mixed():
    signals = {name: {"score": 100 if i % 2 == 0 else 0} for i, name in enumerate(SIGNAL_DISPLAY)}
    score = compute_score(signals, EQUAL_WEIGHTS)
    assert 40 < score < 60
