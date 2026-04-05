from __future__ import annotations

import io
import logging
from datetime import timedelta

from shared.models import ProvisioningRecord, ProvisioningState
from shared.util import JsonFormatter, SensitiveDataFilter, utc_now

from conftest import load_service_module


def test_cloudinit_template_contains_required_bootstrap_behaviors(monkeypatch):
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SECRET_API_URL", "https://secret-api.tailnet.example/v1/bootstrap-secrets")
    monkeypatch.setenv("BOOTSTRAP_SSH_IMPORT_ID", "gh:test-user")
    monkeypatch.setenv("UBUNTU_PRO_TOKEN", "pro-token")

    config_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "config", reload_package=True)
    cloudinit_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "services.cloudinit")
    config_module.get_settings.cache_clear()
    service = cloudinit_module.CloudInitService(config_module.get_settings())

    record = ProvisioningRecord(
        node_id="node-123",
        seed_token="seed-123",
        instance_id="iid-123",
        hostname="bootstrap-01",
        tailscale_auth_key="tskey-auth-test",
        tailscale_tags=["tag:bootstrap"],
        state=ProvisioningState.USER_DATA_ISSUED.value,
        approved=False,
        expires_at=utc_now() + timedelta(hours=1),
    )

    rendered = service.render_user_data(record)

    assert rendered.startswith("#cloud-config")
    assert "set -euo pipefail" in rendered
    assert "ssh_import_id:" in rendered
    assert "- gh:test-user" in rendered
    assert "/usr/local/bin/bootstrap.sh" in rendered
    assert "/etc/systemd/system/bootstrap.service" in rendered
    assert "--authkey=tskey-auth-test" in rendered
    assert "--advertise-tags=tag:bootstrap" in rendered
    assert "/etc/bootstrap/secrets.env" in rendered
    assert "403|409|425|502|503|504" in rendered


def test_cloudinit_template_omits_ssh_import_id_when_disabled(monkeypatch):
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SECRET_API_URL", "https://secret-api.tailnet.example/v1/bootstrap-secrets")
    monkeypatch.setenv("BOOTSTRAP_SSH_IMPORT_ID", "   ")
    monkeypatch.setenv("UBUNTU_PRO_TOKEN", "pro-token")

    config_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "config", reload_package=True)
    cloudinit_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "services.cloudinit")
    config_module.get_settings.cache_clear()
    service = cloudinit_module.CloudInitService(config_module.get_settings())

    record = ProvisioningRecord(
        node_id="node-123",
        seed_token="seed-123",
        instance_id="iid-123",
        hostname="bootstrap-01",
        tailscale_auth_key="tskey-auth-test",
        tailscale_tags=["tag:bootstrap"],
        state=ProvisioningState.USER_DATA_ISSUED.value,
        approved=False,
        expires_at=utc_now() + timedelta(hours=1),
    )

    rendered = service.render_user_data(record)

    assert "ssh_import_id:" not in rendered


def test_logging_redacts_sensitive_fields():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter(service_name="unit-test"))

    logger = logging.getLogger("provisioning.redaction")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info(
        "issuing bootstrap auth key",
        extra={
            "tailscale_auth_key": "tskey-auth-secret",
            "bootstrap_env_json": {"EXAMPLE_TOKEN": "super-secret"},
            "safe_field": "visible",
        },
    )

    output = stream.getvalue()
    assert "tskey-auth-secret" not in output
    assert "super-secret" not in output
    assert "[REDACTED]" in output
    assert "visible" in output
