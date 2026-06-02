"""Fetch each configured asset's history into data/{id}_history.csv."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS

DATA_DIR = Path(__file__).parent.parent / "data"


def main():
    DATA_DIR.mkdir(exist_ok=True)
    for cfg in ASSETS:
        print(f"Fetching {cfg.display_name} history...")
        try:
            df = cfg.fetch()
        except Exception as e:  # per-asset isolation: one feed failing won't block others
            print(f"  ERROR fetching {cfg.id}: {e}", file=sys.stderr)
            continue
        out = DATA_DIR / f"{cfg.id}_history.csv"
        df.to_csv(out, index=False)
        print(f"  saved {len(df)} rows to {out.name}")


if __name__ == "__main__":
    main()
