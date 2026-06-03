"""Send the daily Web Push digest to each registered device.

Reads the ephemeral notify.json (written by build_dashboard.py) and the
PUSH_SUBSCRIPTIONS / VAPID_* environment (GitHub Actions secrets), then pushes a
single digest notification per device. Resilient: never raises, always exits 0,
so a push failure can't block the daily deploy.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from pywebpush import webpush, WebPushException

ROOT = Path(__file__).parent.parent
NOTIFY_PATH = ROOT / "notify.json"
DASHBOARD_URL = "/fbtc-timing/"


def format_digest_line(entry: dict) -> str:
    """One line per ticker, e.g. 'Bitcoin 54.5 ↑ +2.1 — CLOSE'."""
    d = entry["delta_1d"]
    arrow = "↑" if d > 0.5 else "↓" if d < -0.5 else "→"
    return f"{entry['display_name']} {entry['composite']:.1f} {arrow} {d:+.1f} — {entry['verdict']}"


def build_title(n_assets: int) -> str:
    return "Kairos" if n_assets == 1 else "Kairos — daily scores"


def build_payload(entries: list) -> dict:
    return {
        "title": build_title(len(entries)),
        "body": "\n".join(format_digest_line(e) for e in entries),
        "url": DASHBOARD_URL,
    }
