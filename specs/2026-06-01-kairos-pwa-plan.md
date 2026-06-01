# Kairos PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard installable as a home-screen app named "Kairos" on Android and iOS, launching fullscreen with always-fresh data (no caching).

**Architecture:** Add three static files to `docs/` (manifest, no-op service worker, icon PNGs), a one-time Python icon generator, and PWA `<head>` tags + service-worker registration to the Jinja2 template. Nothing in the data pipeline changes.

**Tech Stack:** Static HTML/JSON/JS, Python 3.11 + cairosvg (local icon generation only), Jinja2 template.

**Spec:** `specs/2026-06-01-kairos-pwa-design.md`
**Icon reference:** `specs/kairos-icon-reference.html` (exact SVG), `specs/kairos-icon-reference.png` (visual)

---

## Critical Gotcha (read before starting)

The site is served from `https://meyogui.github.io/fbtc-timing/`, **not** the domain root. Every absolute path in this plan uses the `/fbtc-timing/` prefix — manifest `start_url`/`scope`/`icons`, the `apple-touch-icon` href, the manifest link, and the service-worker registration path. A wrong prefix makes Chrome **silently** refuse the install prompt with no error. Do not "simplify" these to `/`.

---

## File Map

| File | Responsibility |
|---|---|
| `scripts/generate_icons.py` | One-time script: rasterize the locked SVG into 3 PNG icons |
| `docs/icons/icon-192.png` | 192×192 app icon (generated) |
| `docs/icons/icon-512.png` | 512×512 app icon (generated) |
| `docs/icons/icon-512-maskable.png` | 512×512 maskable icon with safe-zone padding (generated) |
| `docs/manifest.json` | PWA manifest — declares the installable app |
| `docs/sw.js` | No-op service worker (enables install, no caching) |
| `templates/dashboard.html.j2` | Add PWA head tags, change title, register SW |

---

## Task 1: Icon generator script

**Files:**
- Create: `scripts/generate_icons.py`
- Create (output): `docs/icons/icon-192.png`, `docs/icons/icon-512.png`, `docs/icons/icon-512-maskable.png`

- [ ] **Step 1: Install cairosvg locally**

Run:
```
pip install cairosvg
```
Expected: `Successfully installed cairosvg-...` (and its deps cairocffi, cssselect2, tinycss2). This is a local dev dependency only — do NOT add it to `requirements.txt`.

- [ ] **Step 2: Create `scripts/generate_icons.py`**

This script embeds the locked icon SVG twice: once as the "full bleed" artwork (for `icon-192` and `icon-512`), and once scaled to a ~72% safe zone on a solid background (for the maskable variant). It rasterizes each to PNG with cairosvg.

