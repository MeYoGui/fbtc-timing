import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_monthly_rsi_cadence_is_monthly_others_daily():
    from assets.bitcoin import CONFIG as BTC
    from assets.eth import CONFIG as ETH
    for cfg in (BTC, ETH):
        rsi = next(s for s in cfg.signals if s.key == "monthly_rsi")
        assert rsi.cadence == "monthly"
        others = [s for s in cfg.signals if s.key != "monthly_rsi"]
        assert all(s.cadence == "daily" for s in others), cfg.id
