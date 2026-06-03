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


def load_subscriptions() -> list:
    raw = os.environ.get("PUSH_SUBSCRIPTIONS", "").strip()
    if not raw:
        return []
    try:
        subs = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"PUSH_SUBSCRIPTIONS is not valid JSON: {e}", file=sys.stderr)
        return []
    return subs if isinstance(subs, list) else []


def _short(sub: dict) -> str:
    return (sub.get("endpoint", "") or "")[:48]


def send_all(payload: dict, subscriptions: list, vapid_private_key: str, vapid_subject: str) -> None:
    """Send the payload to every subscription. Logs and continues on any failure."""
    data = json.dumps(payload)
    # pywebpush accepts a PEM file path for vapid_private_key; write the secret to a temp file.
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(vapid_private_key)
        pem_path = fh.name
    try:
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info=sub,
                    data=data,
                    vapid_private_key=pem_path,
                    vapid_claims={"sub": vapid_subject},
                )
                print(f"sent to {_short(sub)}")
            except WebPushException as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (404, 410):
                    print(f"  device gone (rotated/expired): {_short(sub)} [{code}]", file=sys.stderr)
                else:
                    print(f"  send failed: {_short(sub)} [{code}]: {e}", file=sys.stderr)
            except Exception as e:  # network/timeout/bad-key — never let one device abort the rest
                print(f"  send error: {_short(sub)}: {e}", file=sys.stderr)
    finally:
        os.unlink(pem_path)


def main() -> None:
    if not NOTIFY_PATH.exists():
        print("notify.json missing — run build_dashboard.py first; skipping", file=sys.stderr)
        return
    try:
        entries = json.loads(NOTIFY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"could not read notify.json ({e}); skipping", file=sys.stderr)
        return
    if not entries:
        print("no assets in notify.json; nothing to send")
        return
    subscriptions = load_subscriptions()
    if not subscriptions:
        print("no subscribers; nothing to send")
        return
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    vapid_subject = os.environ.get("VAPID_SUBJECT", "").strip()
    if not vapid_private_key or not vapid_subject:
        print("VAPID_PRIVATE_KEY / VAPID_SUBJECT not set; skipping", file=sys.stderr)
        return
    payload = build_payload(entries)
    send_all(payload, subscriptions, vapid_private_key, vapid_subject)


if __name__ == "__main__":
    main()
