from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import httpx

from shared.util import utc_now

from .config import Settings, get_settings


class TailscaleControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class TailnetDevice:
    device_id: str
    name: str | None
    hostname: str | None
    addresses: list[str]
    tags: list[str]
    authorized: bool | None
    created: datetime | None


class TailscaleControlClient:
    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._http_client = http_client or httpx.Client(timeout=settings.tailscale_http_timeout_seconds)

    def list_devices(self) -> list[TailnetDevice]:
        access_token = self._fetch_access_token()
        tailnet = quote(self.settings.tailnet_name, safe="")
        response = self._http_client.get(
            f"{self.settings.tailscale_api_base_url}/tailnet/{tailnet}/devices",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self._raise_for_status(response, "failed to list tailnet devices")
        body = response.json()
        raw_devices = body.get("devices") or body.get("Devices") or body
        if not isinstance(raw_devices, list):
            raise TailscaleControlError("tailscale device list response had unexpected shape")
        return [self._parse_device(item) for item in raw_devices if isinstance(item, dict)]

    def find_device(self, *, hostname: str | None, node_name: str | None, tailnet_ip: str | None) -> TailnetDevice | None:
        normalized_hostname = self._normalize_name(hostname)
        normalized_node_name = self._normalize_name(node_name)
        for device in self.list_devices():
            device_names = {
                self._normalize_name(device.hostname),
                self._normalize_name(device.name),
            }
            if tailnet_ip and tailnet_ip in device.addresses:
                return device
            if normalized_node_name and normalized_node_name in device_names:
                return device
            if normalized_hostname and normalized_hostname in device_names:
                return device
        return None

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
            raise TailscaleControlError("tailscale OAuth token exchange returned no access token")
        return access_token

    def _parse_device(self, item: dict[str, Any]) -> TailnetDevice:
        name = item.get("name") or item.get("Name")
        hostname = item.get("hostname") or item.get("Hostname") or self._normalize_name(name)
        tags = [str(tag) for tag in (item.get("tags") or item.get("Tags") or [])]
        addresses = [str(address) for address in (item.get("addresses") or item.get("Addresses") or [])]
        authorized = item.get("authorized")
        if authorized is None:
            authorized = item.get("Authorized")
        return TailnetDevice(
            device_id=str(item.get("id") or item.get("ID") or item.get("nodeId") or item.get("NodeID") or ""),
            name=name,
            hostname=hostname,
            addresses=addresses,
            tags=tags,
            authorized=authorized if isinstance(authorized, bool) else None,
            created=self._parse_datetime(item.get("created") or item.get("Created") or item.get("createdAt")),
        )

    @staticmethod
    def _normalize_name(value: str | None) -> str | None:
        if not value:
            return None
        return value.rstrip(".").split(".", 1)[0]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    @staticmethod
    def _raise_for_status(response: httpx.Response, message: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TailscaleControlError(message) from exc


@lru_cache(maxsize=1)
def get_tailscale_control_client() -> TailscaleControlClient:
    return TailscaleControlClient(get_settings())
