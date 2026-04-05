from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from email.header import decode_header
from functools import lru_cache
from typing import Any

import httpx

from .config import Settings, get_settings


@dataclass(frozen=True)
class BootstrapCallerIdentity:
    tailnet_ip: str | None
    node_name: str | None
    tags: list[str]
    capabilities: dict[str, list[dict[str, Any]]]
    auth_source: str


class TailscaleAuthorizationError(RuntimeError):
    pass


class TailscaleAuthHelper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decode_rfc2047_header(self, value: str) -> str:
        parts: list[str] = []
        for fragment, encoding in decode_header(value):
            if isinstance(fragment, bytes):
                parts.append(fragment.decode(encoding or "utf-8"))
            else:
                parts.append(fragment)
        return "".join(parts)

    def parse_app_capabilities(self, value: str) -> dict[str, list[dict[str, Any]]]:
        decoded = self.decode_rfc2047_header(value)
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise TailscaleAuthorizationError("invalid tailscale app capabilities header") from exc
        if not isinstance(parsed, dict):
            raise TailscaleAuthorizationError("invalid tailscale app capabilities header")
        capabilities: dict[str, list[dict[str, Any]]] = {}
        for key, entries in parsed.items():
            if isinstance(entries, list):
                capabilities[str(key)] = [entry for entry in entries if isinstance(entry, dict)]
        return capabilities

    def authorize_app_capabilities(self, capabilities: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        entries = capabilities.get(self.settings.bootstrap_capability, [])
        if not entries:
            raise TailscaleAuthorizationError("bootstrap capability not granted")
        if not any(entry.get("role") == self.settings.bootstrap_role for entry in entries):
            raise TailscaleAuthorizationError("bootstrap capability not granted")
        return capabilities

    def lookup_whois_identity(self, remote_addr: str) -> BootstrapCallerIdentity:
        payload = self._localapi_whois(remote_addr)
        if payload is None:
            payload = self._cli_whois(remote_addr)
        if payload is None:
            raise TailscaleAuthorizationError("unable to resolve caller via tailscale whois")
        return self._authorize_whois_payload(payload=payload, remote_addr=remote_addr)

    def _localapi_whois(self, remote_addr: str) -> dict[str, Any] | None:
        transport = httpx.HTTPTransport(uds=self.settings.ts_localapi_socket)
        try:
            with httpx.Client(
                transport=transport,
                timeout=self.settings.ts_localapi_timeout_seconds,
                base_url=self.settings.ts_localapi_base_url,
            ) as client:
                response = client.get("/localapi/v0/whois", params={"addr": remote_addr})
                response.raise_for_status()
                return response.json()
        except (FileNotFoundError, OSError, httpx.HTTPError):
            return None

    def _cli_whois(self, remote_addr: str) -> dict[str, Any] | None:
        try:
            completed = subprocess.run(
                [self.settings.tailscale_cli_path, "whois", "--json", remote_addr],
                capture_output=True,
                check=True,
                text=True,
                timeout=self.settings.ts_localapi_timeout_seconds,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None

    def _authorize_whois_payload(self, payload: dict[str, Any], remote_addr: str) -> BootstrapCallerIdentity:
        node = payload.get("Node") or {}
        tags = [str(tag) for tag in (node.get("Tags") or payload.get("Tags") or [])]
        capabilities = self._extract_capabilities(payload=payload, node=node)
        if self.settings.bootstrap_tag not in tags:
            raise TailscaleAuthorizationError("caller is missing bootstrap tag")
        if self.settings.bootstrap_capability not in capabilities:
            raise TailscaleAuthorizationError("bootstrap capability not granted")

        return BootstrapCallerIdentity(
            tailnet_ip=self._extract_tailnet_ip(payload=payload, node=node) or remote_addr,
            node_name=self.normalize_node_name(node.get("Name") or node.get("ComputedName") or payload.get("NodeName")),
            tags=tags,
            capabilities=capabilities,
            auth_source="direct_whois",
        )

    @staticmethod
    def _extract_capabilities(payload: dict[str, Any], node: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        raw = payload.get("CapMap") or payload.get("Capabilities") or node.get("CapMap") or node.get("Capabilities") or {}
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, list[dict[str, Any]]] = {}
        for key, entries in raw.items():
            if isinstance(entries, list):
                normalized[str(key)] = [entry for entry in entries if isinstance(entry, dict)]
            elif isinstance(entries, dict):
                normalized[str(key)] = [entries]
        return normalized

    @staticmethod
    def _extract_tailnet_ip(payload: dict[str, Any], node: dict[str, Any]) -> str | None:
        for candidate in (payload.get("TailnetIP"), node.get("TailnetIP")):
            if isinstance(candidate, str) and candidate:
                return candidate
        for candidate in (node.get("Addresses") or payload.get("Addresses") or []):
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    @staticmethod
    def normalize_node_name(name: str | None) -> str | None:
        if not name:
            return None
        return name.rstrip(".").split(".", 1)[0]


@lru_cache(maxsize=1)
def get_tailscale_auth_helper() -> TailscaleAuthHelper:
    return TailscaleAuthHelper(get_settings())
