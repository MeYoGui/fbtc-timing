# Kairos New-Design Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current single-scroll Kairos dashboard with a two-view single-page app — an index "landing" view of token cards, and a per-asset details view opened by tapping a card — matching the mockups in `specs/new-design/`.

**Architecture:** The dashboard is **generated**: `scripts/build_dashboard.py` assembles one data blob per asset and renders `templates/dashboard.html.j2` into `docs/index.html` (committed to git; rebuilt daily by CI). We therefore edit the **template** and the **build script**, never `docs/index.html` directly — we regenerate it. The new template is a single HTML document containing two view containers (`#view-index`, `#view-details`); JavaScript toggles between them (no page reload) and uses URL hash routing so the browser Back button and the existing alerts deep-link keep working. All rendering is client-side from a `const ASSETS = {{ assets_json }}` blob, exactly as today.

**Tech Stack:** Python 3.11 (pandas, numpy, jinja2, pytest) for the build; Tailwind CSS (CDN), Chart.js 4 (CDN), vanilla JS, Google Fonts (Space Grotesk, JetBrains Mono, Material Symbols) for the front end.

---

## Decisions locked in (from clarifying questions)

1. **Navigation:** Single-page show/hide (one HTML file, two view containers) — plus lightweight `#hash` routing for Back-button correctness.
2. **Score history (mini-bars):** Derived from existing data — the per-asset `trend.{day,week,month}.spark[].score` already in the blob.
3. **Font:** Space Grotesk (body/headings) + JetBrains Mono (numeric data) across **both** views (the details mockup's Inter is dropped so the app reads as one product).
4. **Settings gear (details header):** Rendered but a no-op (`type="button"`, no handler) for now.
5. **Existing features:** **Drop** the methodology table and the "How is X calculated?" breakdown panel. **Keep** the multi-window price chart (6M/1Y/2Y/All pills) on the details view.
6. **Index timeframe pills (Day/Week/Month):** Control the mini-bar charts inside the cards by switching which `trend` window's `spark` is shown.
7. **Details metric cards:** Data-driven — render whatever signals each asset has configured (so ETH shows its own set), not a hardcoded six.

## Palette decision (explicit)

The two mockups use slightly different palettes (index: `deep-abyss #050505` bg + `cyber-emerald #00ff88`; details: `#131313` bg + `#00E676`/`#75ff9e`). To make the app read as one product we adopt the **index palette across both views**: background `#050505`, primary/emerald `#00ff88`. The details view is re-skinned onto these tokens, so it will be slightly darker than `details_screen.png` by design.

## File Structure

- **Modify** `scripts/build_dashboard.py` — add two pure helper functions (`compute_price_change_24h`, `verdict_description`) and wire their outputs (`price_change_24h`, `verdict_description`) into the per-asset blob in `_assemble_asset`. Nothing else in the build pipeline changes.
- **Modify** `tests/test_build_dashboard.py` — add unit tests for the two new helpers and one integration test that a real built asset blob carries the new keys.
- **Rewrite** `templates/dashboard.html.j2` — the entire new two-view UI. This is the bulk of the work, built up section by section (head/scaffold → index markup → index JS → details markup → details JS → boot).
- **Regenerate** `docs/index.html` — by running `python scripts/build_dashboard.py`; committed alongside the template.

## Data contract (what the blob already provides per asset)

Each entry in `ASSETS` (confirmed by reading `docs/index.html`'s embedded JSON) has:
`id`, `display_name`, `short_label` (e.g. `"₿ Bitcoin"`), `accent_color`, `price_unit` (`"$"`), `price` (int), `composite`, `verdict`, `sell_composite`, `sell_verdict`, `spectrum_pos` (float 0–100, the headline number), `spectrum_verdict` (e.g. `"STRONG BUY"`), `score_color`, `distance_text`, `signals` (list of `{key, display_name, reading, bar}` where `bar` has `cursor_pct`, `status_class` ∈ `st-invest|st-wait|st-avoid`, plus zone widths), `chart` (`{dates[], prices[], scores[]}`), `trend` (`{day,week,month}` each `{delta, spark:[{score,label,verdict}], arrows}`), `methodology` (unused after this redesign).

**After this plan** each entry additionally has: `price_change_24h` (float, percent) and `verdict_description` (string sentence).

---

## Task 1: Add `compute_price_change_24h` to the build script

**Files:**
- Modify: `scripts/build_dashboard.py` (add a new top-level function near `format_reading`, e.g. after line 52)
- Test: `tests/test_build_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_build_dashboard.py`:

```python
# ── compute_price_change_24h ─────────────────────────────────────────────────
from build_dashboard import compute_price_change_24h


def test_price_change_24h_positive():
    df = pd.DataFrame({"price": [100.0, 102.5]})
    assert compute_price_change_24h(df) == 2.5


def test_price_change_24h_negative():
    df = pd.DataFrame({"price": [100.0, 95.0]})
    assert compute_price_change_24h(df) == -5.0


def test_price_change_24h_skips_trailing_nan():
    # Last valid pair is 100 -> 110 ; the NaN row must be ignored
    df = pd.DataFrame({"price": [100.0, 110.0, np.nan]})
    assert compute_price_change_24h(df) == 10.0


def test_price_change_24h_single_row_returns_zero():
    df = pd.DataFrame({"price": [100.0]})
    assert compute_price_change_24h(df) == 0.0


def test_price_change_24h_zero_prev_returns_zero():
    df = pd.DataFrame({"price": [0.0, 50.0]})
    assert compute_price_change_24h(df) == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_build_dashboard.py -k price_change_24h -v`
Expected: FAIL — `ImportError: cannot import name 'compute_price_change_24h'`

- [ ] **Step 3: Write the implementation**

In `scripts/build_dashboard.py`, add this function immediately after `format_reading` (after line 52, before `get_score_color`):

```python
def compute_price_change_24h(price_df: pd.DataFrame) -> float:
    """Percent change between the two most recent non-null daily prices.

    Returns 0.0 when there is no prior price or the prior price is zero,
    so the dashboard always has a numeric value to render.
    """
    prices = price_df.dropna(subset=["price"])["price"]
    if len(prices) < 2:
        return 0.0
    last, prev = float(prices.iloc[-1]), float(prices.iloc[-2])
    if prev == 0:
        return 0.0
    return round((last / prev - 1) * 100, 2)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_build_dashboard.py -k price_change_24h -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/build_dashboard.py tests/test_build_dashboard.py
git commit -m "feat: compute 24h price change for dashboard"
```

---

## Task 2: Add `verdict_description` to the build script

**Files:**
- Modify: `scripts/build_dashboard.py` (add after `compute_price_change_24h`)
- Test: `tests/test_build_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_build_dashboard.py`:

```python
# ── verdict_description ──────────────────────────────────────────────────────
from build_dashboard import verdict_description


def test_verdict_description_strong_buy():
    assert verdict_description("STRONG BUY") == (
        "Momentum and on-chain metrics suggest highly favorable entry conditions."
    )


def test_verdict_description_each_verdict_is_nonempty():
    for v in ("STRONG BUY", "BUY", "HOLD", "SELL", "TAKE PROFIT"):
        assert len(verdict_description(v)) > 0


def test_verdict_description_unknown_falls_back_to_hold_copy():
    assert verdict_description("???") == verdict_description("HOLD")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_build_dashboard.py -k verdict_description -v`
Expected: FAIL — `ImportError: cannot import name 'verdict_description'`

- [ ] **Step 3: Write the implementation**

In `scripts/build_dashboard.py`, add immediately after `compute_price_change_24h`:

```python
def verdict_description(spectrum_verdict: str) -> str:
    """One-sentence plain-language summary shown under the details-view verdict."""
    return {
        "STRONG BUY":  "Momentum and on-chain metrics suggest highly favorable entry conditions.",
        "BUY":         "Conditions favor accumulation, though not at peak conviction.",
        "HOLD":        "Signals are mixed — no decisive edge in either direction.",
        "SELL":        "Indicators are cooling; consider trimming exposure.",
        "TAKE PROFIT": "Metrics are stretched — historically a zone for taking profit.",
    }.get(spectrum_verdict, "Signals are mixed — no decisive edge in either direction.")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_build_dashboard.py -k verdict_description -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/build_dashboard.py tests/test_build_dashboard.py
git commit -m "feat: add verdict description copy for details view"
```

---

## Task 3: Wire the new fields into the asset blob

**Files:**
- Modify: `scripts/build_dashboard.py:281-300` (the `return {...}` dict in `_assemble_asset`)
- Test: `tests/test_build_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_build_dashboard.py`:

```python
# ── _assemble_asset integration: new keys present ────────────────────────────
from build_dashboard import _assemble_asset
sys.path.insert(0, str(Path(__file__).parent.parent))
from assets.registry import ASSETS as ASSET_CONFIGS


def test_assembled_bitcoin_blob_has_new_keys():
    cfg = next(c for c in ASSET_CONFIGS if c.id == "bitcoin")
    blob = _assemble_asset(cfg)
    assert blob is not None, "bitcoin data files must be present to run this test"
    assert "price_change_24h" in blob
    assert isinstance(blob["price_change_24h"], float)
    assert "verdict_description" in blob
    assert len(blob["verdict_description"]) > 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_build_dashboard.py -k assembled_bitcoin -v`
Expected: FAIL — `KeyError: 'price_change_24h'` (assertion error on missing key)

- [ ] **Step 3: Write the implementation**

In `scripts/build_dashboard.py`, inside `_assemble_asset`, the function already computes `current_price` (line 268). Immediately after that line, add:

```python
    price_change_24h = compute_price_change_24h(price_df)
```

Then in the `return {...}` dict (lines 281–300), add these two entries right after the `"price"` line:

```python
        "price_change_24h": price_change_24h,
        "verdict_description": verdict_description(spectrum_verdict),
```

(Place them anywhere in the dict; next to `"spectrum_verdict"` is fine too. The point is both keys appear in the returned blob.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_build_dashboard.py -k assembled_bitcoin -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite + a real build to confirm nothing regressed**

Run: `python -m pytest tests/test_build_dashboard.py -v`
Expected: all pass.

Run: `python scripts/build_dashboard.py`
Expected: `Dashboard written to docs/index.html (... bytes; 2 asset(s))`

Confirm the new keys made it into the generated blob:

Run: `python -c "import re,json; html=open('docs/index.html',encoding='utf-8').read(); m=re.search(r'const ASSETS = (\[.*?\]);', html); a=json.loads(m.group(1)); print('price_change_24h' in a[0], 'verdict_description' in a[0], a[0]['price_change_24h'], a[0]['verdict_description'][:20])"`
Expected: `True True <some float> <start of sentence>`

- [ ] **Step 6: Commit**

```bash
git add scripts/build_dashboard.py tests/test_build_dashboard.py docs/index.html
git commit -m "feat: expose 24h change and verdict description in asset blob"
```

---

## Task 4: Rewrite the template head + two-view scaffold

This replaces the entire current `templates/dashboard.html.j2`. We build it up over Tasks 4–9; **Task 4 writes the complete `<head>`, `<body>` open tag, the two empty view containers, and a placeholder `<script>` block** so the file is valid and builds. Later tasks fill the views and the script.

**Files:**
- Modify (full rewrite): `templates/dashboard.html.j2`

- [ ] **Step 1: Replace the whole template file**

Overwrite `templates/dashboard.html.j2` with exactly this (later tasks insert markup where the `<!-- INDEX VIEW ... -->` and `<!-- DETAILS VIEW ... -->` and `/* APP LOGIC ... */` markers are):

```html
<!DOCTYPE html>
<html class="dark" lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kairos — Crypto Market Timing</title>
  <link rel="manifest" href="/fbtc-timing/manifest.json">
  <link rel="icon" type="image/png" sizes="48x48" href="/fbtc-timing/icons/favicon-48.png">
  <link rel="icon" type="image/png" sizes="32x32" href="/fbtc-timing/icons/favicon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/fbtc-timing/icons/favicon-16.png">
  <meta name="theme-color" content="#050505">
  <link rel="apple-touch-icon" href="/fbtc-timing/icons/icon-192.png">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Kairos">
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
  <script id="tailwind-config">
    tailwind.config = {
      darkMode: "class",
      theme: {
        extend: {
          colors: {
            "cyber-emerald": "#00ff88",
            "deep-abyss": "#050505",
            "surface": "#0a0a0a",
            "surface-container": "#0d0d0d",
            "surface-container-low": "#080808",
            "surface-container-high": "#111111",
            "surface-container-highest": "#1a1a1a",
            "surface-variant": "#222222",
            "surface-charcoal": "#0a0a0a",
            "on-surface": "#ffffff",
            "on-surface-variant": "#aaaaaa",
            "outline": "#444444",
            "outline-variant": "#333333",
            "border-subtle": "rgba(255, 255, 255, 0.1)",
            "primary": "#00ff88",
            "buy-vibrant": "#00ff88",
            "buy-steady": "#00C853",
            "hold-neutral": "#D0D0D0",
            "sell-urgent": "#FF3B30",
            "tertiary-container": "#fdb878",
            "error": "#ffb4ab",
            "on-secondary-fixed-variant": "#930005"
          },
          borderRadius: { "DEFAULT": "0.125rem", "lg": "0.25rem", "xl": "0.5rem", "full": "0.75rem" },
          spacing: { "unit": "4px", "stack-sm": "8px", "stack-md": "16px", "stack-lg": "24px", "container-padding": "16px", "gutter": "12px" },
          fontFamily: {
            "body-base": ["Space Grotesk", "sans-serif"],
            "display-lg": ["Space Grotesk", "sans-serif"],
            "headline-md": ["Space Grotesk", "sans-serif"],
            "headline-lg-mobile": ["Space Grotesk", "sans-serif"],
            "data-lg": ["JetBrains Mono", "monospace"],
            "data-sm": ["JetBrains Mono", "monospace"],
            "label-caps": ["JetBrains Mono", "monospace"]
          },
          fontSize: {
            "body-base": ["16px", { "lineHeight": "24px", "fontWeight": "400" }],
            "display-lg": ["32px", { "lineHeight": "40px", "letterSpacing": "-0.02em", "fontWeight": "700" }],
            "headline-md": ["20px", { "lineHeight": "28px", "fontWeight": "600" }],
            "headline-lg-mobile": ["24px", { "lineHeight": "32px", "fontWeight": "700" }],
            "data-lg": ["18px", { "lineHeight": "24px", "letterSpacing": "-0.01em", "fontWeight": "600" }],
            "data-sm": ["13px", { "lineHeight": "16px", "fontWeight": "500" }],
            "label-caps": ["11px", { "lineHeight": "14px", "letterSpacing": "0.05em", "fontWeight": "700" }]
          }
        }
      }
    }
  </script>
  <style>
    body {
      background-color: #050505;
      color: #ffffff;
      min-height: max(884px, 100dvh);
      background-image: radial-gradient(circle at 50% 50%, rgba(0,255,136,0.03) 0%, transparent 100%);
    }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #050505; }
    ::-webkit-scrollbar-thumb { background: #222222; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #aaaaaa; }
    .pulse-ring { animation: pulse-ring 4s cubic-bezier(0.215,0.61,0.355,1) infinite; }
    .pulse-ring-delayed { animation: pulse-ring 4s cubic-bezier(0.215,0.61,0.355,1) infinite 1.2s; }
    @keyframes pulse-ring { 0% { transform: scale(0.8); opacity: 0.5; } 80%, 100% { transform: scale(1.5); opacity: 0; } }
    .hidden-view { display: none !important; }
  </style>
</head>
<body class="font-body-base antialiased pb-24 selection:bg-cyber-emerald/30 selection:text-cyber-emerald">

  <!-- ===================== INDEX VIEW ===================== -->
  <div id="view-index">
    <!-- INDEX VIEW MARKUP (Task 5) -->
  </div>

  <!-- ===================== DETAILS VIEW ===================== -->
  <div id="view-details" class="hidden-view">
    <!-- DETAILS VIEW MARKUP (Task 7) -->
  </div>

  <script>
    const ASSETS = {{ assets_json }};
    const DEFAULT_ASSET = "{{ default_asset }}";
    const UPDATED_AT = "{{ updated_at }}";
    const BY_ID = Object.fromEntries(ASSETS.map(a => [a.id, a]));

    /* APP LOGIC (Tasks 6, 8, 9) */
  </script>

  <script>
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/fbtc-timing/sw.js').catch(() => {});
      });
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: Build and verify the template renders**

Run: `python scripts/build_dashboard.py`
Expected: `Dashboard written to docs/index.html (... bytes; 2 asset(s))` with no Jinja error.

Confirm the two view containers exist in the output:

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('view-index' in h, 'view-details' in h, 'const ASSETS' in h)"`
Expected: `True True True`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: scaffold two-view dashboard template"
```

---

## Task 5: Index view markup

**Files:**
- Modify: `templates/dashboard.html.j2` (replace the `<!-- INDEX VIEW MARKUP (Task 5) -->` line)

- [ ] **Step 1: Insert the index markup**

Replace the line `    <!-- INDEX VIEW MARKUP (Task 5) -->` with:

```html
    <!-- Top App Bar -->
    <header class="fixed top-0 w-full z-50 flex justify-between items-center px-container-padding h-14 bg-deep-abyss/80 backdrop-blur-md border-b border-border-subtle">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-cyber-emerald text-xl" style="font-variation-settings: 'FILL' 1;">analytics</span>
        <span class="text-headline-md font-headline-md font-bold tracking-widest uppercase text-on-surface">KAIROS</span>
      </div>
      <div class="font-data-sm text-data-sm text-on-surface-variant flex flex-col items-end leading-tight">
        <span class="text-cyber-emerald" id="idx-btc-price">—</span>
        <span class="text-[10px] opacity-50" id="idx-updated">—</span>
      </div>
    </header>

    <main class="pt-20 px-4 md:px-6 max-w-[1200px] mx-auto flex flex-col gap-8 items-center">
      <!-- Timeframe Selector -->
      <div class="flex justify-center mt-2 z-20 relative w-full">
        <div class="flex bg-surface-container-low p-1 rounded-full border border-border-subtle shadow-[0_0_15px_rgba(0,0,0,0.5)]">
          <button type="button" data-tf="day"   class="tf-pill px-4 py-1.5 text-data-sm font-data-sm rounded-full uppercase tracking-wider transition-colors">Day</button>
          <button type="button" data-tf="week"  class="tf-pill px-4 py-1.5 text-data-sm font-data-sm rounded-full uppercase tracking-wider transition-colors">Week</button>
          <button type="button" data-tf="month" class="tf-pill px-4 py-1.5 text-data-sm font-data-sm rounded-full uppercase tracking-wider transition-colors">Month</button>
        </div>
      </div>

      <!-- Token cards (rendered by renderIndexCards) -->
      <section id="token-list" class="relative w-full max-w-md flex flex-col items-center justify-center gap-6 z-30 mt-4"></section>
    </main>

    <!-- Bottom Alerts Action -->
    <div class="fixed bottom-0 w-full z-50 flex justify-center items-center px-4 pb-6 pt-10 bg-gradient-to-t from-deep-abyss via-deep-abyss/90 to-transparent pointer-events-none">
      <a href="enable-alerts.html" class="pointer-events-auto bg-cyber-emerald text-deep-abyss font-headline-md text-sm font-bold px-8 py-3 rounded-full shadow-[0_0_20px_rgba(0,255,136,0.3)] hover:bg-white hover:text-deep-abyss transition-all flex items-center gap-2 uppercase tracking-widest">
        <span class="material-symbols-outlined text-[18px]" style="font-variation-settings: 'FILL' 1;">notifications_active</span>
        alerts
      </a>
    </div>
```

- [ ] **Step 2: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: builds cleanly.

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('token-list' in h, 'idx-btc-price' in h, h.count('tf-pill')>=3)"`
Expected: `True True True`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: index view markup (app bar, timeframe pills, card slot)"
```

---

## Task 6: Index view logic — render cards, timeframe pills, open details

**Files:**
- Modify: `templates/dashboard.html.j2` (the `/* APP LOGIC (Tasks 6, 8, 9) */` marker in the main `<script>`)

This task adds the shared helpers (`zoneColor`), index state, card rendering, the timeframe pill behavior, and the card→details entry point. `openDetails`/`closeDetails` bodies are completed in Task 8; here we add minimal versions so clicking is wired and verifiable.

- [ ] **Step 1: Insert the index logic**

Replace the line `    /* APP LOGIC (Tasks 6, 8, 9) */` with:

```javascript
    // ---- shared helpers ----
    function zoneColor(s) {
      return s >= 80 ? '#00ff88' : s >= 60 ? '#00C853' : s >= 40 ? '#D0D0D0' : s >= 20 ? '#ff9800' : '#FF3B30';
    }
    // Which of the 5 spectrum zones a position falls in (0=TP .. 4=Strong Buy)
    function zoneIndex(pos) {
      return pos >= 80 ? 4 : pos >= 60 ? 3 : pos >= 40 ? 2 : pos >= 20 ? 1 : 0;
    }
    const ZONE_LABELS = ['TP', 'Sell', 'Hold', 'Buy', 'Strong Buy'];
    const ZONE_COLORS = ['#FF3B30', '#ff9800', '#D0D0D0', '#00C853', '#00ff88'];

    // ---- index state ----
    let timeframe = (function () {
      try { const w = localStorage.getItem('kairos-trend-window'); if (['day','week','month'].includes(w)) return w; } catch (e) {}
      return 'day';
    })();

    function miniBarsHTML(a) {
      const sp = a.trend[timeframe].spark;
      const scores = sp.map(p => p.score);
      const mx = Math.max.apply(null, scores);
      const mn = Math.min.apply(null, scores) - 3;
      const span = (mx - mn) || 1;
      return sp.map(function (p, i) {
        const h = Math.max(Math.round(((p.score - mn) / span) * 100), 12);
        const last = i === sp.length - 1;
        const bg = last ? 'background:' + zoneColor(p.score) + ';box-shadow:0 0 8px rgba(0,255,136,0.6);' : 'background:#222222;';
        return '<div class="w-full rounded-sm" style="height:' + h + '%;' + bg + '"></div>';
      }).join('');
    }

    function spectrumBandHTML(a) {
      const zi = zoneIndex(a.spectrum_pos);
      const segs = ZONE_COLORS.map(function (c, i) {
        const active = i === zi;
        const style = active
          ? 'background:' + c + ';box-shadow:0 0 10px ' + c + ';'
          : 'background:' + c + ';opacity:0.30;';
        return '<div class="h-full w-1/5" style="' + style + '"></div>';
      }).join('');
      const labels = ZONE_LABELS.map(function (l, i) {
        const active = i === zi;
        return '<span class="' + (active ? 'font-bold' : '') + '" style="color:' + (active ? ZONE_COLORS[i] : '#aaaaaa') + '">' + l + '</span>';
      }).join('');
      return '<div class="relative w-full h-1.5 bg-surface-variant rounded-full overflow-hidden flex">' + segs + '</div>'
        + '<div class="flex justify-between text-[9px] font-label-caps uppercase tracking-tighter mt-1">' + labels + '</div>';
    }

    function cardHTML(a, primary) {
      const col = zoneColor(a.spectrum_pos);
      const border = primary ? 'border-cyber-emerald/40 hover:border-cyber-emerald' : 'border-border-subtle hover:border-cyber-emerald/50';
      const glow = primary ? 'shadow-[0_0_20px_rgba(0,255,136,0.15)] hover:shadow-[0_0_30px_rgba(0,255,136,0.3)]' : 'shadow-lg hover:shadow-[0_0_20px_rgba(0,255,136,0.1)]';
      return '<button type="button" data-asset="' + a.id + '" class="asset-card relative w-full bg-surface-container-high border ' + border + ' rounded-2xl p-6 ' + glow + ' transition-all group overflow-hidden text-left flex flex-col gap-4">'
        + '<div class="flex justify-between items-center relative z-10">'
        +   '<div class="flex items-center gap-2 text-on-surface font-headline-lg-mobile text-2xl">' + a.short_label + '</div>'
        +   '<div class="w-8 h-8 rounded-full bg-surface-container border border-border-subtle flex items-center justify-center group-hover:border-cyber-emerald group-hover:bg-cyber-emerald/10 transition-all">'
        +     '<span class="material-symbols-outlined text-cyber-emerald text-sm opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all">arrow_forward</span>'
        +   '</div>'
        + '</div>'
        + '<div class="flex flex-col gap-3 w-full relative z-10 mt-2">'
        +   '<div class="flex justify-between items-end">'
        +     '<div class="flex flex-col">'
        +       '<span class="text-[11px] font-label-caps tracking-widest font-bold opacity-90" style="color:' + col + '">' + a.spectrum_verdict + '</span>'
        +       '<span class="text-[40px] font-data-lg text-white font-bold leading-none tracking-tight">' + a.spectrum_pos.toFixed(1) + '</span>'
        +     '</div>'
        +     '<div class="flex gap-1 h-6 items-end w-24 mb-1">' + miniBarsHTML(a) + '</div>'
        +   '</div>'
        +   spectrumBandHTML(a)
        + '</div>'
        + '</button>';
    }

    function renderIndexCards() {
      document.getElementById('token-list').innerHTML =
        ASSETS.map(function (a, i) { return cardHTML(a, i === 0); }).join('');
      document.querySelectorAll('.asset-card').forEach(function (el) {
        el.addEventListener('click', function () { openDetails(el.getAttribute('data-asset')); });
      });
    }

    function setTimeframe(w) {
      timeframe = w;
      try { localStorage.setItem('kairos-trend-window', w); } catch (e) {}
      document.querySelectorAll('.tf-pill').forEach(function (el) {
        const active = el.getAttribute('data-tf') === w;
        el.classList.toggle('bg-on-surface', active);
        el.classList.toggle('text-deep-abyss', active);
        el.classList.toggle('font-bold', active);
        el.classList.toggle('shadow-sm', active);
        el.classList.toggle('text-on-surface-variant', !active);
      });
      renderIndexCards();
    }

    function renderIndexHeader() {
      const first = BY_ID[DEFAULT_ASSET] || ASSETS[0];
      document.getElementById('idx-btc-price').textContent = first.price_unit + first.price.toLocaleString();
      document.getElementById('idx-updated').textContent = 'Updated ' + UPDATED_AT;
    }

    // Minimal stubs — full bodies added in Task 8.
    function openDetails(id) { console.log('openDetails', id); }
    function closeDetails() {}
```

- [ ] **Step 2: Add the timeframe pill listeners + boot the index**

At the very end of the same `<script>` block (right before its closing `</script>`), the boot code lives in Task 9. For now, to verify this task, temporarily append this boot snippet **at the end of the script block**:

```javascript
    document.querySelectorAll('.tf-pill').forEach(function (el) {
      el.addEventListener('click', function () { setTimeframe(el.getAttribute('data-tf')); });
    });
    renderIndexHeader();
    setTimeframe(timeframe);
```

(Task 9 replaces this with the final unified boot block.)

- [ ] **Step 3: Build and screenshot to verify against the mockup**

Run: `python scripts/build_dashboard.py`
Expected: builds cleanly.

Verify with Playwright MCP (the `mcp__playwright__*` tools):
1. `browser_navigate` to `file:///C:/Users/guill/Workspace/fbtc-timing/docs/index.html`
2. `browser_resize` width 390 height 844 (iPhone-ish, matches the mockup)
3. `browser_take_screenshot` → compare to `specs/new-design/index_screen.png`

Expected: KAIROS app bar with BTC price top-right; Day/Week/Month pills (Day active, white bg); two cards (Bitcoin highlighted/emerald border, Ethereum subtle) each showing verdict label, big score (83.1 / 87.7), a 6-bar mini chart with the last bar emerald, and a 5-zone spectrum band with the Strong-Buy segment lit. Clicking Day/Week/Month re-renders the mini-bars.

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: index card rendering and timeframe pills"
```

---

## Task 7: Details view markup

**Files:**
- Modify: `templates/dashboard.html.j2` (replace the `<!-- DETAILS VIEW MARKUP (Task 7) -->` line)

- [ ] **Step 1: Insert the details markup**

Replace the line `    <!-- DETAILS VIEW MARKUP (Task 7) -->` with:

```html
    <!-- Top App Bar -->
    <header class="sticky top-0 z-50 flex justify-between items-center px-container-padding h-14 w-full bg-deep-abyss/80 backdrop-blur-md border-b border-border-subtle">
      <button type="button" id="detail-back" aria-label="Go back" class="active:scale-95 transition-transform hover:bg-surface-variant/30 text-cyber-emerald flex items-center justify-center p-2 -ml-2 rounded-full">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <div class="font-headline-md text-headline-md font-bold tracking-tighter text-cyber-emerald">KAIROS TERMINAL</div>
      <button type="button" aria-label="Settings" class="active:scale-95 transition-transform hover:bg-surface-variant/30 text-cyber-emerald flex items-center justify-center p-2 -mr-2 rounded-full">
        <span class="material-symbols-outlined">settings</span>
      </button>
    </header>

    <main class="flex-1 max-w-[1200px] mx-auto w-full flex flex-col">
      <!-- Context Header -->
      <div class="px-container-padding pt-stack-lg pb-stack-sm flex justify-between items-end border-b border-border-subtle/50">
        <div>
          <h1 class="font-display-lg text-display-lg text-on-surface" id="detail-name">—</h1>
          <div class="flex items-center gap-2 mt-1">
            <span class="font-label-caps text-label-caps text-on-surface-variant" id="detail-subtitle">DETAILS</span>
            <span class="h-1 w-1 bg-cyber-emerald rounded-full shadow-[0_0_5px_#00ff88]"></span>
            <span class="font-data-sm text-data-sm text-cyber-emerald">LIVE</span>
          </div>
        </div>
        <div class="text-right">
          <div class="font-data-lg text-data-lg text-on-surface" id="detail-price">—</div>
          <div class="font-data-sm text-data-sm mt-1" id="detail-change">—</div>
        </div>
      </div>

      <!-- Hero: Pulse Verdict -->
      <section class="flex flex-col items-center justify-center py-12 px-container-padding relative overflow-hidden">
        <div class="absolute inset-0 opacity-10 pointer-events-none" style="background-image: radial-gradient(#aaaaaa 1px, transparent 1px); background-size: 24px 24px;"></div>
        <div class="relative w-48 h-48 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border border-cyber-emerald/30 pulse-ring pointer-events-none"></div>
          <div class="absolute inset-0 rounded-full border border-cyber-emerald/10 pulse-ring-delayed pointer-events-none"></div>
          <div class="absolute inset-4 rounded-full bg-cyber-emerald/5 blur-2xl pointer-events-none"></div>
          <div class="relative z-10 w-32 h-32 rounded-full bg-surface-charcoal border border-border-subtle flex flex-col items-center justify-center shadow-[0_0_40px_rgba(0,255,136,0.15)] ring-1 ring-cyber-emerald/50 backdrop-blur-md">
            <span class="font-data-lg text-[32px] leading-none mb-1 text-on-surface" id="detail-hero-score">—</span>
            <span class="font-label-caps text-label-caps text-on-surface-variant">COMPOSITE</span>
          </div>
        </div>
        <div class="mt-8 flex flex-col items-center">
          <h2 class="font-display-lg text-display-lg tracking-[0.2em] uppercase drop-shadow-[0_0_12px_rgba(0,255,136,0.4)]" id="detail-verdict">—</h2>
          <p class="font-body-base text-body-base text-on-surface-variant mt-2 max-w-sm text-center" id="detail-desc">—</p>
        </div>
      </section>

      <!-- Metric Cards (rendered by renderMetricCards) -->
      <section id="metric-cards" class="px-container-padding grid grid-cols-1 md:grid-cols-3 gap-stack-md py-stack-md relative z-10"></section>

      <!-- Historical Chart -->
      <section class="px-container-padding py-stack-md flex-1 pb-stack-lg">
        <div class="bg-surface-charcoal border border-border-subtle rounded-xl p-stack-md flex flex-col relative overflow-hidden">
          <div class="flex justify-between items-center mb-4 z-10">
            <span class="font-label-caps text-label-caps text-on-surface">PRICE (USD) VS COMPOSITE</span>
            <div class="flex gap-2">
              <button type="button" data-cw="6m"  class="cw-pill text-[11px] font-data-sm rounded-full px-3 py-1 transition-colors">6M</button>
              <button type="button" data-cw="1y"  class="cw-pill text-[11px] font-data-sm rounded-full px-3 py-1 transition-colors">1Y</button>
              <button type="button" data-cw="2y"  class="cw-pill text-[11px] font-data-sm rounded-full px-3 py-1 transition-colors">2Y</button>
              <button type="button" data-cw="all" class="cw-pill text-[11px] font-data-sm rounded-full px-3 py-1 transition-colors">All</button>
            </div>
          </div>
          <div class="relative h-64 md:h-80"><canvas id="detail-chart"></canvas></div>
        </div>
      </section>
    </main>

    <!-- Bottom SET ALERTS -->
    <div class="fixed bottom-0 w-full px-container-padding py-4 bg-deep-abyss/90 backdrop-blur-xl border-t border-border-subtle z-50">
      <div class="max-w-[1200px] mx-auto">
        <a href="enable-alerts.html" class="w-full bg-cyber-emerald hover:bg-white text-deep-abyss font-headline-md text-headline-md py-3 rounded-xl shadow-[0_0_20px_rgba(0,255,136,0.3)] hover:shadow-[0_0_30px_rgba(0,255,136,0.5)] active:scale-[0.98] transition-all flex items-center justify-center gap-2 group">
          <span class="material-symbols-outlined transition-transform group-hover:rotate-12" style="font-variation-settings: 'FILL' 1;">notifications_active</span>
          <span class="tracking-wide">SET ALERTS</span>
        </a>
      </div>
    </div>
```

- [ ] **Step 2: Build and verify**

Run: `python scripts/build_dashboard.py`
Expected: builds cleanly.

Run: `python -c "h=open('docs/index.html',encoding='utf-8').read(); print('detail-hero-score' in h, 'metric-cards' in h, 'detail-chart' in h, h.count('cw-pill')>=4)"`
Expected: `True True True True`

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: details view markup (hero, metric grid, chart shell)"
```

---

## Task 8: Details view logic — populate, metric cards, chart, routing

**Files:**
- Modify: `templates/dashboard.html.j2` (replace the stub `openDetails`/`closeDetails` added in Task 6, and add chart helpers, inside the main `<script>`)

- [ ] **Step 1: Replace the stubs with full logic**

Find the two stub lines added in Task 6:

```javascript
    // Minimal stubs — full bodies added in Task 8.
    function openDetails(id) { console.log('openDetails', id); }
    function closeDetails() {}
```

Replace them with:

```javascript
    // ---- details state ----
    let detailId = null;
    let chart = null;
    let chartWindow = (function () {
      try { var w = localStorage.getItem('kairos-chart-window'); if (['6m','1y','2y','all'].includes(w)) return w; } catch (e) {}
      return '1y';
    })();

    // metric card value color from the precomputed status class
    function metricColor(statusClass) {
      return statusClass === 'st-invest' ? '#00ff88'
           : statusClass === 'st-avoid'  ? '#ffb4ab'
           : '#fdb878';
    }

    function metricCardHTML(sig) {
      const b = sig.bar;
      if (!b || !b.has_data) {
        return '<div class="bg-surface-charcoal border border-border-subtle rounded-xl p-stack-md flex flex-col">'
          + '<span class="font-label-caps text-label-caps text-on-surface-variant">' + sig.display_name + '</span>'
          + '<span class="font-data-sm text-data-sm text-outline mt-6">No data</span></div>';
      }
      const col = metricColor(b.status_class);
      return '<div class="bg-surface-charcoal border border-border-subtle rounded-xl p-stack-md flex flex-col hover:border-cyber-emerald/30 transition-colors group">'
        + '<div class="flex justify-between items-start mb-6 gap-2">'
        +   '<span class="font-label-caps text-label-caps text-on-surface-variant group-hover:text-on-surface transition-colors">' + sig.display_name + '</span>'
        +   '<span class="font-data-lg text-data-lg text-right" style="color:' + col + ';text-shadow:0 0 8px ' + col + '33;">' + sig.reading + '</span>'
        + '</div>'
        + '<div class="mt-auto w-full">'
        +   '<div class="flex justify-between font-label-caps text-label-caps text-surface-variant mb-1 text-[9px]"><span>TAKE PROFIT</span><span>STRONG BUY</span></div>'
        +   '<div class="h-1.5 w-full bg-surface-container-highest rounded-full relative overflow-hidden flex">'
        +     '<div class="h-full bg-sell-urgent/20 w-1/4"></div>'
        +     '<div class="h-full bg-surface-variant w-1/2"></div>'
        +     '<div class="h-full bg-cyber-emerald/20 w-1/4"></div>'
        +     '<div class="absolute top-0 bottom-0 w-1" style="left:' + b.cursor_pct + '%;background:' + col + ';box-shadow:0 0 5px ' + col + ';"></div>'
        +   '</div>'
        + '</div></div>';
    }

    function renderMetricCards(a) {
      document.getElementById('metric-cards').innerHTML = a.signals.map(metricCardHTML).join('');
    }

    // ---- chart (ported from the previous dashboard) ----
    function sliceChartData(c, w) {
      var n = { '6m': 26, '1y': 52, '2y': 104 }[w];
      if (!n) return c;
      var start = Math.max(0, c.dates.length - n);
      return { dates: c.dates.slice(start), prices: c.prices.slice(start), scores: c.scores.slice(start) };
    }

    function renderChart(d) {
      var zoneBandsPlugin = {
        id: 'zoneBands',
        beforeDraw: function (ch) {
          var ctx = ch.ctx, yAxis = ch.scales.yScore, xAxis = ch.scales.x;
          [
            { min: 80, max: 100, color: '#00ff8810' },
            { min: 60, max: 80,  color: '#00C85310' },
            { min: 40, max: 60,  color: '#ffffff08' },
            { min: 20, max: 40,  color: '#ff980010' },
            { min: 0,  max: 20,  color: '#FF3B3010' },
          ].forEach(function (z) {
            ctx.fillStyle = z.color;
            ctx.fillRect(xAxis.left, yAxis.getPixelForValue(z.max), xAxis.right - xAxis.left, yAxis.getPixelForValue(z.min) - yAxis.getPixelForValue(z.max));
          });
        },
      };
      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('detail-chart'), {
        type: 'line',
        data: { labels: d.dates, datasets: [
          { label: 'Price (USD)', data: d.prices, yAxisID: 'yPrice', borderColor: '#00ff88', borderWidth: 2, pointRadius: 0, tension: 0.1 },
          { label: 'Composite Score', data: d.scores, yAxisID: 'yScore', borderColor: '#fdb878', borderWidth: 1.5, borderDash: [4, 2], pointRadius: 0, tension: 0.1 },
        ]},
        options: {
          responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { labels: { color: '#aaaaaa', boxWidth: 12, font: { size: 11 } } } },
          scales: {
            x: { ticks: { color: '#555', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yPrice: { type: 'logarithmic', position: 'left', ticks: { color: '#555', font: { size: 10 } }, grid: { color: '#1a1a1a' } },
            yScore: { position: 'right', min: 0, max: 100, ticks: { color: '#555', font: { size: 10 } }, grid: { drawOnChartArea: false } },
          },
        },
        plugins: [zoneBandsPlugin],
      });
    }

    function setChartWindow(w) {
      chartWindow = w;
      try { localStorage.setItem('kairos-chart-window', w); } catch (e) {}
      document.querySelectorAll('.cw-pill').forEach(function (el) {
        const active = el.getAttribute('data-cw') === w;
        el.classList.toggle('bg-on-surface', active);
        el.classList.toggle('text-deep-abyss', active);
        el.classList.toggle('font-bold', active);
        el.classList.toggle('text-on-surface-variant', !active);
      });
      if (detailId) renderChart(sliceChartData(BY_ID[detailId].chart, chartWindow));
    }

    // ---- view switching ----
    function showView(which) {
      document.getElementById('view-index').classList.toggle('hidden-view', which !== 'index');
      document.getElementById('view-details').classList.toggle('hidden-view', which !== 'details');
      window.scrollTo(0, 0);
    }

    function openDetails(id, skipHash) {
      const a = BY_ID[id];
      if (!a) return;
      detailId = id;
      document.getElementById('detail-name').textContent = a.display_name;
      document.getElementById('detail-subtitle').textContent = a.display_name.toUpperCase() + ' DETAILS';
      document.getElementById('detail-price').textContent = a.price_unit + a.price.toLocaleString() + '.00';

      const chg = a.price_change_24h;
      const chgEl = document.getElementById('detail-change');
      chgEl.textContent = (chg >= 0 ? '+' : '') + chg.toFixed(1) + '% (24H)';
      chgEl.style.color = chg >= 0 ? '#00ff88' : '#ffb4ab';

      document.getElementById('detail-hero-score').textContent = a.spectrum_pos.toFixed(1);
      const vEl = document.getElementById('detail-verdict');
      vEl.textContent = a.spectrum_verdict;
      vEl.style.color = a.score_color;
      document.getElementById('detail-desc').textContent = a.verdict_description;

      renderMetricCards(a);
      showView('details');
      setChartWindow(chartWindow); // also renders the chart for this asset
      if (!skipHash) { try { history.pushState({ view: 'details', id: id }, '', '#' + id); } catch (e) {} }
    }

    function closeDetails() {
      detailId = null;
      showView('index');
    }
```

- [ ] **Step 2: Build and screenshot-verify the details view**

Run: `python scripts/build_dashboard.py`
Expected: builds cleanly.

Verify with Playwright MCP:
1. `browser_navigate` to `file:///C:/Users/guill/Workspace/fbtc-timing/docs/index.html`
2. `browser_resize` 390×844
3. `browser_click` the Bitcoin card (ref from `browser_snapshot`)
4. `browser_take_screenshot` → compare to `specs/new-design/details_screen.png`

Expected: back arrow + KAIROS TERMINAL + settings gear; "Bitcoin" with "BITCOIN DETAILS • LIVE", price + green +x.x% (24H) on the right; pulse node showing `83.1 / COMPOSITE`; big emerald "STRONG BUY" + description sentence; metric cards (one per signal) each with reading colored by status and a cursor on the TP→Strong-Buy gauge; price-vs-composite Chart.js chart with 6M/1Y/2Y/All pills (1Y active). Clicking a chart pill reslices the chart.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: details view logic, metric cards, chart, view switching"
```

---

## Task 9: Boot wiring + hash routing + final verification

**Files:**
- Modify: `templates/dashboard.html.j2` (replace the temporary Task 6 boot snippet with the final unified boot block)

- [ ] **Step 1: Replace the temporary boot snippet**

Find the temporary boot snippet appended in Task 6 (at the end of the main `<script>` block):

```javascript
    document.querySelectorAll('.tf-pill').forEach(function (el) {
      el.addEventListener('click', function () { setTimeframe(el.getAttribute('data-tf')); });
    });
    renderIndexHeader();
    setTimeframe(timeframe);
```

Replace it with the final boot block:

```javascript
    // ---- event wiring ----
    document.querySelectorAll('.tf-pill').forEach(function (el) {
      el.addEventListener('click', function () { setTimeframe(el.getAttribute('data-tf')); });
    });
    document.querySelectorAll('.cw-pill').forEach(function (el) {
      el.addEventListener('click', function () { setChartWindow(el.getAttribute('data-cw')); });
    });
    document.getElementById('detail-back').addEventListener('click', function () {
      if (history.state && history.state.view === 'details') { history.back(); } else { closeDetails(); }
    });

    // Back/forward + refresh-with-hash routing
    window.addEventListener('popstate', function (e) {
      if (e.state && e.state.view === 'details' && BY_ID[e.state.id]) { openDetails(e.state.id, true); }
      else { closeDetails(); }
    });

    // ---- initial render ----
    renderIndexHeader();
    setTimeframe(timeframe);
    var initialId = (location.hash || '').replace('#', '');
    if (BY_ID[initialId]) { openDetails(initialId, true); } else { showView('index'); }
```

- [ ] **Step 2: Full rebuild + automated checks**

Run: `python scripts/build_dashboard.py`
Expected: `Dashboard written to docs/index.html (... bytes; 2 asset(s))`

Run the full Python suite to confirm no regression:

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 3: End-to-end UI verification with Playwright MCP**

1. `browser_navigate` to `file:///C:/Users/guill/Workspace/fbtc-timing/docs/index.html`; `browser_resize` 390×844.
2. `browser_console_messages` → expect no errors.
3. `browser_take_screenshot` (index) → matches `specs/new-design/index_screen.png`.
4. `browser_click` Bitcoin card → `browser_take_screenshot` (details) → matches `specs/new-design/details_screen.png`.
5. `browser_navigate_back` → confirm it returns to the index view (hash routing works).
6. Re-open details, switch a chart pill and a timeframe pill → `browser_console_messages` still clean.

Expected: both screens match their mockups (modulo the unified darker palette noted above); Back button returns to index; no console errors.

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: boot wiring and hash routing for two-view dashboard"
```

---

## Task 10: Cleanup of stray screenshot artifacts (optional)

**Files:**
- Delete: `mobile-390.png`, `mobile-after.png`, `mobile-before.png`, `mobile-final.png` (untracked scratch screenshots in repo root, per `git status`)

- [ ] **Step 1: Confirm they are throwaway and remove**

Run: `git status --short`
Expected: the four `mobile-*.png` files show as untracked (`??`).

If they are not needed (they are scratch design captures, not referenced by any page):

```bash
rm mobile-390.png mobile-after.png mobile-before.png mobile-final.png
```

- [ ] **Step 2: Commit (nothing to commit if already untracked-and-deleted; otherwise none needed)**

No commit required — these were never tracked. This step just tidies the working tree.

---

## Self-Review

**1. Spec coverage**

- index_DESIGN / index.html mockup: app bar with KAIROS + BTC price + updated time → Task 5/6. Day/Week/Month selector → Task 5 markup + Task 6 behavior (controls mini-bars). Token cards with verdict, conviction score, mini bar chart, spectrum zone band → Task 6 (`cardHTML`, `miniBarsHTML`, `spectrumBandHTML`). Bottom Alerts button → Task 5. Glow/pulse aesthetic → Task 4 styles + Task 5/6 Tailwind classes. ✔
- details_DESIGN / details.html mockup: back/title/settings header → Task 7 (settings is a no-op per decision 4). Context header (name, subtitle, LIVE, price, 24h change) → Task 7 markup + Task 8 populate (`price_change_24h` from Task 1/3). Hero pulse node (score + COMPOSITE) + verdict + description → Task 7 + Task 8 (`verdict_description` from Task 2/3). Metric cards per signal with reading + TP→Strong-Buy gauge + cursor → Task 8 (`renderMetricCards`, data-driven per decision 7). Price-vs-composite chart with window pills → Task 7 markup + Task 8 (`renderChart`/`sliceChartData`/`setChartWindow`, kept per decision 5). Bottom SET ALERTS → Task 7. ✔
- Navigation card→details, single-page, Back button → Task 6 (click wiring) + Task 8 (`openDetails`/`closeDetails`/`showView`) + Task 9 (hash routing, popstate). ✔
- Fonts Space Grotesk + JetBrains Mono → Task 4 head. ✔

**2. Placeholder scan**

No "TBD/TODO/handle edge cases" left. The only intentional staged placeholders are the HTML comment markers in Task 4 (`<!-- INDEX VIEW MARKUP -->`, etc.) and the Task 6 stub `openDetails`, each explicitly replaced by a named later task with full code. The Task 6 temporary boot snippet is explicitly replaced in Task 9.

**3. Type / name consistency**

- IDs match between markup and JS: `token-list`, `idx-btc-price`, `idx-updated`, `tf-pill`, `asset-card` (Task 5/6); `detail-back`, `detail-name`, `detail-subtitle`, `detail-price`, `detail-change`, `detail-hero-score`, `detail-verdict`, `detail-desc`, `metric-cards`, `detail-chart`, `cw-pill` (Task 7/8/9). ✔
- Function names stable: `zoneColor`, `zoneIndex`, `miniBarsHTML`, `spectrumBandHTML`, `cardHTML`, `renderIndexCards`, `setTimeframe`, `renderIndexHeader` (Task 6); `openDetails`/`closeDetails` (stub in 6 → full in 8), `metricColor`, `metricCardHTML`, `renderMetricCards`, `sliceChartData`, `renderChart`, `setChartWindow`, `showView` (Task 8); boot wiring references all of these (Task 9). ✔
- Blob keys used by JS exist in the data: `spectrum_pos`, `spectrum_verdict`, `score_color`, `short_label`, `display_name`, `price`, `price_unit`, `trend[window].spark[].score`, `signals[].{display_name,reading,bar.{has_data,cursor_pct,status_class}}`, `chart.{dates,prices,scores}` (pre-existing) plus `price_change_24h`, `verdict_description` (added in Tasks 1–3). ✔
- Python: `compute_price_change_24h(price_df)` and `verdict_description(spectrum_verdict)` defined in Task 1/2 and called in Task 3 with matching signatures. ✔

---

## Execution notes

- Run all Python commands from the repo root `C:\Users\guill\Workspace\fbtc-timing`. `python` resolves to the project interpreter that has the `requirements.txt` deps installed (pandas, numpy, jinja2, pytest).
- `docs/index.html` is generated — never hand-edit it; always rerun `python scripts/build_dashboard.py` after changing `templates/dashboard.html.j2` and commit both.
- The existing `docs/enable-alerts.html` and `docs/sw.js` are untouched and the alerts links keep pointing at them.
