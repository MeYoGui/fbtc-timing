---
name: Kairos Performance Dashboard
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#3a3939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#bacbb9'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#859585'
  outline-variant: '#3b4a3d'
  surface-tint: '#00e475'
  primary: '#75ff9e'
  on-primary: '#003918'
  primary-container: '#00e676'
  on-primary-container: '#00612e'
  inverse-primary: '#006d35'
  secondary: '#ffb4aa'
  on-secondary: '#690003'
  secondary-container: '#c5020b'
  on-secondary-container: '#ffd2cc'
  tertiary: '#ffdec4'
  on-tertiary: '#4b2800'
  tertiary-container: '#ffba79'
  on-tertiary-container: '#794810'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#62ff96'
  primary-fixed-dim: '#00e475'
  on-primary-fixed: '#00210b'
  on-primary-fixed-variant: '#005226'
  secondary-fixed: '#ffdad5'
  secondary-fixed-dim: '#ffb4aa'
  on-secondary-fixed: '#410001'
  on-secondary-fixed-variant: '#930005'
  tertiary-fixed: '#ffdcbf'
  tertiary-fixed-dim: '#fdb878'
  on-tertiary-fixed: '#2d1600'
  on-tertiary-fixed-variant: '#6a3c03'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
  buy-vibrant: '#00E676'
  buy-steady: '#00C853'
  sell-urgent: '#FF3B30'
  hold-neutral: '#D0D0D0'
  surface-charcoal: '#161616'
  border-subtle: rgba(255, 255, 255, 0.08)
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-base:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  data-lg:
    fontFamily: JetBrains Mono
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  data-sm:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 16px
  gutter: 12px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 24px
---

## Brand & Style

This design system is engineered for **Kairos**, a high-conviction crypto market-timing dashboard. The brand personality is technical, precise, and authoritative, catering to experienced traders who value signal over noise. 

The visual direction follows a **Technical Minimalism** aesthetic with **Subtle Glassmorphism**. It prioritizes data density and "at-a-glance" cognitive efficiency. The UI evokes the feeling of a professional trading terminal—dark, focused, and high-performance. Every element is designed to minimize distraction, using light and color only to signal actionable market opportunities.

## Colors

The palette is anchored in a **Deep Charcoal/Black** environment to maximize contrast for technical indicators.

- **Primary (Action):** Vibrant Emerald Green (`#00E676`) represents "Strong Buy" signals and primary CTA actions.
- **Secondary (Sentiment):** A sharp Deep Red (`#FF3B30`) is reserved exclusively for "Sell/Take Profit" signals and critical alerts.
- **Neutral:** Mid-tone greys (`#D0D0D0`) are used for "Hold" states and secondary data, ensuring they recede when compared to Buy/Sell signals.
- **Backgrounds:** The primary surface is `#0D0D0D`, with secondary containers at `#161616`. 

Use a linear gradient for sentiment gauges ranging from `#FF3B30` (0%) to `#D0D0D0` (50%) to `#00E676` (100%).

## Typography

The typography system uses a dual-font approach to distinguish between UI narrative and technical data.

- **Inter:** Used for all interface headings, body copy, and navigation. It provides a modern, clean, and highly readable foundation.
- **JetBrains Mono:** Used for all numerical data, timestamps, and ticker symbols. The monospaced nature ensures that fluctuating numbers don't cause layout "jitter" and reinforces the technical dashboard feel.

**Hierarchy Strategy:** Use `label-caps` for table headers and metadata categories. Use `data-lg` for primary price points or signal percentages.

## Layout & Spacing

The system utilizes a **Fixed Grid** on desktop (max-width 1200px) and a **Fluid 4-column Grid** for mobile. 

- **Density:** High. Margins and padding are kept tight (`16px` outer margins) to maximize the amount of data visible without scrolling.
- **Mobile-First:** As a PWA, the layout prioritizes a vertical stack of "Signal Cards." 
- **Rhythm:** A 4px baseline grid ensures consistent alignment of technical data points and icons.
- **Reflow:** On desktop, the single-column mobile feed expands into a 3-column dashboard: Signals (Left), Charting (Center), and Activity Feed (Right).

## Elevation & Depth

Depth is communicated through **Tonal Layering** and **Subtle Glassmorphism** rather than traditional shadows.

- **Level 0 (Background):** `#0D0D0D` - The base layer.
- **Level 1 (Cards):** `#161616` with a `1px` solid border of `rgba(255, 255, 255, 0.08)`.
- **Level 2 (Overlays/Modals):** A semi-transparent surface (`rgba(22, 22, 22, 0.8)`) with a `20px` backdrop-blur. 

Shadows, if used, are extremely subtle: `0 4px 20px rgba(0, 0, 0, 0.5)`, used only to lift active modals above the data grid.

## Shapes

The shape language is "Soft-Industrial." 

- **Components:** Standard buttons and input fields use a `0.25rem` (4px) corner radius to maintain a precise, technical look.
- **Cards:** Larger containers use `rounded-lg` (8px) to provide a subtle distinction between the container and the elements inside it.
- **Status Indicators:** Use circular dots for live status (e.g., "Market Open") and small, squared-off chips for category tags.

## Components

- **Signal Cards:** These are the primary unit of the UI. Use a low-profile card with a thin `#FFFFFF14` border. The top-right corner should feature a high-contrast Buy/Sell/Hold badge using the named brand colors.
- **Data Action Buttons:** Buttons should be full-width on mobile. Primary Buy/Sell buttons use high-saturation backgrounds with black text for maximum legibility. Secondary buttons use the "Ghost" style (transparent background, thin border).
- **Sentiment Gauges:** Horizontal bars showing the spectrum from Red to Green. The "Current State" is indicated by a white vertical needle or a high-glow indicator.
- **Micro-Charts (Sparklines):** Simplified trend lines within cards. Use `primary-color` (Green) for uptrends and `secondary-color` (Red) for downtrends. Sparklines should be monochromatic with a subtle gradient fill below the line.
- **Inputs:** Dark-filled fields (`#0D0D0D`) with a subtle `1px` border that glows primary-green when focused. Use JetBrains Mono for text entry.
- **Technical Chips:** Small, condensed labels used for timeframes (e.g., 1H, 4H, 1D). Active states use a solid white background with black text.