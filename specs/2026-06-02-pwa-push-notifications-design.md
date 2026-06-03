# PWA Daily Push Notifications — Design Spec
**Date:** 2026-06-02

## Goal

Send a **daily push notification** to a small, fixed set of personal devices (2–3) that have the Kairos PWA, containing the current composite score, day-over-day change, and verdict for **every configured ticker**. Tapping the notification opens the dashboard.

This is a personal-use feature for a known handful of devices — **not** a public subscribe-for-anyone feature.

## Approach — self-sent Web Push, no new infrastructure

Standard Web Push (W3C Push API + VAPID), where **we are the sender**. A push is delivered by each browser vendor's free push service (Chrome→Google, Firefox→Mozilla, Safari/iOS→Apple); the only thing the sender needs is the per-device subscription blob and a VAPID keypair. Because the subscriber set is a fixed handful we control, we **capture each device's subscription once** and skip the database + public intake endpoint that a general audience would require.

The existing **daily GitHub Actions workflow becomes the sender** — no Railway, no serverless function, no third-party push product (OneSignal/FCM), no database.

### Data flow

```
[one-time, per device]
  enable-alerts.html → SW subscribe (VAPID public key) → shows subscription blob
       → owner copies/emails the blob → pastes into the PUSH_SUBSCRIPTIONS GitHub secret

[daily, in the existing workflow]
  fetch → compute → score → build_dashboard (also writes ephemeral notify.json)
       → commit + push docs/index.html + data/   (deploy happens here, first)
       → send_push.py (last step, non-blocking): for each subscription, encrypt + POST
            the digest to its push endpoint, signed with the VAPID private key
       → vendor push service → device → sw.js 'push' handler → showNotification
       → tap → opens the dashboard
```

The only "service" involved is each vendor's inherent (free) push endpoint. The only secret is the **VAPID private key**.

## Components

### 1. VAPID keypair (one-time)
`scripts/gen_vapid.py` is run **once, locally**. It prints:
- the **public key** (base64url) — pasted into `docs/enable-alerts.html`'s `applicationServerKey` (public, safe to commit);
- the **private key** in the exact encoding `pywebpush` consumes — stored as the GitHub secret `VAPID_PRIVATE_KEY`.

