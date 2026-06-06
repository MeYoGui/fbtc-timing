import json
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
DOCS_DIR = ROOT / "docs"
NOTIFY_PATH = ROOT / "notify.json"

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
    if name == "mayer_multiple":
        return f"{raw:.2f}× 200DMA"
    if name == "eth_btc_ratio":
        return f"{raw:.2f} z (ETH/BTC)"
    return f"{raw:.3f}"


def get_score_color(verdict: str) -> str:
    return {
        "STRONG BUY":  "#00e676",
        "BUY":         "#00c853",
        "HOLD":        "#ffd740",
        "SELL":        "#ff9800",
        "TAKE PROFIT": "#ff5252",
    }.get(verdict, "#ffd740")


def compute_signal_bar(name: str, raw, score: int, meta: dict) -> dict:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
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


def compute_historical_scores(signals_df: pd.DataFrame, weights: dict, signal_names: list = None) -> pd.Series:
    if signal_names is None:
        signal_names = list(SIGNAL_DISPLAY.keys())   # legacy Bitcoin default
    w = np.array([weights["signals"][s]["weight"] for s in signal_names])
    total_w = w.sum()
    if total_w == 0:
        return pd.Series(np.zeros(len(signals_df)), index=signals_df.index)
    scores = signals_df[signal_names].values @ w / total_w
    return pd.Series(scores, index=signals_df.index)


def _score_to_verdict(score: float) -> str:
    if score >= 80: return "STRONG BUY"
    if score >= 60: return "BUY"
    if score >= 40: return "HOLD"
    if score >= 20: return "SELL"
    return "TAKE PROFIT"


def _spark_label(date: pd.Timestamp, window: str) -> str:
    month_day = f"{date.strftime('%b')} {date.day}"
    if window == "week":
        return f"wk {month_day}"
    if window == "month":
        return date.strftime("%b %Y")
    return month_day  # day


def build_trend_data(signals_df: pd.DataFrame, weights: dict, signal_names: list = None) -> dict:
    """Pre-compute Day/Week/Month trend data for embedding in the dashboard HTML.

    Returns a dict keyed by window ("day", "week", "month"), each containing:
      delta  – float, composite score change from N periods ago (positive = improving)
      spark  – list of up to 7 dicts {"score", "label", "verdict"}, oldest first
      arrows – dict signal_name -> int (1=up, 0=flat, -1=down)
    """
    if signal_names is None:
        signal_names = list(SIGNAL_DISPLAY.keys())   # legacy Bitcoin default
    df = signals_df.copy()
    df["composite_score"] = compute_historical_scores(df, weights, signal_names)
    df = df.set_index("date").sort_index()

    today_composite = float(df["composite_score"].iloc[-1])
    today_date = df.index[-1]
    today_signals = {sig: int(df[sig].iloc[-1]) for sig in signal_names}

    spark_frames = {
        "day":   df.resample("D").last().dropna(subset=["composite_score"]),
        "week":  df.resample("W").last().dropna(subset=["composite_score"]),
        "month": df.resample("ME").last().dropna(subset=["composite_score"]),
    }
    lookback_days = {"day": 1, "week": 7, "month": 30}

    result = {}
    for win in ("day", "week", "month"):
        lookback_date = today_date - pd.Timedelta(days=lookback_days[win])
        prior = df[df.index <= lookback_date]

        if len(prior) > 0:
            ref = prior.iloc[-1]
            delta = round(today_composite - float(ref["composite_score"]), 1)
            arrows = {
                sig: (1 if today_signals[sig] > int(ref[sig])
                      else -1 if today_signals[sig] < int(ref[sig])
                      else 0)
                for sig in signal_names
            }
        else:
            delta = 0.0
            arrows = {sig: 0 for sig in signal_names}

        spark_scores = spark_frames[win]["composite_score"].tail(7)
        entries = list(spark_scores.items())
        spark = [
            {
                "score":   round(float(s), 1),
                "label":   _spark_label(today_date if i == len(entries) - 1 else d, win),
                "verdict": _score_to_verdict(float(s)),
            }
            for i, (d, s) in enumerate(entries)
        ]

        result[win] = {"delta": delta, "spark": spark, "arrows": arrows}

    return result


def build_chart_data(price_df: pd.DataFrame, signals_df: pd.DataFrame, weights: dict, signal_names: list = None) -> dict:
    if signal_names is None:
        signal_names = list(SIGNAL_DISPLAY.keys())   # legacy Bitcoin default
    score_series = compute_historical_scores(signals_df, weights, signal_names)
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


