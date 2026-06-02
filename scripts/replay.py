"""
Simulate the daily GHA pipeline as of a specific historical date.

Usage:
    python scripts/replay.py --date 2026-05-29

Filters btc_history.csv to the target date, runs compute_signals →
score → build_dashboard exactly as the workflow does, then restores
all original data files so the working state is unchanged.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

BACKED_UP = [
    DATA_DIR / "bitcoin_history.csv",
    DATA_DIR / "bitcoin_signal_history.csv",
    DATA_DIR / "bitcoin_current_signals.json",
    DATA_DIR / "bitcoin_score.json",
]


def main():
    parser = argparse.ArgumentParser(description="Replay the GHA pipeline for a historical date.")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    args = parser.parse_args()

    df = pd.read_csv(DATA_DIR / "bitcoin_history.csv")
    if args.date not in df["date"].values:
        print(f"Error: {args.date} not found in bitcoin_history.csv", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Replaying pipeline as of {args.date} ===\n")

    backups = {}
    for path in BACKED_UP:
        if path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            shutil.copy(path, bak)
            backups[path] = bak

    try:
        filtered = df[df["date"] <= args.date].copy()
        filtered.to_csv(DATA_DIR / "bitcoin_history.csv", index=False)
        print(f"bitcoin_history.csv filtered to {len(filtered)} rows (up to {args.date})\n")

        for script in ["compute_signals", "score", "build_dashboard"]:
            print(f"--- {script}.py ---")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / f"{script}.py")],
                capture_output=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"{script}.py exited with code {result.returncode}")
            print()

        replay_html = DOCS_DIR / f"replay-{args.date}.html"
        shutil.copy(DOCS_DIR / "index.html", replay_html)
        print(f"Replay dashboard saved to {replay_html.name}")

    finally:
        for path, bak in backups.items():
            shutil.copy(bak, path)
            bak.unlink()
        print("Original data files restored.")

    print(f"\nReplay dashboard: docs/replay-{args.date}.html")


if __name__ == "__main__":
    main()
