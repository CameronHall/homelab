from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.models import ProvisioningRecord, ProvisioningState
from shared.util import utc_now

from ..config import Settings, get_settings
from ..schemas import BootstrapFile, BootstrapNodeRequest, BootstrapSecretRequest, BootstrapSecretResponse
from ..tailscale_auth import BootstrapCallerIdentity, TailscaleAuthHelper
from ..tailscale_control import TailscaleControlClient, TailscaleControlError, get_tailscale_control_client
from .infisical import InfisicalClient, InfisicalError, get_infisical_client


class BootstrapService:
    def __init__(self, settings: Settings, tailscale_control: TailscaleControlClient, infisical: InfisicalClient) -> None:
        self.settings = settings
        self.tailscale_control = tailscale_control
        self.infisical = infisical

    def fetch_secret_payload(
        self,
        session: Session,
        identity: BootstrapCallerIdentity,
        payload: BootstrapSecretRequest,
    ) -> BootstrapSecretResponse:
        record = self.authorize_record(session=session, identity=identity, payload=payload)

        if record.state != ProvisioningState.SECRETS_DELIVERED.value:
            record.state = ProvisioningState.SECRETS_DELIVERED.value
            record.secrets_retrieved_at = record.secrets_retrieved_at or utc_now()
        else:
            record.secrets_retrieved_at = record.secrets_retrieved_at or utc_now()
        session.add(record)
        session.commit()

        env = dict(self.settings.bootstrap_env)

        if self.infisical.is_configured:
            try:
                token = self.infisical.get_access_token()
                infisical_secrets = self.infisical.list_secrets(token)
                env.update(infisical_secrets)
            except InfisicalError as exc:
                raise HTTPException(status_code=502, detail=f"failed to fetch secrets from Infisical: {exc}") from exc

            env["INFISICAL_CLIENT_ID"] = self.settings.infisical_client_id or ""
            env["INFISICAL_CLIENT_SECRET"] = self.settings.infisical_client_secret or ""

        return BootstrapSecretResponse(
            env=env,
            files=[BootstrapFile(**item) for item in self.settings.bootstrap_files],
            config=self.settings.bootstrap_config,
        )

    def authorize_record(
        self,
        session: Session,
        identity: BootstrapCallerIdentity,
        payload: BootstrapNodeRequest,
    ) -> ProvisioningRecord:
        if self.settings.bootstrap_capability not in identity.capabilities:
            raise HTTPException(status_code=403, detail="bootstrap capability not granted")

        record = self._resolve_record(session=session, identity=identity, payload=payload)
        if record is None:
            raise HTTPException(status_code=404, detail="bootstrap record not found")

        if record.is_expired():
            record.state = ProvisioningState.EXPIRED.value
            session.add(record)
            session.commit()
            raise HTTPException(status_code=410, detail="bootstrap record expired")

        if payload.node_id and payload.node_id != record.node_id:
            raise HTTPException(status_code=403, detail="body node_id does not match provisioning record")
        if payload.hostname and self._normalize_hostname(payload.hostname) != self._normalize_hostname(record.hostname):
            raise HTTPException(status_code=403, detail="hostname does not match provisioning record")
        if payload.instance_id and payload.instance_id != record.instance_id:
            raise HTTPException(status_code=403, detail="instance_id does not match provisioning record")
        if identity.node_name and self._normalize_hostname(identity.node_name) != self._normalize_hostname(record.hostname):
            raise HTTPException(status_code=403, detail="tailscale caller identity does not match provisioning record")

        approval_state = self._refresh_approval_state(record=record, identity=identity)
        if not approval_state:
            record.state = ProvisioningState.WAITING_FOR_APPROVAL.value
            session.add(record)
            session.commit()
            raise HTTPException(status_code=425, detail="device approval still pending")

        return record

    def _refresh_approval_state(self, record: ProvisioningRecord, identity: BootstrapCallerIdentity) -> bool:
        try:
            device = self.tailscale_control.find_device(
                hostname=record.hostname,
                node_name=identity.node_name,
                tailnet_ip=identity.tailnet_ip,
            )
        except TailscaleControlError:
            return bool(record.approved)

        if device is None:
            return bool(record.approved)

        if self.settings.bootstrap_tag not in device.tags:
            return False
        if device.authorized is True:
            record.approved = True
            record.state = ProvisioningState.APPROVED.value
            return True
        return False

    def _resolve_record(
        self,
        session: Session,
        identity: BootstrapCallerIdentity,
        payload: BootstrapNodeRequest,
    ) -> ProvisioningRecord | None:
        if identity.node_name:
            statement = select(ProvisioningRecord).where(
                ProvisioningRecord.hostname == self._normalize_hostname(identity.node_name)
            )
            candidates = session.execute(statement).scalars().all()
            if payload.node_id:
                return next((candidate for candidate in candidates if candidate.node_id == payload.node_id), None)
            return candidates[0] if candidates else None

        if payload.node_id:
            return session.execute(
                select(ProvisioningRecord).where(ProvisioningRecord.node_id == payload.node_id)
            ).scalar_one_or_none()

        if payload.hostname:
            return session.execute(
                select(ProvisioningRecord).where(
                    ProvisioningRecord.hostname == self._normalize_hostname(payload.hostname)
                )
            ).scalar_one_or_none()

        raise HTTPException(status_code=403, detail="bootstrap caller identity could not be matched to a provisioning record")

    @staticmethod
    def _normalize_hostname(value: str) -> str:
        normalized = TailscaleAuthHelper.normalize_node_name(value)
        return normalized or value


@lru_cache(maxsize=1)
def get_bootstrap_service() -> BootstrapService:
    return BootstrapService(get_settings(), get_tailscale_control_client(), get_infisical_client())
