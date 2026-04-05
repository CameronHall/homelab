from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthKeyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    key_id: str | None = None
    created_at: datetime | None = None
    expires_at: datetime
    tags: list[str]


class HealthResponse(BaseModel):
    status: str = "ok"
