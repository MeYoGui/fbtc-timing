import json
import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
DOCS_DIR = Path(__file__).parent.parent / "docs"

SIGNAL_DISPLAY = {
    "mvrv_zscore": "MVRV Z-Score",
    "ma_200w":     "200-Week MA",
    "monthly_rsi": "Monthly RSI",
    "pi_cycle":    "Pi Cycle",
    "puell":       "Puell Multiple",
    "fear_greed":  "Fear & Greed",
}

STATUS_LABELS = {"buy": "Buy Zone", "neutral": "Neutral", "avoid": "Avoid"}


def format_reading(name: str, raw) -> str:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "N/A"
    raw = float(raw)
    if name == "mvrv_zscore":
        return f"{raw:.2f}"
    if name == "ma_200w":
        pct = (raw - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}% vs 200WMA"
    if name == "monthly_rsi":
        return f"{raw:.0f}"
    if name == "pi_cycle":
        pct = (raw - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"111DMA {sign}{pct:.1f}% vs 2×350DMA"
    if name == "puell":
        return f"{raw:.2f}"
    if name == "fear_greed":
        return f"{raw:.0f} / 100"
    return f"{raw:.3f}"


def get_score_color(score: float) -> str:
    if score >= 75:
        return "#00c853"
    if score >= 50:
        return "#69f0ae"
    if score >= 25:
        return "#ffd740"
    return "#ff5252"


def compute_historical_scores(signals_df: pd.DataFrame, weights: dict) -> pd.Series:
    signal_names = list(SIGNAL_DISPLAY.keys())
    w = np.array([weights["signals"][s]["weight"] for s in signal_names])
    total_w = w.sum()
    scores = signals_df[signal_names].values @ w / total_w
    return pd.Series(scores, index=signals_df.index)


def build_chart_data(price_df: pd.DataFrame, signals_df: pd.DataFrame, weights: dict) -> dict:
    score_series = compute_historical_scores(signals_df, weights)
    signals_df = signals_df.copy()
    signals_df["composite_score"] = score_series

    merged = price_df[["date", "price"]].merge(signals_df[["date", "composite_score"]], on="date", how="inner")
    merged = merged.dropna()
    merged["date"] = pd.to_datetime(merged["date"])
    weekly = merged.set_index("date").resample("W").last().reset_index()
    weekly = weekly.dropna()

    return {
        "dates":  weekly["date"].dt.strftime("%Y-%m-%d").tolist(),
        "prices": weekly["price"].round(0).tolist(),
        "scores": weekly["composite_score"].round(1).tolist(),
    }


def main():
    current_score = json.loads((DATA_DIR / "current_score.json").read_text())
    weights = json.loads((DATA_DIR / "weights.json").read_text())
    price_df = pd.read_csv(DATA_DIR / "btc_history.csv")
    price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(DATA_DIR / "signal_history.csv")
    signals_df["date"] = pd.to_datetime(signals_df["date"])

    chart_data = build_chart_data(price_df, signals_df, weights)

    signals = {}
    for name, data in current_score["signals"].items():
        signals[name] = {
            "display_name": data["display_name"],
            "reading_formatted": format_reading(name, data["raw"]),
            "status": data["status"],
            "status_label": STATUS_LABELS[data["status"]],
        }

    methodology = {
        name: {
            "display_name": SIGNAL_DISPLAY[name],
            "weight":    weights["signals"][name]["weight"],
            "precision": weights["signals"][name]["precision"],
            "recall":    weights["signals"][name]["recall"],
            "f1":        weights["signals"][name]["f1"],
        }
        for name in SIGNAL_DISPLAY
    }

    # Use last row with valid price
    btc_price = price_df.dropna(subset=["price"])["price"].iloc[-1]

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        btc_price=btc_price,
        updated_date=current_score["date"],
        composite_score=current_score["composite_score"],
        verdict=current_score["verdict"],
        score_color=get_score_color(current_score["composite_score"]),
        signals=signals,
        chart_data_json=json.dumps(chart_data),
        methodology=methodology,
    )

    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard written to docs/index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
