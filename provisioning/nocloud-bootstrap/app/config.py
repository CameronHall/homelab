from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "nocloud-bootstrap"
    bind_host: str = Field(default="0.0.0.0", alias="NO_CLOUD_BIND_HOST")
    bind_port: int = Field(default=8080, alias="NO_CLOUD_PORT")
    database_url: str = Field(default="sqlite:////data/provisioning.db", alias="DATABASE_URL")
    templates_dir: Path = Field(
        default=Path(__file__).resolve().parent / "templates",
        alias="BOOTSTRAP_TEMPLATE_DIR",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_api_url: str = Field(alias="SECRET_API_URL")
    cluster_bootstrap_api_url: str = Field(alias="CLUSTER_BOOTSTRAP_API_URL")
    microk8s_cluster_name: str = Field(default="homelab", alias="MICROK8S_CLUSTER_NAME")
    argocd_install_manifest_url: str = Field(
        default="https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml",
        alias="ARGOCD_INSTALL_MANIFEST_URL",
    )
    homelab_repo_url: str = Field(
        default="https://github.com/CameronHall/homelab",
        alias="HOMELAB_REPO_URL",
    )
    homelab_repo_revision: str = Field(default="master", alias="HOMELAB_REPO_REVISION")
    tailnet_name: str = Field(default="-", alias="TAILNET_NAME")
    bootstrap_tag: str = Field(default="tag:bootstrap", alias="BOOTSTRAP_TAG")
    bootstrap_ssh_import_id: str = Field(default="-", alias="BOOTSTRAP_SSH_IMPORT_ID")
    auth_key_expiry_minutes: int = Field(default=10, alias="AUTH_KEY_EXPIRY_MINUTES")
    provisioning_record_ttl_hours: int = Field(default=24, alias="PROVISIONING_RECORD_TTL_HOURS")
    user_data_reuse_ttl_seconds: int = Field(default=120, alias="USER_DATA_REUSE_TTL_SECONDS")
    ts_api_client_id: str = Field(alias="TS_API_CLIENT_ID")
    ts_api_client_secret: str = Field(alias="TS_API_CLIENT_SECRET")
    ts_oauth_token_url: str = Field(default="https://api.tailscale.com/api/v2/oauth/token", alias="TS_OAUTH_TOKEN_URL")
    tailscale_api_base_url: str = Field(default="https://api.tailscale.com/api/v2", alias="TAILSCALE_API_BASE_URL")
    http_timeout_seconds: float = Field(default=10.0, alias="TAILSCALE_HTTP_TIMEOUT_SECONDS")
    ubuntu_pro_token: str = Field(default="-", alias="UBUNTU_PRO_TOKEN")

    @field_validator("bootstrap_tag")
    @classmethod
    def validate_bootstrap_tag(cls, value: str) -> str:
        if not value.startswith("tag:"):
            raise ValueError("BOOTSTRAP_TAG must start with 'tag:'")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
