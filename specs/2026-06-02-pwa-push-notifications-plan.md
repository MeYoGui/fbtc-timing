# PWA Daily Push Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send a daily Web Push notification to 2–3 personal devices containing each configured ticker's score, day-delta, and verdict — sent by the existing GitHub Actions workflow, with no new infrastructure.

**Architecture:** Self-sent Web Push (VAPID). `build_dashboard.py` emits an ephemeral `notify.json`; `send_push.py` (run as the last, non-blocking step of `daily.yml`) reads it plus a `PUSH_SUBSCRIPTIONS` secret and pushes a single digest notification per device via `pywebpush`. Devices are registered once through an unlinked `enable-alerts.html` page; the service worker gains `push`/`notificationclick` handlers.

**Tech Stack:** Python 3.11 (pywebpush, cryptography), vanilla JS service worker + Web Push API, GitHub Actions.

**Reference:** Design spec `specs/2026-06-02-pwa-push-notifications-design.md`. Notification "format A": `Bitcoin 54.5 ↑ +2.1 — CLOSE`.

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | Add `pywebpush` |
| `.gitignore` | Ignore the ephemeral `notify.json` |
| `scripts/gen_vapid.py` | One-time: generate VAPID keypair (public app-server key + private PEM) |
| `scripts/build_dashboard.py` | Also emit `notify.json` (compact per-asset digest source) |
| `scripts/send_push.py` | Build digest + send Web Push to each subscription (resilient) |
| `docs/sw.js` | Add `push` + `notificationclick` handlers |
| `docs/enable-alerts.html` | Unlinked per-device setup page (subscribe + copy/share blob) |
| `.github/workflows/daily.yml` | Deploy first, then a non-blocking send step |
| `tests/test_push.py` | Unit tests for notify entries + send_push pure functions + send loop |

**Conventions:** `notify.json` lives at repo root (git-ignored, consumed in-job). Secrets: `VAPID_PRIVATE_KEY` (PEM), `VAPID_SUBJECT` (`mailto:`), `PUSH_SUBSCRIPTIONS` (JSON array). The dashboard URL path is `/fbtc-timing/`.

---

## Task 1: Add dependency + git-ignore notify.json

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Add pywebpush to requirements.txt**

Append `pywebpush>=1.14` as a new line at the end of `requirements.txt` (it pulls in `cryptography`, `py-vapid`, `http-ece`).

- [ ] **Step 2: Install it**

Run: `pip install -r requirements.txt`
Expected: installs `pywebpush`, `py-vapid`, `http-ece` (cryptography already present).

- [ ] **Step 3: Ignore notify.json**

In `.gitignore`, under the `# Local replay artifacts` section, add a new line:
```
# Ephemeral push digest (consumed in-job, never committed)
notify.json
```

- [ ] **Step 4: Verify the existing suite still passes**

Run: `python -m pytest -q`
Expected: 47 passed.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "build: add pywebpush dependency; git-ignore ephemeral notify.json"
```

---

## Task 2: `scripts/gen_vapid.py` — one-time key generation

Generates the VAPID keypair using `cryptography` directly (precise, no format ambiguity). The **public app-server key** (base64url uncompressed point) goes into `enable-alerts.html`; the **private PEM** becomes the `VAPID_PRIVATE_KEY` secret.

**Files:**
- Create: `scripts/gen_vapid.py`
- Test: `tests/test_push.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_push.py` with:

```python
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
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_push.py -k generate -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gen_vapid'`.

- [ ] **Step 3: Implement gen_vapid.py**

Create `scripts/gen_vapid.py`:

```python
"""One-time VAPID keypair generation for Web Push.

Run once:  python scripts/gen_vapid.py

Prints the application server key (paste into docs/enable-alerts.html) and the
private key PEM (store as the VAPID_PRIVATE_KEY GitHub secret).

GENERATE ONCE, NEVER ROTATE: regenerating invalidates every existing
subscription (push services reject a VAPID key that doesn't match the one used
at subscribe time).
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate() -> tuple[str, str]:
    """Return (application_server_key_base64url, private_key_pem)."""
    key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_point = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    app_server_key = base64.urlsafe_b64encode(pub_point).rstrip(b"=").decode()
    return app_server_key, priv_pem


def main() -> None:
    app_key, priv_pem = generate()
    print("\n=== applicationServerKey (paste into docs/enable-alerts.html) ===\n")
    print(app_key)
    print("\n=== VAPID_PRIVATE_KEY (store as a GitHub Actions secret, full PEM) ===\n")
    print(priv_pem)
    print("Also set VAPID_SUBJECT to a mailto: address, e.g. mailto:you@example.com")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `python -m pytest tests/test_push.py -k generate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/gen_vapid.py tests/test_push.py
