from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .util import ensure_utc, utc_now


class Base(DeclarativeBase):
    pass


class ProvisioningState(str, Enum):
    CREATED = "created"
    USER_DATA_ISSUED = "user_data_issued"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    SECRETS_DELIVERED = "secrets_delivered"
    EXPIRED = "expired"
    FAILED = "failed"


class ProvisioningRecord(Base):
    __tablename__ = "provisioning_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    seed_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    instance_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tailscale_auth_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tailscale_auth_key_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tailscale_auth_key_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tailscale_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default=ProvisioningState.CREATED.value, index=True)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_data_rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    secrets_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_expired(self, now: datetime | None = None) -> bool:
        current_time = now or utc_now()
        expires_at = ensure_utc(self.expires_at)
        return current_time >= expires_at


class ClusterState(Base):
    __tablename__ = "cluster_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    established: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bootstrap_node: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ClusterBootstrapLock(Base):
    __tablename__ = "cluster_bootstrap_locks"

    cluster_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
