import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from assets import eth


def test_good_entry_flags_deep_drawdown_with_strong_recovery():
    # 51 days at ATH=100, then a 60%-drawdown day (40 <= 45 threshold),
    # then a 548-day ramp up to 200 so the 18-month forward return is huge.
    prices = [100.0] * 51 + [40.0] + list(np.linspace(41.0, 200.0, 548))
    df = pd.DataFrame({"price": prices})
    assert len(df) == 600

    good = eth.good_entry(df)

    assert bool(good.iloc[51]) is True          # the drawdown day qualifies
    assert int(good.sum()) == 1                  # nothing else does
    assert good.dtype == bool


def test_good_entry_rejects_shallow_drawdown():
    # Price only 20% below ATH (80 > 45 threshold) -> never a good entry.
    prices = [100.0] * 51 + [80.0] + list(np.linspace(81.0, 300.0, 548))
    df = pd.DataFrame({"price": prices})
    good = eth.good_entry(df)
    assert int(good.sum()) == 0
