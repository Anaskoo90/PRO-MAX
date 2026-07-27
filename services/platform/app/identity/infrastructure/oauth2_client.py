"""
OAuth2 / OpenID Connect client — a generic Authorization Code flow client
configured per external provider (config values, e.g. actual Discord OAuth2
client id/secret, are still unconfigured — this is the mechanism, not a
specific provider integration). Supports plain OAuth2 userinfo endpoints as
well as providers that return a signed OIDC id_token.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.platform_core.shared_kernel.constants import TIMEOUT_EXTERNAL_SECONDS


@dataclass(frozen=True, slots=True)
class OAuth2ProviderConfig:
    provider_key: str  # e.g. "discord"
    client_id: str
    client_secret: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None  # None if identity comes only from the id_token
    redirect_uri: str
    scopes: tuple[str, ...]
    jwks_uri: str | None = None  # required only if verifying an id_token


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    provider_key: str
    subject: str  # provider's stable user id
    email: str | None
    display_name: str | None


class OAuth2ExchangeError(Exception):
    pass


class OAuth2Client:
    def __init__(self, config: OAuth2ProviderConfig) -> None:
        self._config = config

    def build_authorization_url(self) -> tuple[str, str]:
        """Returns (authorization_url, state). Caller persists `state`
        (e.g. in a short-lived signed cookie) and verifies it on callback
        to prevent CSRF on the OAuth2 flow."""
        state = secrets.token_urlsafe(32)
        params = httpx.QueryParams(
            {
                "response_type": "code",
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "scope": " ".join(self._config.scopes),
                "state": state,
            }
        )
        return f"{self._config.authorization_endpoint}?{params}", state

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=TIMEOUT_EXTERNAL_SECONDS) as client:
            response = await client.post(
                self._config.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._config.redirect_uri,
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                },
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            raise OAuth2ExchangeError(f"Token exchange failed: {response.status_code} {response.text}")
        return response.json()

    async def fetch_external_identity(self, token_response: dict[str, Any]) -> ExternalIdentity:
        access_token = token_response.get("access_token")
        if self._config.userinfo_endpoint and access_token:
            async with httpx.AsyncClient(timeout=TIMEOUT_EXTERNAL_SECONDS) as client:
                response = await client.get(
                    self._config.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            response.raise_for_status()
            payload = response.json()
            return ExternalIdentity(
                provider_key=self._config.provider_key,
                subject=str(payload.get("sub") or payload.get("id")),
                email=payload.get("email"),
                display_name=payload.get("name") or payload.get("username"),
            )

        id_token = token_response.get("id_token")
        if id_token:
            claims = self._verify_id_token(id_token)
            return ExternalIdentity(
                provider_key=self._config.provider_key,
                subject=claims["sub"],
                email=claims.get("email"),
                display_name=claims.get("name"),
            )

        raise OAuth2ExchangeError("Provider returned neither a userinfo endpoint result nor an id_token")

    def _verify_id_token(self, id_token: str) -> dict[str, Any]:
        if not self._config.jwks_uri:
            raise OAuth2ExchangeError(
                f"Provider '{self._config.provider_key}' returned an id_token but has no "
                "jwks_uri configured — refusing to decode it without signature verification"
            )
        jwk_client = jwt.PyJWKClient(self._config.jwks_uri)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        return jwt.decode(
            id_token,
            key=signing_key.key,
            algorithms=["RS256"],
            audience=self._config.client_id,
        )
