import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"

SIGNAL_DISPLAY = {
    "mvrv_zscore": "MVRV Z-Score",
    "ma_200w":     "200-Week MA",
    "monthly_rsi": "Monthly RSI",
    "pi_cycle":    "Pi Cycle",
    "puell":       "Puell Multiple",
    "fear_greed":  "Fear & Greed",
}  # retained for test back-compat; per-asset names come from SignalSpec.display_name


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


def get_sell_verdict(sell_score: float) -> str:
    if sell_score >= 75:
        return "STRONG SELL"
    if sell_score >= 50:
        return "HIGH"
    if sell_score >= 25:
        return "ELEVATED"
    return "LOW"


def compute_spectrum_pos(buy: float, sell: float) -> float:
    """Spectrum position 0-100. 50 = HOLD. 100 = STRONG BUY. 0 = TAKE PROFIT.
    sell only pulls the pointer left when it is meaningfully active (>= 25)."""
    effective_sell = sell if sell >= 25 else 0.0
    raw = 50.0 + (buy - effective_sell) / 2.0
    return round(max(0.0, min(100.0, raw)), 1)


def get_spectrum_verdict(spectrum_pos: float) -> str:
    if spectrum_pos >= 80:
        return "STRONG BUY"
    if spectrum_pos >= 60:
        return "BUY"
    if spectrum_pos >= 40:
        return "HOLD"
    if spectrum_pos >= 20:
        return "SELL"
    return "TAKE PROFIT"


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


def _signal_meta(cfg) -> dict:
    return {
        s.key: {
            "range_lo": s.range_lo, "range_hi": s.range_hi,
            "invest_thresh": s.invest_thresh, "avoid_thresh": s.avoid_thresh,
            "fmt": s.fmt,
        }
        for s in cfg.signals
    }


def _score_asset(cfg) -> None:
    current_path = DATA_DIR / f"{cfg.id}_current_signals.json"
    weights_path = DATA_DIR / f"{cfg.id}_weights.json"
    if not current_path.exists():
        print(f"  skip {cfg.id}: {current_path.name} missing", file=sys.stderr)
        return
    if not weights_path.exists():
        raise FileNotFoundError(
            f"{weights_path.name} not found — run 'python scripts/backtest.py' first "
            "or trigger the 'Re-derive Signal Weights' workflow on GitHub Actions."
        )
    current = json.loads(current_path.read_text())
    weights = json.loads(weights_path.read_text())
    names = {s.key: s.display_name for s in cfg.signals}

    composite = compute_score(current["signals"], weights)
    verdict = get_verdict(composite)

    # ── sell composite ────────────────────────────────────────────────
    sell_weights_path = DATA_DIR / f"{cfg.id}_sell_weights.json"
    sell_composite = 0.0
    if sell_weights_path.exists():
        sell_weights = json.loads(sell_weights_path.read_text())
        sell_signals = {
            name: {"score": data.get("sell_score", 0)}
            for name, data in current["signals"].items()
        }
        sell_composite = round(compute_score(sell_signals, sell_weights), 1)
    else:
        print(f"  {cfg.id}: sell weights missing — run backtest first", file=sys.stderr)

    sell_verdict = get_sell_verdict(sell_composite)
    spectrum_pos = compute_spectrum_pos(composite, sell_composite)
    spectrum_verdict = get_spectrum_verdict(spectrum_pos)

    output = {
        "date": current["date"],
        "composite_score": composite,
        "verdict": verdict,
        "sell_composite": sell_composite,
        "sell_verdict": sell_verdict,
        "spectrum_pos": spectrum_pos,
        "spectrum_verdict": spectrum_verdict,
        "signals": {
            name: {
                "display_name": names[name],
                "raw": _sanitize_float(data["raw"]),
                "score": data["score"],
                "sell_score": data.get("sell_score", 0),
                "status": "buy" if data["score"] == 100 else ("avoid" if data["score"] == 0 else "neutral"),
            }
            for name, data in current["signals"].items()
        },
        "weights": {name: weights["signals"][name]["weight"] for name in weights["signals"]},
        "signal_meta": _signal_meta(cfg),
    }
    (DATA_DIR / f"{cfg.id}_score.json").write_text(json.dumps(output, indent=2))
    print(f"  {cfg.id}: {composite}/100 — {verdict} (sell: {sell_composite}, spectrum: {spectrum_pos} — {spectrum_verdict})")


def main():
    for cfg in ASSETS:
        print(f"Scoring {cfg.display_name}...")
        _score_asset(cfg)


if __name__ == "__main__":
    main()