git commit -m "feat: add one-time VAPID key generator (gen_vapid.py)"
```

---

## Task 3: `build_dashboard.py` emits `notify.json`

Add a pure `_notify_entries(assets)` helper and write `notify.json` at the end of `main()`. Reuses values already in each assembled blob (`composite`, `verdict`, and the Day-trend delta), so the notification delta matches the dashboard exactly.

**Files:**
- Modify: `scripts/build_dashboard.py`
- Test: `tests/test_push.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_push.py`:

```python
import build_dashboard


def test_notify_entries_shape():
    assets = [
        {
            "id": "bitcoin", "display_name": "Bitcoin",
            "composite": 54.5, "verdict": "CLOSE",
            "trend": {"day": {"delta": 2.1, "spark": [], "arrows": {}}},
            # other blob keys ignored by _notify_entries
            "short_label": "₿ Bitcoin", "accent_color": "#f7931a",
        }
    ]
    entries = build_dashboard._notify_entries(assets)
    assert entries == [
        {"id": "bitcoin", "display_name": "Bitcoin",
         "composite": 54.5, "verdict": "CLOSE", "delta_1d": 2.1}
    ]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_push.py -k notify_entries -v`
Expected: FAIL with `AttributeError: module 'build_dashboard' has no attribute '_notify_entries'`.

- [ ] **Step 3: Add the helper and write notify.json**

In `scripts/build_dashboard.py`, the imports/constants block currently defines `DATA_DIR`, `TEMPLATES_DIR`, `DOCS_DIR`. Add a repo-root constant near them:

```python
ROOT = Path(__file__).parent.parent
NOTIFY_PATH = ROOT / "notify.json"
```

Add this helper just above `def main():`:

```python
def _notify_entries(assets: list) -> list:
    """Compact per-asset digest for the daily push (id, name, composite, verdict, day-delta)."""
    return [
        {
            "id": a["id"],
            "display_name": a["display_name"],
            "composite": a["composite"],
            "verdict": a["verdict"],
            "delta_1d": a["trend"]["day"]["delta"],
        }
        for a in assets
    ]
```

In `main()`, immediately after `(DOCS_DIR / "index.html").write_text(html, encoding="utf-8")` and before the final `print(...)`, add:

```python
    NOTIFY_PATH.write_text(json.dumps(_notify_entries(assets)), encoding="utf-8")
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `python -m pytest tests/test_push.py -k notify_entries -v`
Expected: PASS.

- [ ] **Step 5: Verify the real build writes notify.json**

Run: `python scripts/build_dashboard.py`
Then: `python -c "import json; d=json.load(open('notify.json')); print(d)"`
Expected: a list with one entry, e.g. `[{'id': 'bitcoin', 'display_name': 'Bitcoin', 'composite': 54.5, 'verdict': 'CLOSE', 'delta_1d': <float>}]`.

- [ ] **Step 6: Confirm notify.json is git-ignored**

Run: `git status --short`
Expected: `notify.json` does NOT appear (ignored by Task 1). Only `docs/index.html` may show as modified — discard it: `git checkout -- docs/index.html`.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_dashboard.py tests/test_push.py
git commit -m "feat: build_dashboard emits ephemeral notify.json digest"
```

---

## Task 4: `send_push.py` — payload builders (pure functions)

**Files:**
- Create: `scripts/send_push.py`
- Test: `tests/test_push.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_push.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_push.py -k "digest or title or payload" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'send_push'`.

- [ ] **Step 3: Create send_push.py with the pure functions**

Create `scripts/send_push.py`:

```python
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
```

- [ ] **Step 4: Run to confirm pass**

Run: `python -m pytest tests/test_push.py -k "digest or title or payload" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/send_push.py tests/test_push.py
git commit -m "feat: send_push digest payload builders"
```

---

## Task 5: `send_push.py` — subscription loading, send loop, main

**Files:**
- Modify: `scripts/send_push.py`
- Test: `tests/test_push.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_push.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_push.py -k "subscriptions or send_all" -v`
Expected: FAIL with `AttributeError: module 'send_push' has no attribute 'load_subscriptions'`.

- [ ] **Step 3: Implement loading, send loop, and main**

Append to `scripts/send_push.py`:

```python
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
    finally:
        os.unlink(pem_path)


