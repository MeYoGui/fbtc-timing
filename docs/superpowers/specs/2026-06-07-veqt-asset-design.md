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
- **Signals:** a **7-candidate pool**, pruned by the proxy backtest to those that earn weight. Contrarian/value: Drawdown-from-ATH, Mayer Multiple, Monthly RSI, VIX fear; valuation: Shiller CAPE; trend/stress (counterbalancing, `invert`): 12-month momentum, VIX term structure.
- **Data:** Yahoo Finance v8 chart API (keyless, UA) for prices + VIX + VIX3M; Shiller/multpl (keyless) for CAPE.

## Data layer

A new keyless **Yahoo v8 fetcher** module (`assets/yahoo.py`). Endpoint pattern:
`https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>?range=max&interval=1d` with a browser `User-Agent` header (verified: VEQT.TO, ^GSPC, ^VIX all return JSON; without a UA, requests are rate-limited). Helper parses `chart.result[0].timestamp` + `indicators.quote[0].close` into a `date`/`price` DataFrame.

Two compositions, both merging the auxiliary series on `date` (forward-filled where a series is monthly/sparser): `vix` (^VIX, 1990→), `vix3m` (^VIX3M, 2006→), and `cape` (Shiller PE10, monthly, 1871→ via a keyless multpl scrape / Shiller dataset).
- **Live fetch** (`veqt.fetch`): `VEQT.TO` close (CAD, 2019→) + vix + vix3m + cape → `date, price, vix, vix3m, cape`.
- **Proxy fetch** (`veqt.proxy_fetch`): `^GSPC` close (1927→) + vix + vix3m + cape → same columns. Auxiliary series that don't reach back to 1927 (vix→1990, vix3m→2006) are NaN early; the dependent signals yield **neutral** on NaN rows, so the price-only signals still train on the full 1927→ span.

**Risk:** Yahoo is unofficial and rate-limits; the fetcher must send a UA and retry with backoff. Less stable than the crypto sources (documented risk, not a blocker).

## Signal set — 7-candidate pool, pruned by the backtest

We do **not** pre-commit to a fixed set. Because the proxy backtest runs on 1927→ S&P 500, we compute all seven candidates on the proxy, derive per-signal precision/recall + weights, and **keep only those that earn meaningful weight** for the live VEQT config. This lets the long history prune redundant/weak signals empirically. The price-only signals need **no window changes** (their windows are day-count or cadence-independent, already correct for ~252-trading-day equity years).

| Signal | Compute | Direction | Notes |
|---|---|---|---|
| **Drawdown-from-ATH** | **new** `compute_drawdown_from_ath` | low = buy | `price / price.expanding().max()` → 1.0 at ATH, 0.70 = 30% below. Deep drawdown = buy. Cadence-independent. Primary entry signal. |
| **Mayer Multiple** | reuse `compute_mayer_multiple` | low = buy | `price / 200-day MA`. 200 *trading* days = standard equity 200-day MA; existing `rolling(200)` already correct. |
| **Monthly RSI** | reuse `compute_monthly_rsi` | low = buy | Monthly resample is cadence-independent. Oversold = buy. |
| **VIX fear** | **new** `compute_vix` | **high = buy** (`invert`) | Pass-through of `vix`. High volatility/panic = good entry. |
| **Shiller CAPE** | **new** `compute_cape` | low = buy | Pass-through of `cape` (ffilled monthly). Cheap valuation = buy. *Caveat:* US-only, structurally elevated for a decade → may rarely fire buy; the backtest decides if it earns weight. |
| **12-month momentum** | **new** `compute_momentum_12m` | **high = buy** (`invert`) | `price / price.shift(252)`. Trend-following filter that **counterbalances** the contrarian dip-buyers — "buy the dip, but only once the long trend hasn't broken / is turning up." |
| **VIX term structure** | **new** `compute_vix_term` | **high = buy** (`invert`) | `vix / vix3m`; > 1 (backwardation) = acute panic = buy. *Caveat:* vix3m only from 2006, so this is trainable on ~3 stress events; likely low/no weight — included because requested. |

### Inverted-signal support (VIX fear, 12-month momentum, VIX term structure)

The pipeline currently assumes "lower raw = more buy-favorable" everywhere. Three of the candidates are the opposite (high = buy). To support them cleanly **without ugly negative raw values in the UI**, add an `invert: bool = False` field to `SignalSpec` (now justified by three real consumers, and reusable for any future momentum-style signal):

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
    signals=[ ... ],  # the SignalSpecs that earned weight in the proxy backtest (pruned from the 7-candidate pool)
    weight_overrides=None,
    strong_buy_cutoff=<calibrated, default 85>,
)
```
Appended to `assets/registry.py` `ASSETS` (third entry → third chip). No template structural changes beyond the inverted-gauge handling above; the asset renders client-side from embedded JSON like BTC/ETH. `strong_buy_cutoff` calibrated to keep STRONG BUY rare (consistent with the recent recalibration), computed during the backtest.

## Testing

- `tests/test_yahoo.py` — fetcher parses a recorded Yahoo JSON fixture into `date/price` (+ vix merge); handles missing/NaN closes.
- `tests/test_signals.py` — new computes on synthetic frames: `compute_drawdown_from_ath` (ATH→1.0, post-drawdown < 1), `compute_vix`/`compute_cape` pass-through, `compute_momentum_12m` (`price/price.shift(252)`), `compute_vix_term` (`vix/vix3m`); NaN-input → neutral handling for the sparse/late-start series.
- `tests/test_compute_signals.py` — `signal_score`/`sell_signal_score` with `invert=True` (high value → buy; low value → avoid/sell).
- `tests/test_framework.py` — VEQT registry/config: the pruned signal set is non-empty, `proxy_fetch` set, `price_unit="C$"`, `invert=True` on each high-is-buy spec (VIX / momentum / VIX-term, whichever survive pruning); data-independent scoring-parity test for VEQT (pin logic with a fixture, refresh-safe).
- `tests/test_veqt.py` — `good_entry` on a synthetic equity series (drawdown + forward recovery → True; shallow dip → False); proxy-vs-live separation (compute runs on whichever frame is passed).
- Full suite green.

## Risks / open items (documented)

- **Data-source stability** — Yahoo (prices/VIX/VIX3M) is unofficial → UA + retry/backoff; the CAPE scrape (multpl/Shiller) is a second fragile keyless dependency. Both less reliable than the crypto sources. Each aux series must fail soft (NaN → neutral), never break the daily run.
- **US proxy vs global VEQT** — S&P 500 ≠ VEQT's global mix, but equity drawdowns are globally correlated and VEQT is ~45% US; an acknowledged approximation. CAPE/VIX are likewise US gauges applied to a global ETF.
- **Proxy→live transfer** — weights/thresholds trained on ^GSPC applied to VEQT; relies on scale-free ratios transferring. Reasonable, not guaranteed.
- **Short aux histories** — VIX→1990, VIX3M→2006: the VIX-term signal trains on only ~3 stress events and may not earn weight (kept because requested). Early proxy rows are neutral for these.
- **CAPE regime drift** — structurally elevated for a decade; may behave as a near-permanent "avoid." The backtest decides its weight rather than assuming it helps.
- **Philosophical** — timing overlay on a buy-and-hold product; the conservative entry-tilt framing (muted sell) keeps it honest.

## Out of scope (v1)

- VGRO and the "Both" option (the equity machinery makes a follow-up easy).
- A truly global long-history proxy (ACWI/VT are too short; revisit if a long global series becomes keyless).
- CAD/USD FX normalization (VEQT shown in its native CAD).
