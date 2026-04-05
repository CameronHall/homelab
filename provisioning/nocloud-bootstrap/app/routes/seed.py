from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..services.cloudinit import CloudInitService, get_cloudinit_service
from ..services.provisioning import ProvisioningService, get_provisioning_service

router = APIRouter()


@router.get("/seed/{token}/", response_class=PlainTextResponse)
@router.get("/seed/{token}", response_class=PlainTextResponse)
def seed_root(
    token: str,
    session: Session = Depends(get_session),
    provisioning_service: ProvisioningService = Depends(get_provisioning_service),
) -> PlainTextResponse:
    provisioning_service.get_active_record(session=session, token=token)
    body = (
        "NoCloud seed root\n"
        f"meta-data: /seed/{token}/meta-data\n"
        f"user-data: /seed/{token}/user-data\n"
    )
    return PlainTextResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/seed/{token}/meta-data", response_class=PlainTextResponse)
def meta_data(
    token: str,
    session: Session = Depends(get_session),
    provisioning_service: ProvisioningService = Depends(get_provisioning_service),
    cloudinit_service: CloudInitService = Depends(get_cloudinit_service),
) -> PlainTextResponse:
    record = provisioning_service.get_active_record(session=session, token=token)
    return PlainTextResponse(
        cloudinit_service.render_meta_data(record),
        media_type="text/yaml; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/seed/{token}/user-data", response_class=PlainTextResponse)
def user_data(
    token: str,
    session: Session = Depends(get_session),
    provisioning_service: ProvisioningService = Depends(get_provisioning_service),
    cloudinit_service: CloudInitService = Depends(get_cloudinit_service),
) -> PlainTextResponse:
    record = provisioning_service.issue_user_data(session=session, token=token)
    return PlainTextResponse(
        cloudinit_service.render_user_data(record),
        media_type="text/cloud-config; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
