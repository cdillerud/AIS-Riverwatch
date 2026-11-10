"""Google ID-token verification and password hashing (offline)."""
import hashlib

import pytest
from fastapi.testclient import TestClient

import server
from services.google_auth import GoogleAuthError, verify_google_credential

CLIENT_ID = "123-abc.apps.googleusercontent.com"


def _claims(**overrides):
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1098765",
        "email": "Skipper@Example.com",
        "email_verified": True,
        "name": "Skipper",
        "picture": "https://example.com/p.png",
    }
    claims.update(overrides)
    return claims


def _verifier(claims=None, error=None):
    def verify(token, client_id):
        assert client_id == CLIENT_ID
        if error:
            raise error
        return claims
    return verify


def test_valid_token_returns_normalized_identity():
    out = verify_google_credential("jwt", CLIENT_ID, verifier=_verifier(_claims()))
    assert out == {"sub": "1098765", "email": "skipper@example.com",
                   "name": "Skipper", "picture": "https://example.com/p.png"}


@pytest.mark.parametrize("claims", [
    _claims(email_verified=False),
    _claims(email_verified=None),
    _claims(email=""),
    _claims(aud="someone-elses-app"),
    _claims(iss="https://evil.example.com"),
    _claims(sub=""),
])
def test_untrustworthy_tokens_are_rejected(claims):
    with pytest.raises(GoogleAuthError):
        verify_google_credential("jwt", CLIENT_ID, verifier=_verifier(claims))


def test_bad_signature_or_expiry_is_rejected():
    with pytest.raises(GoogleAuthError):
        verify_google_credential("jwt", CLIENT_ID, verifier=_verifier(error=ValueError("Token expired")))
    with pytest.raises(GoogleAuthError):
        verify_google_credential("", CLIENT_ID, verifier=_verifier(_claims()))


client = TestClient(server.app)  # no context manager: startup (DB) hooks not run


def test_google_endpoint_off_without_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert client.get("/api/auth/config").json() == {"google_client_id": None}
    assert client.post("/api/auth/google", json={"credential": "x"}).status_code == 503


def test_google_endpoint_rejects_invalid_credential(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    assert client.get("/api/auth/config").json() == {"google_client_id": CLIENT_ID}
    assert client.post("/api/auth/google", json={}).status_code == 400
    # A garbage JWT fails signature parsing before any network call.
    assert client.post("/api/auth/google", json={"credential": "not-a-jwt"}).status_code == 401


def test_emergent_session_exchange_is_gone():
    assert client.post("/api/auth/google/session", json={"session_id": "x"}).status_code in (404, 405)


def test_password_hash_roundtrip_and_legacy_upgrade():
    h = server.hash_password("correct horse")
    assert h.startswith("pbkdf2_sha256$")
    assert server.verify_password("correct horse", h)
    assert not server.verify_password("wrong", h)
    assert not server.password_needs_rehash(h)

    salt = "abcd"
    legacy = f"{salt}${hashlib.sha256((salt + 'old pw').encode()).hexdigest()}"
    assert server.verify_password("old pw", legacy)
    assert not server.verify_password("nope", legacy)
    assert server.password_needs_rehash(legacy)

    for junk in ("", "x", None, "a$b$c"):
        assert not server.verify_password("pw", junk)
