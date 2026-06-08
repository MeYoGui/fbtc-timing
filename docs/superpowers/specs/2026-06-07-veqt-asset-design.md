# VEQT Asset (Proxy-Backtested Equity ETF) — Design

**Date:** 2026-06-07
**Status:** Draft for review

## Goal

Add **VEQT** (Vanguard All-Equity ETF Portfolio, TSX, CAD) to Kairos as a third asset chip, with a **conservative lump-sum entry-timing signal** — "is now an above-average time to add?" — rather than an aggressive buy↔sell trader. Because VEQT has only ~7 years of history (first trade 2019-02-05), its weights/thresholds are **derived on a long-history proxy index (S&P 500, ^GSPC, 1927→)** and applied to VEQT's own live price.

This is the framework's deliberately-deferred **non-crypto asset** path: it needs a new data source, a new signal set, and a new proxy-backtest mechanism. It is *not* config-only.

## Decisions (from brainstorming)

- **Asset:** VEQT only (100% equity → cleanest entry signal).
- **Intent:** Conservative entry-timing tilt; sell side muted.
- **Weights:** Proxy backtest on S&P 500 (^GSPC), applied live to VEQT.
- **Signals:** 4 — Drawdown-from-ATH, Mayer Multiple, Monthly RSI, VIX fear.
- **Data:** Yahoo Finance v8 chart API (keyless, requires User-Agent).

## Data layer

A new keyless **Yahoo v8 fetcher** module (`assets/yahoo.py`). Endpoint pattern:
`https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>?range=max&interval=1d` with a browser `User-Agent` header (verified: VEQT.TO, ^GSPC, ^VIX all return JSON; without a UA, requests are rate-limited). Helper parses `chart.result[0].timestamp` + `indicators.quote[0].close` into a `date`/`price` DataFrame.

Two compositions, both merging the **VIX** series on `date`:
- **Live fetch** (`veqt.fetch`): `VEQT.TO` close (CAD, 2019→) + `^VIX` → columns `date, price, vix`.
- **Proxy fetch** (`veqt.proxy_fetch`): `^GSPC` close (1927→) + `^VIX` (1990→) → columns `date, price, vix`. (Pre-1990 rows have NaN vix; the VIX signal yields neutral there, which is fine — the other three signals still train on the full range.)

**Risk:** Yahoo is unofficial and rate-limits; the fetcher must send a UA and retry with backoff. Less stable than the crypto sources (documented risk, not a blocker).

## Signal set

