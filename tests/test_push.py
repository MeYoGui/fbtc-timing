import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import gen_vapid
from pywebpush import WebPushException


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
         "composite": 54.5, "sell_composite": 0.0,
         "spectrum_pos": 77.2, "spectrum_verdict": "CLOSE", "delta_1d": 2.1}
    ]


import send_push


def test_format_digest_line_up():
    e = {"display_name": "Bitcoin", "spectrum_pos": 54.5, "spectrum_verdict": "CLOSE", "delta_1d": 2.1}
    assert send_push.format_digest_line(e) == "Bitcoin 54.5 ↑ +2.1 — CLOSE"


def test_format_digest_line_down():
    e = {"display_name": "Ethereum", "spectrum_pos": 61.0, "spectrum_verdict": "CLOSE", "delta_1d": -1.3}
    assert send_push.format_digest_line(e) == "Ethereum 61.0 ↓ -1.3 — CLOSE"


def test_format_digest_line_flat():
    e = {"display_name": "Gold", "spectrum_pos": 50.0, "spectrum_verdict": "WAIT", "delta_1d": 0.2}
    assert send_push.format_digest_line(e) == "Gold 50.0 → +0.2 — WAIT"


def test_build_title_single_vs_multi():
    assert send_push.build_title(1) == "Kairos"
    assert send_push.build_title(3) == "Kairos — daily scores"


def test_build_payload():
    entries = [
        {"display_name": "Bitcoin", "spectrum_pos": 54.5, "spectrum_verdict": "CLOSE", "delta_1d": 2.1},
        {"display_name": "Gold", "spectrum_pos": 70.2, "spectrum_verdict": "INVEST", "delta_1d": 4.0},
    ]
    p = send_push.build_payload(entries)
    assert p["title"] == "Kairos — daily scores"
    assert p["body"] == "Bitcoin 54.5 ↑ +2.1 — CLOSE\nGold 70.2 ↑ +4.0 — INVEST"
    assert p["url"] == "/fbtc-timing/"


from types import SimpleNamespace


def test_load_subscriptions_empty(monkeypatch):
    monkeypatch.delenv("PUSH_SUBSCRIPTIONS", raising=False)
    assert send_push.load_subscriptions() == []


def test_load_subscriptions_parses_json(monkeypatch):
    monkeypatch.setenv("PUSH_SUBSCRIPTIONS", '[{"endpoint":"https://x/1","keys":{}}]')
    subs = send_push.load_subscriptions()
    assert subs == [{"endpoint": "https://x/1", "keys": {}}]


def test_send_all_calls_webpush_per_subscription(monkeypatch):
    calls = []
    monkeypatch.setattr(send_push, "webpush", lambda **kw: calls.append(kw))
    subs = [{"endpoint": "https://x/1", "keys": {}}, {"endpoint": "https://x/2", "keys": {}}]
    send_push.send_all({"title": "T", "body": "B", "url": "/u"}, subs, "PEM", "mailto:a@b.c")
    assert len(calls) == 2
    assert calls[0]["vapid_claims"] == {"sub": "mailto:a@b.c"}


def test_send_all_swallows_410(monkeypatch):
    def boom(**kw):
        raise WebPushException("gone", response=SimpleNamespace(status_code=410))
    monkeypatch.setattr(send_push, "webpush", boom)
    # must not raise
    send_push.send_all({"title": "T", "body": "B", "url": "/u"},
                       [{"endpoint": "https://x/1", "keys": {}}], "PEM", "mailto:a@b.c")


def test_format_digest_line_buy():
    from send_push import format_digest_line
    entry = {"display_name": "Bitcoin", "spectrum_pos": 69.7, "spectrum_verdict": "BUY", "delta_1d": 3.2}
    line = format_digest_line(entry)
    assert line == "Bitcoin 69.7 ↑ +3.2 — BUY"


def test_format_digest_line_take_profit_flag():
    from send_push import format_digest_line
    entry = {"display_name": "Ethereum", "spectrum_pos": 22.4, "spectrum_verdict": "TAKE PROFIT", "delta_1d": -4.1}
    line = format_digest_line(entry)
    assert "TAKE PROFIT ⚠️" in line


def test_format_digest_line_strong_buy_flag():
    from send_push import format_digest_line
    entry = {"display_name": "Bitcoin", "spectrum_pos": 83.1, "spectrum_verdict": "STRONG BUY", "delta_1d": 5.0}
    line = format_digest_line(entry)
    assert "STRONG BUY ✓" in line


def test_format_digest_line_sell_flag():
    from send_push import format_digest_line
    entry = {"display_name": "Bitcoin", "spectrum_pos": 30.0, "spectrum_verdict": "SELL", "delta_1d": -2.0}
    line = format_digest_line(entry)
    assert "SELL ⚠️" in line
