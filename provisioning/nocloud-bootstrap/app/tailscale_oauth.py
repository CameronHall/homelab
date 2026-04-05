from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from shared.util import utc_now

from .config import Settings
from .schemas import AuthKeyResult

SAFE_DESCRIPTION_RE = re.compile(r"[^A-Za-z0-9_-]")


class TailscaleOAuthError(RuntimeError):
    pass


class TailscaleOAuthClient:
    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._http_client = http_client or httpx.Client(timeout=settings.http_timeout_seconds)

    def create_bootstrap_auth_key(self, node_id: str, expiry_minutes: int) -> AuthKeyResult:
        access_token = self._fetch_access_token()
        payload = {
            "capabilities": {
                "devices": {
                    "create": {
                        "reusable": False,
                        "ephemeral": False,
                        "preauthorized": False,
                        "tags": [self.settings.bootstrap_tag],
                    }
                }
            },
            "expirySeconds": max(expiry_minutes * 60, 60),
            "description": self._build_description(node_id),
        }
        tailnet = quote(self.settings.tailnet_name, safe="")
        response = self._http_client.post(
            f"{self.settings.tailscale_api_base_url}/tailnet/{tailnet}/keys?all=true",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )
        self._raise_for_status(response, "failed to create bootstrap auth key")
        body = response.json()
        key = body.get("key")
        if not key:
            raise TailscaleOAuthError("tailscale response did not include a one-time auth key")

        expires_at = self._parse_datetime(body.get("expires")) or (utc_now() + timedelta(minutes=expiry_minutes))
        return AuthKeyResult(
            key=key,
            key_id=body.get("id"),
            created_at=self._parse_datetime(body.get("created")),
            expires_at=expires_at,
            tags=[self.settings.bootstrap_tag],
        )

    def _fetch_access_token(self) -> str:
        response = self._http_client.post(
            self.settings.ts_oauth_token_url,
            data={
                "client_id": self.settings.ts_api_client_id,
                "client_secret": self.settings.ts_api_client_secret,
            },
        )
        self._raise_for_status(response, "failed to exchange tailscale OAuth credentials")
        body = response.json()
        access_token = body.get("access_token")
        if not access_token:
            raise TailscaleOAuthError("tailscale OAuth token exchange returned no access token")
        return access_token

    @staticmethod
    def _parse_datetime(value: Any) -> Any:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    @staticmethod
    def _build_description(node_id: str) -> str:
        safe_node_id = SAFE_DESCRIPTION_RE.sub("-", node_id)[:40].strip("-") or "bootstrap"
        return f"bootstrap-{safe_node_id}"[:50]

    @staticmethod
    def _raise_for_status(response: httpx.Response, message: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TailscaleOAuthError(message) from exc
