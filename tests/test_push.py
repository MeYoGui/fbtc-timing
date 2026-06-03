import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import gen_vapid


def test_generate_returns_appkey_and_pem():
    app_key, priv_pem = gen_vapid.generate()
    # application server key: base64url, no padding, ~87-88 chars (65-byte point)
    assert isinstance(app_key, str)
    assert "=" not in app_key and "+" not in app_key and "/" not in app_key
    assert 80 <= len(app_key) <= 90
    # private key: unencrypted PKCS8 PEM
    assert priv_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert priv_pem.strip().endswith("-----END PRIVATE KEY-----")


import build_dashboard


def test_notify_entries_shape():
    assets = [
        {
            "id": "bitcoin", "display_name": "Bitcoin",
            "composite": 54.5, "verdict": "CLOSE",
            "trend": {"day": {"delta": 2.1, "spark": [], "arrows": {}}},
            "short_label": "₿ Bitcoin", "accent_color": "#f7931a",
        }
    ]
    entries = build_dashboard._notify_entries(assets)
    assert entries == [
        {"id": "bitcoin", "display_name": "Bitcoin",
         "composite": 54.5, "verdict": "CLOSE", "delta_1d": 2.1}
    ]


import send_push


def test_format_digest_line_up():
    e = {"display_name": "Bitcoin", "composite": 54.5, "verdict": "CLOSE", "delta_1d": 2.1}
    assert send_push.format_digest_line(e) == "Bitcoin 54.5 ↑ +2.1 — CLOSE"


def test_format_digest_line_down():
    e = {"display_name": "Ethereum", "composite": 61.0, "verdict": "CLOSE", "delta_1d": -1.3}
    assert send_push.format_digest_line(e) == "Ethereum 61.0 ↓ -1.3 — CLOSE"


def test_format_digest_line_flat():
    e = {"display_name": "Gold", "composite": 50.0, "verdict": "WAIT", "delta_1d": 0.2}
    assert send_push.format_digest_line(e) == "Gold 50.0 → +0.2 — WAIT"


def test_build_title_single_vs_multi():
    assert send_push.build_title(1) == "Kairos"
    assert send_push.build_title(3) == "Kairos — daily scores"


def test_build_payload():
    entries = [
        {"display_name": "Bitcoin", "composite": 54.5, "verdict": "CLOSE", "delta_1d": 2.1},
        {"display_name": "Gold", "composite": 70.2, "verdict": "INVEST", "delta_1d": 4.0},
    ]
    p = send_push.build_payload(entries)
    assert p["title"] == "Kairos — daily scores"
    assert p["body"] == "Bitcoin 54.5 ↑ +2.1 — CLOSE\nGold 70.2 ↑ +4.0 — INVEST"
    assert p["url"] == "/fbtc-timing/"
