from __future__ import annotations

import shlex
import subprocess
import time
from datetime import timedelta
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models import ClusterBootstrapLock, ClusterState
from shared.util import ensure_utc, utc_now

from ..config import Settings, get_settings
from ..schemas import ClusterBootstrapRequest, ClusterBootstrapResponse
from ..services.bootstrap import BootstrapService, get_bootstrap_service
from ..tailscale_auth import BootstrapCallerIdentity


class ClusterCommandError(RuntimeError):
    pass


class MicroK8sJoinCommandProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_join_command(self, state: ClusterState) -> str:
        target = state.bootstrap_node or state.api_endpoint
        if not target:
            raise ClusterCommandError("cluster bootstrap node is unknown")

        command = [
            "ssh",
            *shlex.split(self.settings.microk8s_bootstrap_ssh_options),
            "-p",
            str(self.settings.microk8s_bootstrap_ssh_port),
        ]
        if self.settings.microk8s_bootstrap_ssh_key_path:
            command.extend(["-i", str(self.settings.microk8s_bootstrap_ssh_key_path)])
        command.append(f"{self.settings.microk8s_bootstrap_ssh_user}@{target}")
        command.append(f"microk8s add-node --token-ttl {self.settings.microk8s_join_token_ttl_seconds}")

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=True,
                text=True,
                timeout=self.settings.microk8s_remote_command_timeout_seconds,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ClusterCommandError("failed to generate MicroK8s join command from bootstrap node") from exc

        join_command = self._extract_join_command(completed.stdout)
        if not join_command:
            raise ClusterCommandError("bootstrap node did not return a valid MicroK8s join command")
        return join_command

    @staticmethod
    def _extract_join_command(output: str) -> str | None:
        for line in output.splitlines():
            candidate = line.strip()
            if candidate.startswith("microk8s join "):
                return candidate
        return None


class ClusterBootstrapService:
    def __init__(
        self,
        settings: Settings,
        bootstrap_service: BootstrapService,
        join_command_provider: MicroK8sJoinCommandProvider,
    ) -> None:
        self.settings = settings
        self.bootstrap_service = bootstrap_service
        self.join_command_provider = join_command_provider

    def decide_role(
        self,
        session: Session,
        identity: BootstrapCallerIdentity,
        payload: ClusterBootstrapRequest,
    ) -> ClusterBootstrapResponse:
        record = self.bootstrap_service.authorize_record(session=session, identity=identity, payload=payload)
        cluster_name = (payload.cluster_name or self.settings.microk8s_cluster_name).strip()
        if not cluster_name:
            raise HTTPException(status_code=400, detail="cluster_name must not be empty")

        self._acquire_lock(session=session, cluster_name=cluster_name, owner_node_id=record.node_id)
        try:
            state = session.execute(
                select(ClusterState).where(ClusterState.cluster_name == cluster_name)
            ).scalar_one_or_none()

            advertised_endpoint = (payload.api_endpoint or record.hostname).strip() if (payload.api_endpoint or record.hostname) else None
            normalized_hostname = self.bootstrap_service._normalize_hostname(record.hostname)

            if state is None:
                state = ClusterState(
                    cluster_name=cluster_name,
                    established=True,
                    bootstrap_node=normalized_hostname,
                    api_endpoint=advertised_endpoint,
                )
                session.add(state)
                session.commit()
                session.refresh(state)
                return ClusterBootstrapResponse(role="bootstrap", cluster_name=cluster_name)

            if not state.established:
                state.established = True
                state.bootstrap_node = normalized_hostname
                state.api_endpoint = advertised_endpoint
                session.add(state)
                session.commit()
                return ClusterBootstrapResponse(role="bootstrap", cluster_name=cluster_name)

            if state.bootstrap_node == normalized_hostname:
                if advertised_endpoint and not state.api_endpoint:
                    state.api_endpoint = advertised_endpoint
                    session.add(state)
                    session.commit()
                return ClusterBootstrapResponse(role="bootstrap", cluster_name=cluster_name)

            try:
                join_command = self.join_command_provider.generate_join_command(state)
            except ClusterCommandError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            return ClusterBootstrapResponse(
                role="join",
                cluster_name=cluster_name,
                join_command=join_command,
            )
        finally:
            self._release_lock(session=session, cluster_name=cluster_name, owner_node_id=record.node_id)

    def _acquire_lock(self, session: Session, cluster_name: str, owner_node_id: str) -> None:
        deadline = time.monotonic() + self.settings.cluster_bootstrap_lock_timeout_seconds
        stale_before = utc_now() - timedelta(seconds=self.settings.cluster_bootstrap_lock_stale_seconds)

        while True:
            existing = session.get(ClusterBootstrapLock, cluster_name)
            if existing is not None and ensure_utc(existing.acquired_at) < stale_before:
                session.delete(existing)
                session.commit()
                session.expire_all()
                continue

            try:
                session.add(
                    ClusterBootstrapLock(
                        cluster_name=cluster_name,
                        owner_node_id=owner_node_id,
                    )
                )
                session.commit()
                return
            except IntegrityError:
                session.rollback()
                if time.monotonic() >= deadline:
                    raise HTTPException(status_code=503, detail="cluster bootstrap lock busy")
                time.sleep(self.settings.cluster_bootstrap_lock_retry_seconds)

    def _release_lock(self, session: Session, cluster_name: str, owner_node_id: str) -> None:
        session.rollback()
        existing = session.get(ClusterBootstrapLock, cluster_name)
        if existing is None or existing.owner_node_id != owner_node_id:
            return
        session.delete(existing)
        session.commit()


@lru_cache(maxsize=1)
def get_cluster_bootstrap_service() -> ClusterBootstrapService:
    settings = get_settings()
    return ClusterBootstrapService(
        settings=settings,
        bootstrap_service=get_bootstrap_service(),
        join_command_provider=MicroK8sJoinCommandProvider(settings),
    )