> **Generate once, never rotate.** Regenerating the keypair invalidates every existing subscription (push services reject a VAPID key that doesn't match the one used at subscribe time). Rotation would require re-capturing every device.

### 2. Service worker — `docs/sw.js`
Gains two handlers; caching behavior is unchanged (still no `fetch` handler, still always-fresh, still installable):
- `push` → reads the JSON payload (guarding a null `event.data`) and calls `self.registration.showNotification(title, { body, icon: '/fbtc-timing/icons/icon-192.png', data: { url } })` (an optional monochrome `badge` can be added later if a suitable asset exists; not required).
- `notificationclick` → closes the notification, focuses an existing in-scope client if open, otherwise `clients.openWindow(url)` (the dashboard).

### 3. Setup page — `docs/enable-alerts.html` (unlinked)
A standalone page, **not linked from the public dashboard** (because we only send to the fixed committed list, a public "enable" button would mislead visitors who'd never receive anything). Two states, matching the validated mockup:

- **Before:** Kairos-branded page, a single `🔔 Enable daily alerts` button, and iOS instructions ("Add to Home Screen → open the installed app → return here → Enable"). On tap: register the SW, `Notification.requestPermission()`, then `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: <VAPID public> })`.
- **After:** a "✓ This device is subscribed" confirmation, the subscription JSON in a copyable monospace box, and **Copy** + **Email/Share** (`navigator.share` with a `mailto:` fallback) buttons so the blob can be moved off a phone, plus the instruction to paste it into the `PUSH_SUBSCRIPTIONS` secret.

No "test notification" button (a real end-to-end test needs the private key, which must not ship to the browser — see Verification for the manual test path).

### 4. Subscription storage — GitHub secret `PUSH_SUBSCRIPTIONS`
A JSON array of the 2–3 subscription blobs (`{ endpoint, keys: { p256dh, auth } }`), stored as a **GitHub Actions secret** — *not* committed (the repo is public; publishing device push endpoints is needless exposure). Adding/removing a device = editing the secret. `send_push.py` reads it from the environment.

### 5. Sender — `scripts/send_push.py`
- Reads `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (a `mailto:`), and `PUSH_SUBSCRIPTIONS` from the environment, plus the ephemeral `notify.json`.
- Builds the digest (see Notification format) and, per subscription, calls `pywebpush.webpush(sub, data=payload, vapid_private_key=..., vapid_claims={"sub": VAPID_SUBJECT})`.
- **Resilience:** empty subscriber list → log "no subscribers" and exit 0. A `404`/`410` response → log *which* device went dark (rotation/expiry signal). Any other per-device error → log and continue. **Never raises; always exits 0.**

### 6. Digest source — `notify.json` (ephemeral)
`build_dashboard.py` writes a compact `notify.json` (workspace root, **git-ignored**, consumed within the same job — not committed). One entry per asset: `{ id, display_name, composite, verdict, delta_1d }`, taken from values it already computes (`composite`, `verdict`, and the **Day** trend delta from `build_trend_data`). This reuses the existing delta math, so the notification's "↑ +2.1" equals the dashboard's Day trend exactly, and it is multi-asset by construction.

## Notification format (validated: "format A")

- **One single notification**, **one line per configured ticker** (a daily digest, not one notification per ticker).
- **Line:** `{display_name} {composite} {arrow}{±delta} — {VERDICT}` — e.g. `Bitcoin 54.5 ↑ +2.1 — CLOSE`. Arrow/sign uses the same thresholds as the dashboard Day trend: `↑` when delta > 0.5, `↓` when < −0.5, else `→`.
- **Title:** `Kairos` when one ticker is configured; `Kairos — daily scores` when more than one.
- **Tap:** opens the dashboard (last-selected asset). Per-ticker deep-linking is a non-goal (it would require one notification per ticker).
- **Display limits:** Android/iOS show ~4 lines collapsed (expandable). Fine for the realistic 1–4 tickers. If the list ever exceeds ~5, switch the title to a summary (e.g. "4 tickers · top: Gold INVEST") — future, out of scope.

## Timing

The send runs as the **final step of the existing daily workflow**, immediately after the dashboard is built and deployed — i.e. "around the time the dashboard is refreshed" (≈ 08:00 ET, per the `0 12 * * *` UTC cron). No separate schedule.

## Workflow changes — `.github/workflows/daily.yml`

- Add `pywebpush` to `requirements.txt`; add `notify.json` to `.gitignore`.
- **Order:** build → **commit + push the dashboard first** → then a final `Send push notifications` step running `python scripts/send_push.py` with `env:` `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `PUSH_SUBSCRIPTIONS`, and **`continue-on-error: true`** so a push failure can never block the deploy. (The `0 12 * * *` cron and the `git add data/ docs/index.html` line are unchanged.)

## iOS specifics

- Web Push on iOS/iPadOS works **only** for a Home-Screen-installed PWA, **iOS 16.4+**.
- The `subscribe()` call must happen from a **user gesture inside the installed app** (the Enable button satisfies this).
- Apple's push service is the strictest about the VAPID JWT — it requires a valid `mailto:` `sub` and a short expiry (`pywebpush` defaults are fine). iOS gets its own verification pass.

## Security

- Private key only ever lives in the `VAPID_PRIVATE_KEY` secret and on the owner's machine during one-time generation; never in any served file.
- Public key in `enable-alerts.html` is public by design.
- Subscriptions live in the `PUSH_SUBSCRIPTIONS` secret, never committed, never served.
- The static GitHub Pages site remains keyless; all secret-holding logic is in the Actions runner.

## Testing

- **Unit (pytest):** `format_digest_line()` for positive / negative / flat deltas and the `↑/↓/→` mapping; title selection for 1 vs N assets; empty-subscriptions no-op; mock `pywebpush.webpush` to assert one call per subscription with the correct payload and that a `410` response does not raise. Existing 47 tests remain green.
- **Manual:** desktop Chrome on `localhost` (a secure context, so the SW + subscribe work) to capture a subscription and run `send_push.py` locally with a test VAPID key; then deploy and verify a real phone, including the iOS installed-PWA path.

## Verification (end-to-end, per device, one-time)

A real end-to-end test must come from the holder of the private key (not the browser):
1. Open `enable-alerts.html` on the device, Enable, capture the blob, add it to `PUSH_SUBSCRIPTIONS`.
2. Trigger the daily workflow manually — GitHub "Run workflow" (`workflow_dispatch`) or `gh workflow run "Daily Dashboard Update"` — *or* run `python scripts/send_push.py` locally against the new subscription.
3. Confirm the device receives the digest and that tapping it opens the dashboard.

## File structure

| File | Action |
|---|---|
| `scripts/gen_vapid.py` | Create — one-time VAPID key generation (prints public + private) |
| `docs/enable-alerts.html` | Create — unlinked per-device setup page (subscribe + copy/share blob) |
| `scripts/send_push.py` | Create — sender (pywebpush), reads `notify.json` + secrets |
| `docs/sw.js` | Modify — add `push` + `notificationclick` handlers |
| `scripts/build_dashboard.py` | Modify — also emit ephemeral `notify.json` |
| `requirements.txt` | Modify — add `pywebpush` |
| `.gitignore` | Modify — add `notify.json` |
| `.github/workflows/daily.yml` | Modify — reorder (deploy first), add non-blocking send step |
| GitHub repo secrets (manual) | `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `PUSH_SUBSCRIPTIONS` |

## Non-goals

- No public subscribe feature (fixed, manually-curated device list).
- No per-ticker deep-linking (single digest notification).
- No automatic re-subscription on rotation (manual re-capture — see Risks).
- No "test notification" button on the setup page.
- No database, no Railway, no serverless function, no third-party push provider.

## Risks / known limitations

- **Subscription rotation = silent death.** Browsers occasionally rotate/expire subscriptions; the SW's `pushsubscriptionchange` normally re-registers *with a server*, which we don't have. When a device's subscription rotates (realistically weeks–months), it silently stops receiving until the owner re-runs `enable-alerts.html` and re-pastes. `send_push.py` logs `404/410` so dead devices are visible. Acceptable tax for 2–3 personal devices.
- **iOS is the fragile path** — installed-PWA-only, gesture-bound subscribe, strict Apple VAPID. Needs its own test pass.
- **Manual blob transfer** from a phone is the weakest UX link; mitigated by the Copy + Email/Share buttons.
- **VAPID key is single-source-of-truth** — losing it or rotating it invalidates all subscriptions.
