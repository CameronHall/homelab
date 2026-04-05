from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class BootstrapSecretRequest(BaseModel):
    node_id: str | None = None
    hostname: str | None = None
    instance_id: str | None = None


class BootstrapFile(BaseModel):
    path: str
    content: str


class BootstrapSecretResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"env": {"EXAMPLE_TOKEN": "..."}, "files": []}})

    env: dict[str, str] = Field(default_factory=dict)
    files: list[BootstrapFile] = Field(default_factory=list)
    config: dict[str, Any] | None = None