def _assemble_asset(cfg) -> dict:
    """Build the full client-render blob for one asset, or None if data is missing."""
    score_path = DATA_DIR / f"{cfg.id}_score.json"
    hist_path = DATA_DIR / f"{cfg.id}_history.csv"
    sig_path = DATA_DIR / f"{cfg.id}_signal_history.csv"
    weights_path = DATA_DIR / f"{cfg.id}_weights.json"
    if not all(p.exists() for p in (score_path, hist_path, sig_path, weights_path)):
        print(f"  skip {cfg.id}: missing data files", file=sys.stderr)
        return None

    current_score = json.loads(score_path.read_text())
    weights = json.loads(weights_path.read_text())
    price_df = pd.read_csv(hist_path)
    price_df["date"] = pd.to_datetime(price_df["date"])
    signals_df = pd.read_csv(sig_path)
    signals_df["date"] = pd.to_datetime(signals_df["date"])
    signal_names = [s.key for s in cfg.signals]

    signal_meta = current_score["signal_meta"]
    signals = []
    for spec in cfg.signals:
        data = current_score["signals"][spec.key]
        signals.append({
            "key": spec.key,
            "display_name": data["display_name"],
            "reading": format_reading(spec.key, data["raw"]),
            "bar": compute_signal_bar(spec.key, data["raw"], data["score"], signal_meta[spec.key]),
        })

    composite = current_score["composite_score"]
    verdict = current_score["verdict"]
    sell_composite   = current_score.get("sell_composite", 0.0)
    sell_verdict     = current_score.get("sell_verdict", "LOW")
    spectrum_pos     = current_score.get("spectrum_pos", round(50 + composite / 2, 1))
    spectrum_verdict = current_score.get("spectrum_verdict", verdict)

    if spectrum_pos >= 80:
        distance_text = "Strong Buy zone"
    elif spectrum_pos >= 60:
        distance_text = f"{80 - spectrum_pos:.1f} pts from Strong Buy"
    elif spectrum_pos >= 40:
        distance_text = f"{60 - spectrum_pos:.1f} pts from Buy zone"
    elif spectrum_pos >= 20:
        distance_text = f"{spectrum_pos - 20:.1f} pts into Sell zone"
    else:
        distance_text = "Take profit zone"

    current_price = price_df.dropna(subset=["price"])["price"].iloc[-1]

    methodology = [
        {
            "display_name": next(s.display_name for s in cfg.signals if s.key == name),
            "weight": weights["signals"][name]["weight"],
            "precision": weights["signals"][name]["precision"],
            "recall": weights["signals"][name]["recall"],
            "f1": weights["signals"][name]["f1"],
        }
        for name in (s.key for s in cfg.signals)
    ]

    return {
        "id":               cfg.id,
        "display_name":     cfg.display_name,
        "short_label":      cfg.short_label,
        "accent_color":     cfg.accent_color,
        "price_unit":       cfg.price_unit,
        "price":            round(float(current_price)),
        "composite":        composite,
        "verdict":          verdict,
        "sell_composite":   sell_composite,
        "sell_verdict":     sell_verdict,
        "spectrum_pos":     spectrum_pos,
        "spectrum_verdict": spectrum_verdict,
        "score_color":      get_score_color(spectrum_verdict),
        "distance_text":    distance_text,
        "signals":          signals,
        "chart":            build_chart_data(price_df, signals_df, weights, signal_names),
        "trend":            build_trend_data(signals_df, weights, signal_names),
        "methodology":      methodology,
    }


def _notify_entries(assets: list) -> list:
    return [
        {
            "id":               a["id"],
            "display_name":     a["display_name"],
            "composite":        a["composite"],
            "sell_composite":   a.get("sell_composite", 0.0),
            "spectrum_pos":     a.get("spectrum_pos", round(50 + a["composite"] / 2, 1)),
            "spectrum_verdict": a.get("spectrum_verdict", a.get("verdict", "HOLD")),
            "delta_1d":         a["trend"]["day"]["delta"],
        }
        for a in assets
    ]


def main():
    updated_at = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M %Z")
    assets = []
    for cfg in ASSETS:
        blob = _assemble_asset(cfg)
        if blob is not None:
            assets.append(blob)
    if not assets:
        raise RuntimeError("no assets could be assembled — aborting dashboard build")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        updated_at=updated_at,
        assets_json=json.dumps(assets),
        default_asset=assets[0]["id"],
    )
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    NOTIFY_PATH.write_text(json.dumps(_notify_entries(assets)), encoding="utf-8")
    print(f"Dashboard written to docs/index.html ({len(html):,} bytes; {len(assets)} asset(s))")


if __name__ == "__main__":
    main()