def main() -> None:
    if not NOTIFY_PATH.exists():
        print("notify.json missing — run build_dashboard.py first; skipping", file=sys.stderr)
        return
    entries = json.loads(NOTIFY_PATH.read_text(encoding="utf-8"))
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
```

- [ ] **Step 4: Run the send_push tests**

Run: `python -m pytest tests/test_push.py -v`
Expected: PASS (all push tests).

- [ ] **Step 5: Dry-run main with no subscribers (no-op, exit 0)**

Run: `python scripts/build_dashboard.py && python scripts/send_push.py`
Expected: prints `no subscribers; nothing to send` and exits 0 (PUSH_SUBSCRIPTIONS unset locally).

- [ ] **Step 6: Full suite**

Run: `python -m pytest -q`
Expected: all pass (47 prior + the new push tests).

- [ ] **Step 7: Commit**

```bash
git add scripts/send_push.py tests/test_push.py
git commit -m "feat: send_push subscription loading, resilient send loop, and main"
```

---

## Task 6: Service worker — `push` + `notificationclick`

**Files:**
- Modify: `docs/sw.js`

- [ ] **Step 1: Append the handlers**

The current `docs/sw.js` has only `install` + `activate` listeners. Append these two handlers to the end of the file (do not remove the existing ones; caching behavior is unchanged):

```javascript

