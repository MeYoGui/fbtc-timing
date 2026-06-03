"""One-time VAPID keypair generation for Web Push.

Run once:  python scripts/gen_vapid.py

Prints the application server key (paste into docs/enable-alerts.html) and the
private key PEM (store as the VAPID_PRIVATE_KEY GitHub secret).

GENERATE ONCE, NEVER ROTATE: regenerating invalidates every existing
subscription (push services reject a VAPID key that doesn't match the one used
at subscribe time).
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate() -> tuple[str, str]:
    """Return (application_server_key_base64url, private_key_pem)."""
    key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_point = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    app_server_key = base64.urlsafe_b64encode(pub_point).rstrip(b"=").decode()
    return app_server_key, priv_pem


def main() -> None:
    app_key, priv_pem = generate()
    print("\n=== applicationServerKey (paste into docs/enable-alerts.html) ===\n")
    print(app_key)
    print("\n=== VAPID_PRIVATE_KEY (store as a GitHub Actions secret, full PEM) ===\n")
    print(priv_pem)
    print("Also set VAPID_SUBJECT to a mailto: address, e.g. mailto:you@example.com")


if __name__ == "__main__":
    main()
