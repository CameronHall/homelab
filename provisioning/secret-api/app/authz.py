from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings
from .tailscale_auth import BootstrapCallerIdentity, TailscaleAuthHelper, TailscaleAuthorizationError, get_tailscale_auth_helper

logger = logging.getLogger(__name__)


def get_bootstrap_caller_identity(
    request: Request,
    settings: Settings = Depends(get_settings),
    auth_helper: TailscaleAuthHelper = Depends(get_tailscale_auth_helper),
) -> BootstrapCallerIdentity:
    remote_addr = request.client.host if request.client else None
    header_value = request.headers.get(settings.tailscale_app_capabilities_header)
    if settings.tailscale_auth_mode == "serve_http":
        if not header_value:
            raise HTTPException(status_code=403, detail="missing tailscale app capabilities header")
        try:
            capabilities = auth_helper.parse_app_capabilities(header_value)
            authorized_capabilities = auth_helper.authorize_app_capabilities(capabilities)
        except TailscaleAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        identity = BootstrapCallerIdentity(
            tailnet_ip=None,
            node_name=None,
            tags=[],
            capabilities=authorized_capabilities,
            auth_source="serve_app_caps",
        )
    else:
        if not remote_addr:
            raise HTTPException(status_code=403, detail="missing remote client address for tailscale whois")
        try:
            identity = auth_helper.lookup_whois_identity(remote_addr)
        except TailscaleAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    logger.info(
        "bootstrap caller authorized",
        extra={
            "auth_source": identity.auth_source,
            "node_name": identity.node_name,
            "tailnet_ip": identity.tailnet_ip,
            "remote_addr": remote_addr,
        },
    )
    return identity