// ── Web Push ──────────────────────────────────────────────────────────────
self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (e) { payload = {}; }
  const title = payload.title || 'Kairos';
  const options = {
    body: payload.body || '',
    icon: '/fbtc-timing/icons/icon-192.png',
    data: { url: payload.url || '/fbtc-timing/' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/fbtc-timing/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const c of clients) {
        if (c.url.includes('/fbtc-timing/') && 'focus' in c) return c.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
```

- [ ] **Step 2: Sanity-check the file is valid JS**

Run: `node --check docs/sw.js` (if Node is available) — Expected: no output (valid). If Node is unavailable, visually confirm the braces/parens balance.

- [ ] **Step 3: Commit**

```bash
git add docs/sw.js
git commit -m "feat: service worker push + notificationclick handlers"
```

(End-to-end browser verification happens in Task 9 after a VAPID key exists.)

---

## Task 7: `docs/enable-alerts.html` — per-device setup page

A standalone, unlinked page matching the validated mockup: a Kairos-branded page with an Enable button (+ iOS instructions), and an after-state showing the subscription blob with Copy + Email/Share.

**Files:**
- Create: `docs/enable-alerts.html`

- [ ] **Step 1: Create the page**

Create `docs/enable-alerts.html`. Note the `VAPID_PUBLIC_KEY` constant near the top of the script — it is filled in Task 9 Step 2 with the value printed by `gen_vapid.py` (left as the literal marker for now):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kairos — Enable alerts</title>
  <link rel="manifest" href="/fbtc-timing/manifest.json">
  <meta name="theme-color" content="#0d0d0d">
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,-apple-system,sans-serif;background:#0d0d0d;color:#d0d0d0;max-width:480px;margin:0 auto;padding:2rem 1.5rem}
    .kwm{font-size:1.2rem;font-weight:700;letter-spacing:.08em;margin-bottom:1.8rem}
    .kwm .k{color:#ff6b3d}.kwm .a{color:#ffa033}.kwm .i{color:#ffd740;text-shadow:0 0 7px rgba(255,215,64,.85)}.kwm .r{color:#80d94a}.kwm .o{color:#00c853}.kwm .s{color:#00c853}
    h1{font-size:1.25rem;color:#f0f0f0;margin-bottom:.6rem}
    p{color:#9a9aa6;font-size:.92rem;line-height:1.55;margin-bottom:1.1rem}
    button{display:block;width:100%;text-align:center;border:none;border-radius:10px;padding:14px;font-size:1rem;font-weight:700;cursor:pointer}
    .primary{background:#1f6f43;color:#eafff1}
    .secondary{background:#1a1a1a;color:#cfcfd6;border:1px solid #2a2a2a;margin-top:.6rem}
    .ios{margin-top:1.2rem;padding:12px 13px;background:#141414;border:1px solid #232323;border-radius:9px;color:#8a8a96;font-size:.8rem;line-height:1.5}
    .ios b{color:#c9c9d2}
    .ok{color:#46d17f;font-weight:700;margin-bottom:.7rem}
    .err{color:#ff6b6b;font-weight:600;margin-top:.8rem}
    .blob{background:#08080a;border:1px solid #242424;border-radius:8px;padding:11px;color:#7fd1a3;font-family:ui-monospace,Menlo,monospace;font-size:.72rem;line-height:1.45;white-space:pre-wrap;word-break:break-all;max-height:180px;overflow:auto;margin-bottom:.6rem}
    .hidden{display:none}
    .row{display:flex;gap:.6rem}
    .row button{margin-top:0}
  </style>
</head>
<body>
  <div class="kwm"><span class="k">K</span><span class="a">A</span><span class="i">I</span><span class="r">R</span><span class="o">O</span><span class="s">S</span></div>

  <div id="setup">
    <h1>Enable daily alerts</h1>
    <p>Get one notification each morning with the current score &amp; verdict for every ticker. This registers <b style="color:#c9c9d2">this device</b> only.</p>
    <button id="enable" class="primary">🔔 Enable daily alerts</button>
    <p id="error" class="err hidden"></p>
    <div class="ios"><b>On iPhone/iPad:</b> first tap <b>Share → Add to Home Screen</b>, open Kairos from your home screen, then return here and tap Enable. (iOS 16.4+)</div>
  </div>

  <div id="done" class="hidden">
    <p class="ok">✓ This device is subscribed</p>
    <p>Copy the code below and send it to yourself, then add it to the project's <b style="color:#c9c9d2">PUSH_SUBSCRIPTIONS</b> secret (a JSON array).</p>
    <div id="blob" class="blob"></div>
    <div class="row">
      <button id="copy" class="primary">📋 Copy</button>
      <button id="share" class="secondary">✉️ Email / Share</button>
    </div>
  </div>

  <script>
    // Filled in Task 9 with the output of `python scripts/gen_vapid.py`.
    const VAPID_PUBLIC_KEY = "REPLACE_WITH_APPLICATION_SERVER_KEY";

    function urlBase64ToUint8Array(base64String) {
      const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
      const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
      const raw = atob(base64);
      const out = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
      return out;
    }

    function showError(msg) {
      const el = document.getElementById("error");
      el.textContent = msg;
      el.classList.remove("hidden");
    }

    let subJson = "";

    document.getElementById("enable").addEventListener("click", async () => {
      try {
        if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
          return showError("This browser doesn't support push notifications.");
        }
        const perm = await Notification.requestPermission();
        if (perm !== "granted") return showError("Notification permission was not granted.");
        const reg = await navigator.serviceWorker.register("/fbtc-timing/sw.js");
        await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
        });
        subJson = JSON.stringify(sub.toJSON(), null, 2);
        document.getElementById("blob").textContent = subJson;
        document.getElementById("setup").classList.add("hidden");
        document.getElementById("done").classList.remove("hidden");
      } catch (e) {
        showError("Could not subscribe: " + e.message);
      }
    });

    document.getElementById("copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(subJson); alert("Copied."); }
      catch (e) { alert("Copy failed — select the text manually."); }
    });

    document.getElementById("share").addEventListener("click", async () => {
      if (navigator.share) {
        try { await navigator.share({ title: "Kairos push subscription", text: subJson }); return; }
        catch (e) { /* fall through to mailto */ }
      }
      window.location.href =
        "mailto:?subject=" + encodeURIComponent("Kairos push subscription") +
        "&body=" + encodeURIComponent(subJson);
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add docs/enable-alerts.html
git commit -m "feat: unlinked enable-alerts setup page for per-device subscription"
```

---

## Task 8: Workflow integration — `daily.yml`

Deploy the dashboard first, then send notifications as a final non-blocking step.

**Files:**
- Modify: `.github/workflows/daily.yml`

- [ ] **Step 1: Add the send step**

In `.github/workflows/daily.yml`, after the existing `Commit and push updates` step (the last step in the `update` job), append a new step:

```yaml
      - name: Send push notifications
        continue-on-error: true
        env:
          VAPID_PRIVATE_KEY: ${{ secrets.VAPID_PRIVATE_KEY }}
          VAPID_SUBJECT: ${{ secrets.VAPID_SUBJECT }}
          PUSH_SUBSCRIPTIONS: ${{ secrets.PUSH_SUBSCRIPTIONS }}
        run: python scripts/send_push.py
```

This runs after `build_dashboard.py` (which wrote `notify.json` earlier in the job) and after the commit/push, so a push failure can never block the deploy. No other lines change (`0 12 * * *` cron and `git add data/ docs/index.html` stay as-is).

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml')); print('daily.yml OK')"`
Expected: `daily.yml OK`. (If PyYAML isn't installed: `pip install pyyaml` first, or visually confirm indentation matches the surrounding steps.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily.yml
git commit -m "ci: send daily push notifications after deploy (non-blocking)"
```

---

## Task 9: One-time setup runbook + final verification

This task is the operator runbook (secrets, key, device capture) plus a final automated check. The code is complete after Task 8; these steps wire up the live secrets and verify end-to-end.

**Files:**
- Modify: `docs/enable-alerts.html` (insert the real public key)

- [ ] **Step 1: Generate the VAPID keypair (once)**

Run: `python scripts/gen_vapid.py`
Copy the printed **applicationServerKey** and the **private key PEM**.

- [ ] **Step 2: Insert the public key into the setup page**

In `docs/enable-alerts.html`, replace `REPLACE_WITH_APPLICATION_SERVER_KEY` with the applicationServerKey from Step 1. Commit:
```bash
git add docs/enable-alerts.html
git commit -m "chore: set VAPID application server key in enable-alerts page"
```

- [ ] **Step 3: Set the GitHub Actions secrets**

In the repo Settings → Secrets and variables → Actions, add:
- `VAPID_PRIVATE_KEY` = the full PEM from Step 1 (including the BEGIN/END lines).
- `VAPID_SUBJECT` = `mailto:<your email>`.
- `PUSH_SUBSCRIPTIONS` = `[]` for now (filled in Step 5).

- [ ] **Step 4: Deploy the pages (push to main)**

Push the committed changes so `enable-alerts.html` + the updated `sw.js` are live on GitHub Pages. Wait ~2 minutes.

- [ ] **Step 5: Register each device (2–3 times)**

On each device: open `https://meyogui.github.io/fbtc-timing/enable-alerts.html` (on iOS: Add the dashboard to Home Screen first, open the installed app, then navigate to this page within it). Tap **Enable**, then **Copy/Email** the blob to yourself. Collect the 2–3 blobs into a JSON array and update the `PUSH_SUBSCRIPTIONS` secret, e.g.:
```json
[ {"endpoint":"https://...","keys":{"p256dh":"...","auth":"..."}},
  {"endpoint":"https://...","keys":{"p256dh":"...","auth":"..."}} ]
```

- [ ] **Step 6: End-to-end test (manual)**

Trigger the workflow: GitHub → Actions → "Daily Dashboard Update" → **Run workflow** (or `gh workflow run "Daily Dashboard Update"`). Confirm each device receives the digest notification and that tapping it opens the dashboard. Check the run's "Send push notifications" step log for `sent to ...` lines (and any `device gone` warnings).

- [ ] **Step 7: Final automated verification**

Run: `python -m pytest -q`
Expected: all pass (47 prior + push tests).

Run: `python scripts/build_dashboard.py && python scripts/send_push.py`
Expected (locally, no secrets): `no subscribers; nothing to send` and exit 0. Discard the rebuilt dashboard timestamp: `git checkout -- docs/index.html`.

- [ ] **Step 8: Confirm clean tree**

Run: `git status --short`
Expected: empty (notify.json git-ignored; index.html discarded).

---

## Notes for the implementer

- **Resilience is the contract.** `send_push.py` must never raise and the workflow step is `continue-on-error: true` — a push problem can never block the daily dashboard deploy.
- **Generate the VAPID key once, never rotate** — rotation invalidates every existing subscription.
- **`notify.json` is ephemeral** (repo root, git-ignored). It is written by `build_dashboard.py` and read by `send_push.py` within the same workflow run; it is never committed.
- **iOS** only delivers Web Push to an installed PWA (16.4+); the subscribe call must come from a tap inside the installed app.
- **Known limitation:** on subscription rotation a device goes silent (404/410 in logs) until re-registered via `enable-alerts.html`. No server exists to auto-re-subscribe — this is the accepted trade-off of the no-infra design.
