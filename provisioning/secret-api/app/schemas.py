from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class BootstrapNodeRequest(BaseModel):
    node_id: str | None = None
    hostname: str | None = None
    instance_id: str | None = None


class BootstrapSecretRequest(BootstrapNodeRequest):
    pass


class ClusterBootstrapRequest(BootstrapNodeRequest):
    cluster_name: str | None = None
    api_endpoint: str | None = None


class BootstrapFile(BaseModel):
    path: str
    content: str


class BootstrapSecretResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"env": {"EXAMPLE_TOKEN": "..."}, "files": []}})

    env: dict[str, str] = Field(default_factory=dict)
    files: list[BootstrapFile] = Field(default_factory=list)
    config: dict[str, Any] | None = None


class ClusterBootstrapResponse(BaseModel):
    role: Literal["bootstrap", "join"]
    cluster_name: str
    join_command: str | None = None
