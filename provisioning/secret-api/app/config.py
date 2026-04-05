from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "secret-api"
    bind_host: str = Field(default="127.0.0.1", alias="SECRET_API_BIND_HOST")
    bind_port: int = Field(default=8081, alias="SECRET_API_PORT")
    database_url: str = Field(default="sqlite:////data/provisioning.db", alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    tailscale_auth_mode: Literal["serve_http", "direct_whois"] = Field(
        default="serve_http",
        alias="TAILSCALE_AUTH_MODE",
    )
    tailscale_app_capabilities_header: str = Field(
        default="Tailscale-App-Capabilities",
        alias="TAILSCALE_APP_CAPABILITIES_HEADER",
    )
    bootstrap_capability: str = Field(default="homelab.local/cap/bootstrap", alias="BOOTSTRAP_CAPABILITY")
    bootstrap_role: str = Field(default="bootstrap-client", alias="BOOTSTRAP_CAPABILITY_ROLE")
    bootstrap_tag: str = Field(default="tag:bootstrap", alias="BOOTSTRAP_TAG")
    ts_localapi_socket: str = Field(default="/var/run/tailscale/tailscaled.sock", alias="TS_LOCALAPI_SOCKET")
    ts_localapi_base_url: str = Field(default="http://local-tailscaled.sock", alias="TS_LOCALAPI_BASE_URL")
    ts_localapi_timeout_seconds: float = Field(default=3.0, alias="TS_LOCALAPI_TIMEOUT_SECONDS")
    tailscale_cli_path: str = Field(default="tailscale", alias="TAILSCALE_CLI_PATH")
    tailnet_name: str = Field(default="-", alias="TAILNET_NAME")
    ts_api_client_id: str = Field(alias="TS_API_CLIENT_ID")
    ts_api_client_secret: str = Field(alias="TS_API_CLIENT_SECRET")
    ts_oauth_token_url: str = Field(default="https://api.tailscale.com/api/v2/oauth/token", alias="TS_OAUTH_TOKEN_URL")
    tailscale_api_base_url: str = Field(default="https://api.tailscale.com/api/v2", alias="TAILSCALE_API_BASE_URL")
    tailscale_http_timeout_seconds: float = Field(default=10.0, alias="TAILSCALE_HTTP_TIMEOUT_SECONDS")
    bootstrap_env: dict[str, str] = Field(default_factory=dict, alias="BOOTSTRAP_ENV_JSON")
    bootstrap_files: list[dict[str, str]] = Field(default_factory=list, alias="BOOTSTRAP_FILES_JSON")
    bootstrap_config: dict[str, Any] | None = Field(default=None, alias="BOOTSTRAP_CONFIG_JSON")

    @field_validator("bootstrap_env", mode="before")
    @classmethod
    def parse_bootstrap_env(cls, value: Any) -> dict[str, str]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
        parsed = json.loads(value)
        return {str(key): str(item) for key, item in parsed.items()}

    @field_validator("bootstrap_files", mode="before")
    @classmethod
    def parse_bootstrap_files(cls, value: Any) -> list[dict[str, str]]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return value
        return json.loads(value)

    @field_validator("bootstrap_config", mode="before")
    @classmethod
    def parse_bootstrap_config(cls, value: Any) -> dict[str, Any] | None:
        if value in (None, ""):
            return None
        if isinstance(value, dict):
            return value
        return json.loads(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
