from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import ProvisioningRecord, ProvisioningState
from shared.util import ensure_utc, utc_now

from ..config import Settings, get_settings
from ..tailscale_oauth import TailscaleOAuthClient


class ProvisioningService:
    def __init__(self, settings: Settings, oauth_client: TailscaleOAuthClient) -> None:
        self.settings = settings
        self.oauth_client = oauth_client

    def get_active_record(self, session: Session, token: str) -> ProvisioningRecord:
        record = session.execute(
            select(ProvisioningRecord).where(ProvisioningRecord.seed_token == token)
        ).scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="seed token not found")

        if record.is_expired():
            record.state = ProvisioningState.EXPIRED.value
            session.add(record)
            session.commit()
            raise HTTPException(status_code=410, detail="seed token expired")
        return record

    def issue_user_data(self, session: Session, token: str) -> ProvisioningRecord:
        record = self.get_active_record(session=session, token=token)
        now = utc_now()

        if self._should_issue_new_key(record, now):
            auth_key = self.oauth_client.create_bootstrap_auth_key(
                node_id=record.node_id,
                expiry_minutes=self.settings.auth_key_expiry_minutes,
            )
            record.tailscale_auth_key = auth_key.key
            record.tailscale_auth_key_created_at = auth_key.created_at or now
            record.tailscale_auth_key_expires_at = auth_key.expires_at
            record.tailscale_tags = auth_key.tags
            record.user_data_rendered_at = now
            record.state = ProvisioningState.USER_DATA_ISSUED.value
        elif record.state == ProvisioningState.CREATED.value:
            record.state = ProvisioningState.USER_DATA_ISSUED.value
            record.user_data_rendered_at = record.user_data_rendered_at or now

        session.add(record)
        session.commit()
        session.refresh(record)
        return record

    def _should_issue_new_key(self, record: ProvisioningRecord, now) -> bool:
        if not record.tailscale_auth_key:
            return True
        if not record.user_data_rendered_at:
            return True
        auth_key_expires_at = ensure_utc(record.tailscale_auth_key_expires_at)
        rendered_at = ensure_utc(record.user_data_rendered_at)
        if auth_key_expires_at and now >= auth_key_expires_at:
            return True
        reuse_deadline = rendered_at + timedelta(seconds=self.settings.user_data_reuse_ttl_seconds)
        return now > reuse_deadline and record.state != ProvisioningState.SECRETS_DELIVERED.value


@lru_cache(maxsize=1)
def get_provisioning_service() -> ProvisioningService:
    settings = get_settings()
    return ProvisioningService(settings=settings, oauth_client=TailscaleOAuthClient(settings))
