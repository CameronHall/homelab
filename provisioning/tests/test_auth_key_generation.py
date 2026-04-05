from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx

from conftest import load_service_module


def test_create_bootstrap_auth_key_uses_oauth_client_credentials(monkeypatch):
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("TAILNET_NAME", "example-tailnet")
    monkeypatch.setenv("BOOTSTRAP_TAG", "tag:bootstrap")

    config_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "config", reload_package=True)
    oauth_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "tailscale_oauth")
    config_module.get_settings.cache_clear()
    settings = config_module.get_settings()

    observed = {"token_request": None, "key_request": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            observed["token_request"] = parse_qs(request.content.decode())
            return httpx.Response(200, json={"access_token": "access-123"})

        observed["key_request"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "key-1",
                "key": "tskey-auth-123",
                "created": "2026-04-02T00:00:00Z",
                "expires": "2026-04-02T00:10:00Z",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    auth_client = oauth_module.TailscaleOAuthClient(settings=settings, http_client=client)

    result = auth_client.create_bootstrap_auth_key(node_id="node-123", expiry_minutes=10)

    assert observed["token_request"] == {
        "client_id": ["client-id"],
        "client_secret": ["client-secret"],
    }
    assert observed["key_request"]["capabilities"]["devices"]["create"] == {
        "reusable": False,
        "ephemeral": False,
        "preauthorized": False,
        "tags": ["tag:bootstrap"],
    }
    assert observed["key_request"]["expirySeconds"] == 600
    assert result.key == "tskey-auth-123"
    assert result.created_at == datetime.fromisoformat("2026-04-02T00:00:00+00:00")
    assert result.expires_at == datetime.fromisoformat("2026-04-02T00:10:00+00:00")


def test_create_bootstrap_auth_key_falls_back_to_computed_expiry(monkeypatch):
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")

    config_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "config", reload_package=True)
    oauth_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "tailscale_oauth")
    config_module.get_settings.cache_clear()
    settings = config_module.get_settings()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"access_token": "access-123"})
        return httpx.Response(200, json={"key": "tskey-auth-456"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    auth_client = oauth_module.TailscaleOAuthClient(settings=settings, http_client=client)

    before = datetime.now(tz=timezone.utc)
    result = auth_client.create_bootstrap_auth_key(node_id="node-xyz", expiry_minutes=5)
    after = datetime.now(tz=timezone.utc) + timedelta(minutes=5, seconds=5)

    assert result.key == "tskey-auth-456"
    assert before <= result.expires_at <= after