All four fit the existing pipeline. Three are price-only and need **no window changes** (the crypto-calibrated windows that assume 7-day data don't bite here because these use day-count or cadence-independent windows that are already correct for ~252-trading-day-per-year equity data):

| Signal | Compute | Direction | Notes |
|---|---|---|---|
| **Drawdown-from-ATH** | **new** `compute_drawdown_from_ath` | low = buy | `price / price.expanding().max()` → 1.0 at ATH, 0.70 = 30% below. Deep drawdown (low ratio) = buy. Cadence-independent. Primary entry signal. |
| **Mayer Multiple** | reuse `compute_mayer_multiple` | low = buy | `price / 200-day MA`. 200 *trading* days = the standard equity 200-day MA; existing `rolling(200)` is already correct. |
| **Monthly RSI** | reuse `compute_monthly_rsi` | low = buy | Monthly resample is cadence-independent. Oversold = buy. |
| **VIX fear** | **new** `compute_vix` | **high = buy** (inverted) | Pass-through of the `vix` column. High volatility/panic = good entry. |

### Inverted-signal support (for VIX)

The pipeline currently assumes "lower raw = more buy-favorable" everywhere. VIX is the opposite. To support it cleanly (and reusably for any future momentum-style signal) **without ugly negative raw values in the UI**, add an `invert: bool = False` field to `SignalSpec`:

- `compute_signals.signal_score`: when `invert`, swap the comparisons — `value >= invest_thresh → 100` (buy), `value <= avoid_thresh → 0` (avoid).
- `compute_signals.sell_signal_score`: when `invert`, sell when `value < sell_thresh` (low VIX = complacency).
- Per-signal gauge in `templates/dashboard.html.j2` (AVOID/WAIT/INVEST zones): render INVEST on the high side when `invert` is set, so the gauge reads correctly. The displayed raw stays the natural VIX number (e.g. "28").
- `score.py` `_signal_meta` carries `invert` through to `{id}_score.json` so the template knows.

VEQT VIX thresholds (illustrative, finalized by calibration): `invest_thresh≈28` (VIX ≥ 28 = fear = buy), `avoid_thresh≈15` (VIX ≤ 15 = complacent), `sell_thresh≈12`.

The crypto-only signals (MVRV, Puell, Pi Cycle, crypto Fear&Greed, ETH/BTC) are **dropped** for VEQT — they have no equity analog in this fetch.

## good_entry / good_exit (equity-calibrated, run on the proxy)

ETH's drawdown-from-ATH `good_entry` is the template, recalibrated to equity magnitudes and **trading-day** windows:

```
good_entry: price ≥ DRAWDOWN below trailing ATH  AND  forward HOLDING_DAYS return ≥ MIN_RETURN
```
Starting calibration targets (tuned by the backtest run, not hand-final): `DRAWDOWN ≈ 0.12–0.18`, `HOLDING_DAYS ≈ 504` (~2 trading years), `MIN_RETURN ≈ 0.20`. These produce a meaningful number of events on ^GSPC (1927→ spans ~10+ major drawdowns), unlike VEQT's two.

**good_exit muted:** entry-tilt rarely sells. Set a conservative "stretched" exit (e.g. price far above 200-day trend / very low VIX) with high thresholds, or a minimal exit so `sell_composite` stays low and the spectrum rarely drops below HOLD.

## Framework extension: proxy backtesting

The one genuinely new piece of machinery. Add to `AssetConfig`:

```python
proxy_fetch: Optional[Callable[[], pd.DataFrame]] = None
```

- **`scripts/backtest.py`:** when `cfg.proxy_fetch` is set, build the price/signal DataFrame from `proxy_fetch()` (S&P 500 + VIX) instead of the live `{id}_history.csv`, run `good_entry`/`good_exit` and per-signal precision/recall on it, and derive `{id}_weights.json` (+ `{id}_sell_weights.json`) from the proxy. Threshold calibration (à la `scripts/calibrate_eth_thresholds.py`, `anchored_threshold`) also runs on the proxy to set each signal's invest/avoid thresholds to a target invest rate. Optionally cache the proxy series to `data/{id}_proxy_history.csv` for reproducibility.
- **Daily pipeline unchanged:** `fetch_data` → `compute_signals` → `score` → `build_dashboard` all run on the **live** VEQT fetch. The proxy is needed only at backtest time (the manual `backtest.yml` workflow), so the daily cron stays simple and crypto-identical.
- **`scripts/validate_composite.py`:** for VEQT, validate on the proxy series (where the drawdown events exist). Emit `data/veqt_validation.json` with a noted caveat that VEQT's own out-of-sample window is short (~7 yrs).

This keeps weights held to the same evidentiary bar as the crypto assets, while signals are computed and displayed on VEQT's actual price (the ratios — drawdown, Mayer, RSI, VIX level — are scale-free and transfer from proxy to ETF).

## Config & UI

New `assets/veqt.py`:
```python
CONFIG = AssetConfig(
    id="veqt", display_name="VEQT", short_label="VEQT",
    accent_color="#c0392b", price_unit="C$",
    fetch=fetch, proxy_fetch=proxy_fetch,
    good_entry=good_entry, good_exit=good_exit,
    signals=[ drawdown_from_ath, mayer_multiple, monthly_rsi, vix ],  # SignalSpecs
    weight_overrides=None,
    strong_buy_cutoff=<calibrated, default 85>,
)
```
Appended to `assets/registry.py` `ASSETS` (third entry → third chip). No template structural changes beyond the inverted-gauge handling above; the asset renders client-side from embedded JSON like BTC/ETH. `strong_buy_cutoff` calibrated to keep STRONG BUY rare (consistent with the recent recalibration), computed during the backtest.

## Testing

- `tests/test_yahoo.py` — fetcher parses a recorded Yahoo JSON fixture into `date/price` (+ vix merge); handles missing/NaN closes.
- `tests/test_signals.py` — `compute_drawdown_from_ath` (ATH→1.0, post-drawdown < 1) and `compute_vix` pass-through on a synthetic frame.
- `tests/test_compute_signals.py` — `signal_score`/`sell_signal_score` with `invert=True` (high value → buy; low value → avoid/sell).
- `tests/test_framework.py` — VEQT registry/config: 4 signals, `proxy_fetch` set, `price_unit="C$"`, `invert` on the VIX spec; data-independent scoring-parity test for VEQT (pin logic with a fixture, refresh-safe).
- `tests/test_veqt.py` — `good_entry` on a synthetic equity series (drawdown + forward recovery → True; shallow dip → False); proxy-vs-live separation (compute runs on whichever frame is passed).
- Full suite green.

## Risks / open items (documented)

- **Yahoo stability** — unofficial API; mitigate with UA + retry/backoff; accept lower reliability than crypto sources.
- **US proxy vs global VEQT** — S&P 500 ≠ VEQT's global mix, but equity drawdowns are globally correlated and VEQT is ~45% US; an acknowledged approximation.
- **Proxy→live transfer** — weights/thresholds trained on ^GSPC applied to VEQT; relies on scale-free ratios transferring. Reasonable, not guaranteed.
- **VIX pre-1990** — proxy rows before 1990 have no VIX; that signal is neutral there while the other three train on the full span.
- **Philosophical** — timing overlay on a buy-and-hold product; the conservative entry-tilt framing (muted sell) keeps it honest.

## Out of scope (v1)

- VGRO and the "Both" option (the equity machinery makes a follow-up easy).
- A truly global long-history proxy (ACWI/VT are too short; revisit if a long global series becomes keyless).
- CAD/USD FX normalization (VEQT shown in its native CAD).
