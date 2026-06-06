"""Typed config interface every asset must satisfy."""
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd


@dataclass
class SignalSpec:
    """Binds a shared signal compute-function to one asset's thresholds + display meta."""
    key: str
    display_name: str
    compute: Callable[[pd.DataFrame], pd.Series]
    invest_thresh: float
    avoid_thresh: float
    sell_thresh: float        # raw value ABOVE which signal says "sell" (score = 100)
    range_lo: float
    range_hi: float
    fmt: str


@dataclass
class AssetConfig:
    id: str
    display_name: str
    short_label: str
    accent_color: str
    price_unit: str
    fetch: Callable[[], pd.DataFrame]
    signals: list[SignalSpec]
    good_entry: Callable[[pd.DataFrame], pd.Series]
    good_exit: Callable[[pd.DataFrame], pd.Series]   # symmetric with good_entry
    weight_overrides: Optional[dict[str, float]] = None
    sell_weight_overrides: Optional[dict[str, float]] = None
