# Multi-Asset Framework — Design Spec
**Date:** 2026-06-02

## Goal

Convert the Kairos dashboard from a hard-coded single-asset (Bitcoin) pipeline into a **config-driven, multi-asset-ready architecture**, and introduce the **score-chip multi-asset UI**. Bitcoin remains the only configured asset in this scope; the deliverable is the foundation plus UI so that adding a second ticker later (likely Ethereum, which reuses the existing crypto signals) is just a new config file — no pipeline changes.

This is the foundation-only slice of a larger multi-asset vision. Non-crypto assets (e.g., gold) and the new data sources / signal types / backtest semantics they require are explicitly **out of scope** here and will be designed separately when a non-crypto asset is actually added.

## Visual Reference

The chosen UI is locked. See `specs/2026-06-02-multi-asset-ui-reference.png` — the in-scope layout: a single zone-colored **Bitcoin** score chip (score, verdict, mini-sparkline) selected with its accent-colored border, followed by a dimmed dashed **"+ more coming"** placeholder chip, expanding into the full existing dashboard (trend toggle, score card, zone strip, sparkline, signal table) below. The implementation should match this.

---

## Background — current architecture

The pipeline is five scripts run in sequence, all assuming Bitcoin:

1. `fetch_data.py` → `data/btc_history.csv` (price, market cap, MVRV, miner revenue, fear & greed)
2. `compute_signals.py` → `data/signal_history.csv` + `data/current_signals.json` (6 signals)
3. `score.py` → `data/current_score.json` (weighted composite + verdict + signal meta)
4. `backtest.py` → `data/weights.json` (weights from signal precision vs halving-cycle "good entries")
5. `build_dashboard.py` → `docs/index.html`

The 6 signals: `mvrv_zscore`, `ma_200w`, `monthly_rsi`, `pi_cycle`, `puell`, `fear_greed`. Bitcoin-specific knowledge is currently scattered across all five scripts (CoinMetrics asset code `btc`, halving dates, signal thresholds, display metadata).

---

## What Changes

### 1. New `assets/` package — per-asset configs

A new package `assets/` holds one module per asset plus a registry.

**`assets/registry.py`** — exposes the ordered list of configured assets:

```python
from assets import bitcoin
ASSETS = [bitcoin.CONFIG]   # Ethereum/gold appended here later
```

**`assets/base.py`** — defines the `AssetConfig` dataclass (the interface every asset must satisfy):

```python
@dataclass
class AssetConfig:
    id: str                 # "bitcoin" — used in filenames, JSON keys, DOM ids
    display_name: str       # "Bitcoin"
    short_label: str        # "₿ Bitcoin" (chip label)
    accent_color: str       # "#f7931a"
    price_unit: str         # "$" prefix / display format for the header price
    fetch: Callable[[], pd.DataFrame]          # returns history DataFrame with a "date" column
    signals: list[SignalSpec]                  # which signals + thresholds, ordered for display
    good_entry: Callable[[pd.DataFrame], pd.Series]  # backtest target (bool series)
    weight_overrides: dict | None = None       # optional (e.g., Bitcoin's MVRV 2× anchor)
```

`SignalSpec` binds a shared signal function to this asset's thresholds and display metadata:

```python
@dataclass
class SignalSpec:
    key: str                # "mvrv_zscore"
    display_name: str       # "MVRV Z-Score"
    compute: Callable[[pd.DataFrame], pd.Series]   # raw-value series from the shared library
    invest_thresh: float
    avoid_thresh: float
    range_lo: float
    range_hi: float
    fmt: str                # "{:.1f}"
```

