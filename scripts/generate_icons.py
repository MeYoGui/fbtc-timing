"""
One-time generator for the Kairos PWA icons.

Rasterizes the locked icon SVG (see specs/kairos-icon-reference.html) into the
three PNG sizes the manifest needs. Run manually after any icon change:

    python scripts/generate_icons.py

Requires cairosvg (preferred) or playwright (fallback, local dev dependency,
NOT in requirements.txt):
    pip install cairosvg          # Linux/macOS with libcairo
    pip install playwright && python -m playwright install chromium  # Windows fallback
"""
from pathlib import Path

ICONS_DIR = Path(__file__).parent.parent / "docs" / "icons"

# Shared inner artwork: waveform polyline, green dot, and KAIROS wordmark.
# Embedded into both SVG templates via string concatenation so {size} can
# still be resolved with a plain .format(size=size) call at render time.
_ARTWORK = """
    <polyline points="14,65 36,65 50,22 64,108 78,40 92,65 128,65"
      fill="none" stroke="url(#grad)" stroke-width="6"
      stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="128" cy="65" r="7" fill="#00c853" filter="url(#glow)"/>
    <text font-size="19" font-family="sans-serif" font-weight="700">
      <tspan x="47"  y="140" fill="#ff6b3d">K</tspan>
      <tspan x="61"  y="140" fill="#ffa033">A</tspan>
      <tspan x="73"  y="140" fill="#ffd740" filter="url(#glow-i)">I</tspan>
      <tspan x="82"  y="140" fill="#80d94a">R</tspan>
      <tspan x="97"  y="140" fill="#00c853">O</tspan>
      <tspan x="112" y="140" fill="#00c853">S</tspan>
    </text>
"""

_DEFS = """
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="#ff5252"/>
      <stop offset="45%"  stop-color="#ffd740"/>
      <stop offset="100%" stop-color="#00c853"/>
    </linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="glow-i"><feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
"""

# The pulse-waveform + KAIROS wordmark, on a #0d0d0d rounded square.
# Differs from MASKABLE_SVG: rx="34" background rect, translate(0, 6) wrapper.
ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 160 160">'
    + _DEFS
    + '<rect x="0" y="0" width="160" height="160" rx="34" fill="#0d0d0d"/>'
    + '<g transform="translate(0, 6)">'
    + _ARTWORK
    + '</g>'
    + '</svg>'
)

# Maskable variant: same artwork scaled into the central ~72% safe zone,
# full #0d0d0d background bleeding to all edges so Android's adaptive mask
# never clips the waveform or wordmark.
# Differs from ICON_SVG: no rx on background rect, translate(22, 28) scale(0.72) wrapper.
MASKABLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 160 160">'
    + _DEFS
    + '<rect x="0" y="0" width="160" height="160" fill="#0d0d0d"/>'
    + '<g transform="translate(22, 28) scale(0.72)">'
    + _ARTWORK
    + '</g>'
    + '</svg>'
)


def _render_cairosvg(svg: str, size: int, out_path: Path) -> None:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                     write_to=str(out_path),
                     output_width=size, output_height=size)


def _render_playwright(svg: str, size: int, out_path: Path) -> None:
    """Fallback renderer using a headless Chromium browser (Windows-friendly)."""
    from playwright.sync_api import sync_playwright
    import base64

    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    data_url = f"data:image/svg+xml;base64,{encoded}"
    html = (
        f"<html><body style='margin:0;padding:0;background:#0d0d0d'>"
        f"<img src='{data_url}' width='{size}' height='{size}' "
        f"style='display:block'></body></html>"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size})
        page.set_content(html)
        page.wait_for_load_state("networkidle")
        png_bytes = page.screenshot(
            clip={"x": 0, "y": 0, "width": size, "height": size},
            type="png",
        )
        browser.close()
    out_path.write_bytes(png_bytes)


def render(svg_template: str, size: int, out_name: str, renderer: str) -> None:
    svg = svg_template.format(size=size)
    out_path = ICONS_DIR / out_name
    if renderer == "cairosvg":
        _render_cairosvg(svg, size, out_path)
    else:
        _render_playwright(svg, size, out_path)
    print(f"wrote {out_path.relative_to(ICONS_DIR.parent.parent)} ({size}x{size})")


def _pick_renderer() -> str:
    try:
        import cairosvg  # noqa: F401 — import triggers the native-lib check
        return "cairosvg"
    except (ImportError, OSError):
        try:
            import playwright  # noqa: F401
            return "playwright"
        except ImportError:
            raise RuntimeError(
                "No SVG renderer found.\n"
                "  On Linux/macOS: pip install cairosvg\n"
                "  On Windows:     pip install playwright && "
                "python -m playwright install chromium"
            )


def main() -> None:
    renderer = _pick_renderer()
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    render(ICON_SVG, 192, "icon-192.png", renderer)
    render(ICON_SVG, 512, "icon-512.png", renderer)
    render(MASKABLE_SVG, 512, "icon-512-maskable.png", renderer)
    print("Done. Icons written to docs/icons/")


if __name__ == "__main__":
    main()
