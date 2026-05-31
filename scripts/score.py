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


def get_verdict(score: float) -> str:
    if score >= 75:
        return "STRONG BUY"
    if score >= 50:
        return "ACCUMULATE"
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
    }

    (DATA_DIR / "current_score.json").write_text(json.dumps(output, indent=2))
    print(f"Score: {composite}/100 — {verdict}")
    for name, d in output["signals"].items():
        print(f"  {d['display_name']}: {d['status'].upper()}")


if __name__ == "__main__":
    main()
