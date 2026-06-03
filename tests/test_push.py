import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import gen_vapid


def test_generate_returns_appkey_and_pem():
    app_key, priv_pem = gen_vapid.generate()
    # application server key: base64url, no padding, ~87-88 chars (65-byte point)
    assert isinstance(app_key, str)
    assert "=" not in app_key and "+" not in app_key and "/" not in app_key
    assert 80 <= len(app_key) <= 90
    # private key: unencrypted PKCS8 PEM
    assert priv_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert priv_pem.strip().endswith("-----END PRIVATE KEY-----")
