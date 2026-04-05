from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..authz import get_bootstrap_caller_identity
from ..db import get_session
from ..schemas import BootstrapSecretRequest, BootstrapSecretResponse
from ..services.bootstrap import BootstrapService, get_bootstrap_service
from ..tailscale_auth import BootstrapCallerIdentity

router = APIRouter()


@router.post("/v1/bootstrap-secrets", response_model=BootstrapSecretResponse)
def bootstrap_secrets(
    payload: BootstrapSecretRequest,
    session: Session = Depends(get_session),
    identity: BootstrapCallerIdentity = Depends(get_bootstrap_caller_identity),
    bootstrap_service: BootstrapService = Depends(get_bootstrap_service),
) -> BootstrapSecretResponse:
    return bootstrap_service.fetch_secret_payload(session=session, identity=identity, payload=payload)
