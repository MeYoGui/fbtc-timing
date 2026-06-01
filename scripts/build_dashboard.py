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


def get_score_color(verdict: str) -> str:
    return {
        "STRONG BUY": "#00e676",
        "INVEST":     "#00c853",
        "CLOSE":      "#ff9800",
        "WAIT":       "#ffd740",
        "AVOID":      "#ff5252",
    }.get(verdict, "#ffd740")


def compute_signal_bar(name: str, raw, score: int, meta: dict) -> dict:
    if raw is None:
        return {"has_data": False}

    span = meta["range_hi"] - meta["range_lo"]
    avoid_pct  = round((meta["range_hi"] - meta["avoid_thresh"])  / span * 100, 1)
    wait_pct   = round((meta["avoid_thresh"] - meta["invest_thresh"]) / span * 100, 1)
    invest_pct = round(100.0 - avoid_pct - wait_pct, 1)

    cursor_pct = (meta["range_hi"] - float(raw)) / span * 100
    cursor_pct = round(max(0.0, min(100.0, cursor_pct)), 1)

    thresh_avoid_pct  = avoid_pct
    thresh_invest_pct = round(avoid_pct + wait_pct, 1)

    dist_invest = abs(float(raw) - meta["invest_thresh"])
    dist_avoid  = abs(float(raw) - meta["avoid_thresh"])

    if score == 100:
        status_class = "st-invest"
        status_text  = "INVEST"
    elif score == 0:
        status_class = "st-avoid"
        status_text  = "AVOID"
    elif dist_invest <= dist_avoid:
        status_class = "st-wait"
        status_text  = f"WAIT · {dist_invest:.2g} from invest"
    else:
        status_class = "st-wait"
        status_text  = f"WAIT · {dist_avoid:.2g} from avoid ⚠️"

    fmt = meta["fmt"]
    return {
        "has_data":          True,
        "avoid_pct":         avoid_pct,
        "wait_pct":          wait_pct,
        "invest_pct":        invest_pct,
        "cursor_pct":        cursor_pct,
        "thresh_avoid_pct":  thresh_avoid_pct,
        "thresh_invest_pct": thresh_invest_pct,
        "edge_left":         fmt.format(meta["range_hi"]),
        "edge_right":        fmt.format(meta["range_lo"]),
        "thresh_avoid_lbl":  fmt.format(meta["avoid_thresh"]),
        "thresh_invest_lbl": fmt.format(meta["invest_thresh"]),
        "status_class":      status_class,
        "status_text":       status_text,
    }


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

    signal_meta = current_score["signal_meta"]

    signals = {}
    for name, data in current_score["signals"].items():
        signals[name] = {
            "display_name":      data["display_name"],
            "reading_formatted": format_reading(name, data["raw"]),
            "bar": compute_signal_bar(
                name,
                data["raw"],
                data["score"],
                signal_meta[name],
            ),
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

    composite = current_score["composite_score"]
    verdict   = current_score["verdict"]

    if composite >= 80:
        distance_text = "You are in the Strong Buy zone"
    elif composite >= 72:
        distance_text = "You are in the Invest Zone"
    else:
        distance_text = f"{72 - composite:.1f} pts from Invest zone"

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        btc_price=btc_price,
        updated_date=current_score["date"],
        composite_score=composite,
        verdict=verdict,
        score_color=get_score_color(verdict),
        distance_text=distance_text,
        signals=signals,
        chart_data_json=json.dumps(chart_data),
        methodology=methodology,
    )

    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard written to docs/index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
