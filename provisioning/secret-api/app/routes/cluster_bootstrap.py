from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..authz import get_bootstrap_caller_identity
from ..db import get_session
from ..schemas import ClusterBootstrapRequest, ClusterBootstrapResponse
from ..services.cluster_bootstrap import ClusterBootstrapService, get_cluster_bootstrap_service
from ..tailscale_auth import BootstrapCallerIdentity

router = APIRouter()


@router.post("/v1/bootstrap-cluster", response_model=ClusterBootstrapResponse)
def bootstrap_cluster(
    payload: ClusterBootstrapRequest,
    session: Session = Depends(get_session),
    identity: BootstrapCallerIdentity = Depends(get_bootstrap_caller_identity),
    cluster_bootstrap_service: ClusterBootstrapService = Depends(get_cluster_bootstrap_service),
) -> ClusterBootstrapResponse:
    return cluster_bootstrap_service.decide_role(session=session, identity=identity, payload=payload)
