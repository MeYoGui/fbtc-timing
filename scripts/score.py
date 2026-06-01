import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

SIGNAL_DISPLAY = {
    "mvrv_zscore": "MVRV Z-Score",
    "ma_200w":     "200-Week MA",
    "monthly_rsi": "Monthly RSI",
    "pi_cycle":    "Pi Cycle",
    "puell":       "Puell Multiple",
    "fear_greed":  "Fear & Greed",
}

SIGNAL_META = {
    "mvrv_zscore": {
        "range_lo": -3.0, "range_hi": 4.0,
        "invest_thresh": -0.5, "avoid_thresh": 1.5,
        "fmt": "{:.1f}",
    },
    "ma_200w": {
        "range_lo": 0.5, "range_hi": 3.0,
        "invest_thresh": 1.0, "avoid_thresh": 1.2,
        "fmt": "{:.1f}×",
    },
    "monthly_rsi": {
        "range_lo": 0.0, "range_hi": 100.0,
        "invest_thresh": 40.0, "avoid_thresh": 70.0,
        "fmt": "{:.0f}",
    },
    "pi_cycle": {
        "range_lo": 0.0, "range_hi": 1.5,
        "invest_thresh": 0.9, "avoid_thresh": 1.0,
        "fmt": "{:.1f}",
    },
    "puell": {
        "range_lo": 0.0, "range_hi": 4.0,
        "invest_thresh": 0.5, "avoid_thresh": 1.5,
        "fmt": "{:.1f}",
    },
    "fear_greed": {
        "range_lo": 0.0, "range_hi": 100.0,
        "invest_thresh": 25.0, "avoid_thresh": 50.0,
        "fmt": "{:.0f}",
    },
}


def get_verdict(score: float) -> str:
    if score >= 80:
        return "STRONG BUY"
    if score >= 72:
        return "INVEST"
    if score >= 50:
        return "CLOSE"
    if score >= 25:
        return "WAIT"
    return "AVOID"


def compute_score(signals: dict, weights: dict) -> float:
    total_weight = sum(weights["signals"][name]["weight"] for name in signals)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(
        signals[name]["score"] * weights["signals"][name]["weight"]
        for name in signals
    )
    return round(weighted_sum / total_weight, 1)


def _sanitize_float(v):
    """Convert NaN/inf to None for valid JSON null output."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else f
    except (TypeError, ValueError):
        return None


def main():
    current = json.loads((DATA_DIR / "current_signals.json").read_text())

    weights_path = DATA_DIR / "weights.json"
    if not weights_path.exists():
        raise FileNotFoundError(
            "data/weights.json not found — run 'python scripts/backtest.py' first "
            "or trigger the 'Re-derive Signal Weights' workflow on GitHub Actions."
        )
    weights = json.loads(weights_path.read_text())

    composite = compute_score(current["signals"], weights)
    verdict = get_verdict(composite)

    output = {
        "date": current["date"],
        "composite_score": composite,
        "verdict": verdict,
        "signals": {
            name: {
                "display_name": SIGNAL_DISPLAY[name],
                "raw": _sanitize_float(data["raw"]),
                "score": data["score"],
                "status": "buy" if data["score"] == 100 else ("avoid" if data["score"] == 0 else "neutral"),
            }
            for name, data in current["signals"].items()
        },
        "weights": {name: weights["signals"][name]["weight"] for name in weights["signals"]},
        "signal_meta": SIGNAL_META,
    }

    (DATA_DIR / "current_score.json").write_text(json.dumps(output, indent=2))
    print(f"Score: {composite}/100 — {verdict}")
    for name, d in output["signals"].items():
        print(f"  {d['display_name']}: {d['status'].upper()}")


if __name__ == "__main__":
    main()
