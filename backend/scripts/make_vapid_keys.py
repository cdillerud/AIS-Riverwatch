"""Print a new VAPID key pair for Web Push alerts.

    python scripts/make_vapid_keys.py

Put the output in the server's environment (.env next to
docker-compose.prod.yml, or backend/.env) together with VAPID_SUBJECT, then
restart the backend. Keep the private key secret. Changing the keys later
invalidates every existing subscription: boaters have to turn alerts off and
on again on each phone.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_keys() -> tuple:
    """(public, private): uncompressed P-256 point and raw 32-byte private
    value, base64url without padding - the formats browsers and pywebpush use."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    return _b64url(public), _b64url(private)


if __name__ == "__main__":
    pub, priv = make_keys()
    print(f"VAPID_PUBLIC_KEY={pub}")
    print(f"VAPID_PRIVATE_KEY={priv}")
    print("VAPID_SUBJECT=mailto:you@example.com")
