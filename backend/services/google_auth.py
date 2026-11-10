"""
Google Sign-In without a third-party auth broker.

The browser uses Google Identity Services to obtain an ID token (a JWT signed
by Google) and posts it to /api/auth/google. We verify the signature, audience
(our OAuth client ID), issuer and expiry here, and only trust the email when
Google says it is verified.

Configure with GOOGLE_CLIENT_ID (a "Web application" OAuth client in Google
Cloud Console, with the site's origin under "Authorized JavaScript origins").
When it is unset, Google sign-in is simply off and email/password still works.
"""
import os
from typing import Optional

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    pass


def google_client_id() -> Optional[str]:
    value = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    return value or None


def _verify_with_google(credential: str, client_id: str) -> dict:
    # Imported lazily so the backend still starts if google-auth is missing
    # and Google sign-in is not configured.
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)


def verify_google_credential(credential: str, client_id: str, verifier=_verify_with_google) -> dict:
    """Return {sub, email, name, picture} for a valid Google ID token, else raise GoogleAuthError."""
    if not credential or not isinstance(credential, str):
        raise GoogleAuthError("Missing Google credential")
    try:
        claims = verifier(credential, client_id)
    except ValueError as e:  # bad signature, wrong audience, expired, malformed
        raise GoogleAuthError(f"Invalid Google credential: {e}") from e

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleAuthError("Invalid Google credential issuer")
    if claims.get("aud") != client_id:
        raise GoogleAuthError("Google credential was issued for a different app")
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise GoogleAuthError("Google account has no email address")
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("Google has not verified this email address")
    if not claims.get("sub"):
        raise GoogleAuthError("Google credential has no subject")

    return {
        "sub": str(claims["sub"]),
        "email": email,
        "name": claims.get("name") or "",
        "picture": claims.get("picture"),
    }
