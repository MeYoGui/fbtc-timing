"""Typed config interface every asset must satisfy."""
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd


@dataclass
class SignalSpec:
    """Binds a shared signal compute-function to one asset's thresholds + display meta.

    Scoring direction is encoded by the ordering of invest_thresh vs avoid_thresh
    (all current signals are "lower raw value = more invest").
    """
    key: str                                   # "mvrv_zscore" — column + JSON key
    display_name: str                          # "MVRV Z-Score"
    compute: Callable[[pd.DataFrame], pd.Series]  # raw-value series from assets.signals
    invest_thresh: float
    avoid_thresh: float
    range_lo: float
    range_hi: float
    fmt: str                                   # "{:.1f}" — display format for bar labels


@dataclass
class AssetConfig:
    id: str                # "bitcoin" — used in filenames, JSON keys, DOM ids
    display_name: str      # "Bitcoin"
    short_label: str       # "₿ Bitcoin" (chip label)
    accent_color: str      # "#f7931a"
    price_unit: str        # "$" — header price prefix
    fetch: Callable[[], pd.DataFrame]               # returns history DataFrame (has "date")
    signals: list                                   # list[SignalSpec], ordered for display
    good_entry: Callable[[pd.DataFrame], pd.Series]  # backtest target (bool Series)
    weight_overrides: Optional[dict] = None          # e.g. {"mvrv_zscore": 2.0} precision multiplier