Scoring direction is encoded by the ordering of `invest_thresh` vs `avoid_thresh` (as in today's `signal_score`); all current signals are "lower raw value = more invest," so no separate direction flag is needed.

**`assets/signals.py`** — the shared signal **function library**. The six existing computations (`compute_mvrv_zscore`, `compute_200w_ma_ratio`, `compute_monthly_rsi`, `compute_pi_cycle_ratio`, `compute_puell_multiple`, plus the pass-through for `fear_greed`) move here, unchanged, so any asset's config can reference them. This is the mechanism that makes "Ethereum later" a config-only job: a crypto asset reuses these same functions with its own thresholds and CoinMetrics asset code.

**`assets/bitcoin.py`** — Bitcoin's config. Holds everything currently Bitcoin-specific: the CoinMetrics/blockchain.info/alternative.me fetchers (moved from `fetch_data.py`), the six `SignalSpec`s with today's exact thresholds (from `score.py`'s `SIGNAL_META` and `compute_signals.py`'s score calls), the halving-cycle `good_entry` function (moved from `backtest.py`), and the MVRV 2× `weight_overrides` (moved from `backtest.py`).

### 2. Generic pipeline — loop over the registry

Each script keeps its filename and CLI behaviour but iterates over `ASSETS`:

- **`fetch_data.py`**: for each asset, call `config.fetch()` → `data/{id}_history.csv`
- **`compute_signals.py`**: for each asset, run its `SignalSpec`s → `data/{id}_signal_history.csv` + `data/{id}_current_signals.json`
- **`score.py`**: for each asset → `data/{id}_score.json` (includes `signal_meta` built from the asset's `SignalSpec`s)
- **`backtest.py`**: for each asset, label good entries via `config.good_entry`, derive weights by precision (+ optional `weight_overrides`) → `data/{id}_weights.json`
- **`build_dashboard.py`**: load every asset's artifacts, compute the trend layer per asset, render a single `docs/index.html` with all assets embedded

**Data file namespacing:** all per-asset files become `{id}_*` (e.g., `bitcoin_history.csv`, `bitcoin_signal_history.csv`, `bitcoin_score.json`, `bitcoin_weights.json`). The existing `btc_history.csv` / `signal_history.csv` / `current_score.json` / `weights.json` are renamed accordingly. `replay.py` and tests are updated to the new names.

### 3. Score-chip multi-asset UI (Option C)

`templates/dashboard.html.j2` gains a chip row above the score card:

- **One chip per configured asset**, each showing: short label, composite score (zone-colored), verdict, and a mini 7-point sparkline. With one asset today, a single **Bitcoin** chip renders, selected by default and expanded into the full existing dashboard below (score card, zone strip, sparkline, trend toggle, signal table — all unchanged).
- A dimmed, non-interactive **"+ more coming"** placeholder chip follows the real chips, signaling extensibility without a dead control.
- Clicking a chip switches the whole dashboard to that asset **client-side** — all assets' data (score, signals, trend windows, sparklines) are embedded as JSON at build time, same pattern as the existing trend layer (`{{ trend_data_json }}`). No network requests.
- Selected asset persists in `localStorage` (key `kairos-asset`), defaulting to the first configured asset.
- Each asset's accent color tints its selected chip.

The header price line shows the selected asset's price/unit. The KAIROS wordmark, PWA tags, favicon, and methodology section are unchanged.

### 4. Per-asset / per-signal resilience

The pipeline isolates failures so one feed breaking cannot take down the build:

- A signal whose data is missing/NaN renders as "No data" (the existing `has_data: false` bar path already handles this).
- If an asset's `fetch()` fails entirely, that asset is skipped with a logged warning; the dashboard still builds for the remaining assets. With one asset today this is low-stakes, but it is the correct foundation for multiple feeds.

---

## What Does Not Change

- The 6 Bitcoin signals, their thresholds, scoring, weights, and the resulting composite/verdict — **byte-identical output**, enforced by a golden-master test (see Verification) plus the existing 39 tests.
- The score card, zone strip, signal range bars, trend layer (day/week/month + sparkline + arrows), chart, and methodology section.
- PWA behaviour, icons, the daily 13:00-UTC schedule, the secret-free / keyless deploy.
- No new external data sources, no new signal types, no new backtest semantics.

---

## File Structure

| File | Action |
|---|---|
| `assets/__init__.py` | Create (package marker) |
| `assets/base.py` | Create — `AssetConfig`, `SignalSpec` dataclasses |
| `assets/signals.py` | Create — shared signal function library (moved from `compute_signals.py`) |
| `assets/bitcoin.py` | Create — Bitcoin config (fetchers, signal specs, halving good-entry, weight overrides) |
| `assets/registry.py` | Create — `ASSETS` list |
| `scripts/fetch_data.py` | Modify — loop over registry, `{id}_history.csv` |
| `scripts/compute_signals.py` | Modify — loop, delegate to shared signals, `{id}_*` outputs |
| `scripts/score.py` | Modify — loop, build signal_meta from specs, `{id}_score.json` |
| `scripts/backtest.py` | Modify — loop, per-asset good-entry + weight overrides, `{id}_weights.json` |
| `scripts/build_dashboard.py` | Modify — load all assets, embed all data, render chip UI |
| `scripts/replay.py` | Modify — new data filenames |
| `templates/dashboard.html.j2` | Modify — chip row, placeholder chip, client-side asset switch JS |
| `data/btc_history.csv` → `data/bitcoin_history.csv` (+ other renames) | Rename |
| `tests/` | Modify/Add — golden-master parity test, framework + config tests |

---

## Verification

1. **Golden-master parity:** before refactor, snapshot Bitcoin's `current_score.json` (composite, verdict, all signal scores). After refactor, the regenerated values must match exactly. Add as a test.
2. `python -m pytest -q` → existing 39 tests pass (updated for new filenames), plus new framework/config tests.
3. `python scripts/fetch_data.py && python scripts/compute_signals.py && python scripts/score.py && python scripts/backtest.py && python scripts/build_dashboard.py` runs clean end-to-end.
4. Open `docs/index.html`: a single Bitcoin chip (score, verdict, mini-trend) + a dimmed "+ more coming" chip; the full dashboard renders below identically to today; the trend toggle still works.
5. Add a throwaway second config locally (e.g., a copy of Bitcoin under a different id) and confirm a second chip appears and switching works — then remove it. (Proves the framework before committing.)
6. Push; verify live on GitHub Pages.

---

## Risks / Known Gotchas

- **Big refactor breaking Bitcoin** — mitigated by the golden-master parity test and behaviour-preserving moves (code is relocated into configs, not rewritten).
- **Single-asset UI** — a score-chip switcher with one real chip looks sparse; the "+ more coming" placeholder is the deliberate mitigation, and the UI activates fully when a second config lands.
- **Data filename migration** — `replay.py`, tests, and any cached local data reference old names; all must be updated in lockstep. The git history of `data/*.csv` is preserved through `git mv`.
- **Embedded payload growth** — embedding every asset's trend data grows `index.html`; negligible at 1–2 assets, revisit if many assets are added.
- **Deferred, not solved** — the gold-specific risks from the adversarial review (macro-signal regime decoupling, drawdown/target circularity, COT fragility, threshold calibration, keyless-FRED throttling) are intentionally deferred with gold; they must be revisited when a non-crypto asset is designed.
