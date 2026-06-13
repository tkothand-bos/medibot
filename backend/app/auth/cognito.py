"""AWS Cognito authentication for MediBot.

- /login uses Cognito's USER_PASSWORD_AUTH flow (boto3) and returns the
  Cognito-issued tokens. The user's role is their Cognito *group*
  (one group per role: doctor, nurse, billing_executive, technician, admin).
- Protected endpoints verify the access token's signature against the user
  pool's JWKS, check issuer/client/expiry, and extract the role from the
  `cognito:groups` claim. The role therefore comes from the verified token,
  never from anything the client self-reports.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache

import boto3
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwk, jwt
from jose.utils import base64url_decode

from app.config import get_settings
from app.rbac import ROLE_COLLECTIONS

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=True)

VALID_ROLES = set(ROLE_COLLECTIONS)


@lru_cache(maxsize=1)
def _jwks() -> dict:
    settings = get_settings()
    url = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )
    return requests.get(url, timeout=10).json()


def _issuer() -> str:
    settings = get_settings()
    return (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}"
    )


def login(username: str, password: str) -> dict:
    """Authenticate against Cognito; return tokens + role."""
    settings = get_settings()
    client = boto3.client("cognito-idp", region_name=settings.cognito_region)
    try:
        resp = client.initiate_auth(
            ClientId=settings.cognito_app_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
    except client.exceptions.NotAuthorizedException:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    except client.exceptions.UserNotFoundException:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    tokens = resp["AuthenticationResult"]
    claims = verify_token(tokens["AccessToken"])
    return {
        "access_token": tokens["AccessToken"],
        "id_token": tokens.get("IdToken"),
        "expires_in": tokens.get("ExpiresIn"),
        "token_type": "Bearer",
        "username": claims["username"],
        "role": claims["role"],
    }


def verify_token(token: str) -> dict:
    """Verify a Cognito access token; return {'username', 'role'}.

    Verifies: signature (against JWKS), expiry, issuer, client id, token_use.
    Role is read from the `cognito:groups` claim of the VERIFIED token.
    """
    settings = get_settings()
    try:
        headers = jwt.get_unverified_headers(token)
        kid = headers["kid"]
        key_data = next(k for k in _jwks()["keys"] if k["kid"] == kid)
        public_key = jwk.construct(key_data)

        message, encoded_sig = token.rsplit(".", 1)
        if not public_key.verify(message.encode(), base64url_decode(encoded_sig.encode())):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token signature")

        claims = jwt.get_unverified_claims(token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")

    if claims.get("exp", 0) < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    if claims.get("iss") != _issuer():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token issuer")
    if claims.get("token_use") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")
    if claims.get("client_id") != settings.cognito_app_client_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token not issued for this app")

    groups = claims.get("cognito:groups", [])
    roles = [g for g in groups if g in VALID_ROLES]
    if not roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no MediBot role assigned")

    return {"username": claims.get("username", "unknown"), "role": roles[0]}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """FastAPI dependency: verified user identity + role from the token."""
    return verify_token(credentials.credentials)