```python
"""
One-time generator for the Kairos PWA icons.

Rasterizes the locked icon SVG (see specs/kairos-icon-reference.html) into the
three PNG sizes the manifest needs. Run manually after any icon change:

    python scripts/generate_icons.py

Requires cairosvg (local dev dependency, NOT in requirements.txt):
    pip install cairosvg
"""
from pathlib import Path

import cairosvg

ICONS_DIR = Path(__file__).parent.parent / "docs" / "icons"

# The pulse-waveform + KAIROS wordmark, on a #0d0d0d rounded square.
# viewBox 0 0 160 148 matches the locked reference exactly.
ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 160 160">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#ff5252"/>
      <stop offset="45%"  stop-color="#ffd740"/>
      <stop offset="100%" stop-color="#00c853"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="160" height="160" rx="34" fill="#0d0d0d"/>
  <g transform="translate(0, 6)">
    <polyline points="14,65 36,65 50,22 64,108 78,40 92,65 128,65"
      fill="none" stroke="url(#grad)" stroke-width="6"
      stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="128" cy="65" r="7" fill="#00c853"/>
    <text font-size="19" font-family="sans-serif" font-weight="700">
      <tspan x="47"  y="140" fill="#ff6b3d">K</tspan>
      <tspan x="61"  y="140" fill="#ffa033">A</tspan>
      <tspan x="73"  y="140" fill="#ffd740">I</tspan>
      <tspan x="82"  y="140" fill="#80d94a">R</tspan>
      <tspan x="97"  y="140" fill="#00c853">O</tspan>
      <tspan x="112" y="140" fill="#00c853">S</tspan>
    </text>
  </g>
</svg>
"""

# Maskable variant: same artwork scaled into the central ~72% safe zone,
# full #0d0d0d background bleeding to all edges so Android's adaptive mask
# never clips the waveform or wordmark.
MASKABLE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 160 160">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#ff5252"/>
      <stop offset="45%"  stop-color="#ffd740"/>
      <stop offset="100%" stop-color="#00c853"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="160" height="160" fill="#0d0d0d"/>
  <g transform="translate(22, 28) scale(0.72)">
    <polyline points="14,65 36,65 50,22 64,108 78,40 92,65 128,65"
      fill="none" stroke="url(#grad)" stroke-width="6"
      stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="128" cy="65" r="7" fill="#00c853"/>
    <text font-size="19" font-family="sans-serif" font-weight="700">
      <tspan x="47"  y="140" fill="#ff6b3d">K</tspan>
      <tspan x="61"  y="140" fill="#ffa033">A</tspan>
      <tspan x="73"  y="140" fill="#ffd740">I</tspan>
      <tspan x="82"  y="140" fill="#80d94a">R</tspan>
      <tspan x="97"  y="140" fill="#00c853">O</tspan>
      <tspan x="112" y="140" fill="#00c853">S</tspan>
    </text>
  </g>
</svg>
"""


def render(svg_template: str, size: int, out_name: str) -> None:
    svg = svg_template.format(size=size)
    out_path = ICONS_DIR / out_name
    cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                     write_to=str(out_path),
                     output_width=size, output_height=size)
    print(f"wrote {out_path.relative_to(ICONS_DIR.parent.parent)} ({size}x{size})")


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    render(ICON_SVG, 192, "icon-192.png")
    render(ICON_SVG, 512, "icon-512.png")
    render(MASKABLE_SVG, 512, "icon-512-maskable.png")
    print("Done. Icons written to docs/icons/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the generator**

Run:
```
python scripts/generate_icons.py
```
Expected output:
```
wrote docs/icons/icon-192.png (192x192)
wrote docs/icons/icon-512.png (512x512)
wrote docs/icons/icon-512-maskable.png (512x512)
Done. Icons written to docs/icons/
```

- [ ] **Step 4: Verify the PNGs exist and have correct dimensions**

Run:
```
python -c "from PIL import Image; import glob; [print(f, Image.open(f).size) for f in sorted(glob.glob('docs/icons/*.png'))]"
```
Expected:
```
docs/icons/icon-192.png (192, 192)
docs/icons/icon-512-maskable.png (512, 512)
docs/icons/icon-512.png (512, 512)
```
(If PIL/Pillow is not installed, run `pip install pillow` first — also a local-only check, not a runtime dependency.)

- [ ] **Step 5: Visually verify the generated icon matches the reference**

Open `docs/icons/icon-192.png` in an image viewer. Compare against `specs/kairos-icon-reference.png`: red→yellow→green pulse waveform, glowing green dot at the right tip, "KAIROS" centered below in matching gradient, dark `#0d0d0d` rounded background. They should match.

- [ ] **Step 6: Commit**

```
git add scripts/generate_icons.py docs/icons/icon-192.png docs/icons/icon-512.png docs/icons/icon-512-maskable.png
git commit -m "feat: add Kairos PWA icon generator and generated icons"
```

---

## Task 2: Web app manifest

**Files:**
- Create: `docs/manifest.json`

- [ ] **Step 1: Create `docs/manifest.json`**

Note every path carries the `/fbtc-timing/` prefix (GitHub Pages subpath).

```json
{
  "name": "Kairos",
  "short_name": "Kairos",
  "description": "Know the opportune moment to invest.",
  "start_url": "/fbtc-timing/",
  "scope": "/fbtc-timing/",
  "display": "standalone",
  "background_color": "#0d0d0d",
  "theme_color": "#0d0d0d",
  "orientation": "portrait",
  "icons": [
    { "src": "/fbtc-timing/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/fbtc-timing/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/fbtc-timing/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

- [ ] **Step 2: Validate the JSON parses**

Run:
```
python -c "import json; d=json.load(open('docs/manifest.json')); print(d['name'], d['scope'], len(d['icons']), 'icons')"
```
Expected:
```
Kairos /fbtc-timing/ 3 icons
```

- [ ] **Step 3: Commit**

```
git add docs/manifest.json
git commit -m "feat: add PWA web app manifest"
```

---

## Task 3: Service worker (no-op)

**Files:**
- Create: `docs/sw.js`

- [ ] **Step 1: Create `docs/sw.js`**

```js
// Kairos service worker — intentionally no caching.
// Exists only to satisfy the PWA installability requirement (Chrome/Android
// require a registered service worker to offer "Add to Home Screen").
// There is no 'fetch' handler, so every request goes straight to the network
// and the dashboard always shows fresh data.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
```

- [ ] **Step 2: Verify the file is syntactically valid JavaScript**

Run (node is available via the environment; if not, skip — this is a sanity check only):
```
node --check docs/sw.js && echo "sw.js OK"
```
Expected: `sw.js OK`

- [ ] **Step 3: Commit**

```
git add docs/sw.js
git commit -m "feat: add no-op service worker for PWA installability"
```

---

## Task 4: Template PWA tags and SW registration

**Files:**
- Modify: `templates/dashboard.html.j2`

- [ ] **Step 1: Change the page title and add PWA head tags**

In `templates/dashboard.html.j2`, find this block in `<head>`:

```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FBTC Market Timing</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

Replace it with:

```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kairos</title>
  <link rel="manifest" href="/fbtc-timing/manifest.json">
  <meta name="theme-color" content="#0d0d0d">
  <link rel="apple-touch-icon" href="/fbtc-timing/icons/icon-192.png">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Kairos">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

- [ ] **Step 2: Add the service-worker registration before `</body>`**

In `templates/dashboard.html.j2`, find the closing `</body>` tag (the very last lines of the file, after the existing `<script>` that builds the Chart.js chart). Immediately before `</body>`, add:

```html
  <script>
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/fbtc-timing/sw.js').catch(() => {});
      });
    }
  </script>
</body>
```

(That is: insert the new `<script>` block, keeping the existing `</body>` after it.)

- [ ] **Step 3: Rebuild the dashboard**

Run:
```
python scripts/build_dashboard.py
```
Expected: `Dashboard written to docs/index.html (...)` with no errors.

- [ ] **Step 4: Verify the rendered HTML contains the PWA tags**

Run:
```
python -c "h=open('docs/index.html',encoding='utf-8').read(); print('manifest' , '/fbtc-timing/manifest.json' in h); print('title', '<title>Kairos</title>' in h); print('apple-icon', '/fbtc-timing/icons/icon-192.png' in h); print('sw-register', \"register('/fbtc-timing/sw.js')\" in h)"
```
Expected:
```
manifest True
title True
apple-icon True
sw-register True
```

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run:
```
python -m pytest -v
```
Expected: all 30 tests PASS (no test touches the template, so this just confirms no regression).

- [ ] **Step 6: Commit**

```
git add templates/dashboard.html.j2 docs/index.html
git commit -m "feat: add PWA head tags and service worker registration to dashboard"
```

---

## Task 5: End-to-end verification and deploy

**Files:** none (verification + push only)

- [ ] **Step 1: Confirm all PWA files are present in docs/**

Run:
```
python -c "from pathlib import Path; [print(p, Path(p).exists()) for p in ['docs/manifest.json','docs/sw.js','docs/icons/icon-192.png','docs/icons/icon-512.png','docs/icons/icon-512-maskable.png']]"
```
Expected: all five lines end in `True`.

- [ ] **Step 2: Push to GitHub**

```
git push origin main
```

- [ ] **Step 3: Wait for GitHub Pages to deploy, then verify the manifest is reachable**

After ~1 minute, run:
```
python -c "import urllib.request, json; d=json.load(urllib.request.urlopen('https://meyogui.github.io/fbtc-timing/manifest.json')); print('manifest live:', d['name'], d['scope'])"
```
Expected: `manifest live: Kairos /fbtc-timing/`

If this 404s, the GitHub Pages deploy hasn't finished yet — wait and retry. If it persists, confirm GitHub Pages is enabled on branch `main`, folder `/docs`.

- [ ] **Step 4: Verify the icon is reachable**

```
python -c "import urllib.request; r=urllib.request.urlopen('https://meyogui.github.io/fbtc-timing/icons/icon-192.png'); print('icon HTTP', r.status, r.headers['Content-Type'])"
```
Expected: `icon HTTP 200 image/png`

- [ ] **Step 5: Manual install test (Android)**

On an Android phone, open Chrome and visit `https://meyogui.github.io/fbtc-timing/`. Chrome should show an install banner or an "Install app" / "Add to Home screen" option in the ⋮ menu. Install it. Confirm:
- The home-screen icon is the Kairos pulse icon
- The app name reads "Kairos"
- Launching opens fullscreen (no browser address bar)
- The "Updated" date in the dashboard matches today's pipeline run (fresh data, not cached)

- [ ] **Step 6: Manual install test (iPhone, iOS 16.4+)**

On an iPhone, open Safari and visit `https://meyogui.github.io/fbtc-timing/`. Tap Share → Add to Home Screen. Confirm the suggested name is "Kairos" and the icon is correct. Add it, launch it, confirm fullscreen + fresh data.

---

## Notes for the implementer

- **Do not** add `cairosvg` or `pillow` to `requirements.txt`. They are local-only tools for generating/verifying icons. The daily GitHub Actions workflow never regenerates icons — the PNGs are committed static assets.
- **Do not** add a `fetch` handler to `sw.js`. The whole point is no caching — fresh data every load.
- **Do not** change the `/fbtc-timing/` path prefix anywhere. It is required because GitHub Pages serves this repo from a subpath.
- No data-pipeline files (`fetch_data.py`, `compute_signals.py`, `score.py`, `build_dashboard.py`) change in this plan. `build_dashboard.py` is only *run*, not edited.
