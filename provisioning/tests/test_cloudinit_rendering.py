from __future__ import annotations

import io
import logging
from datetime import timedelta

from shared.models import ProvisioningRecord, ProvisioningState
from shared.util import JsonFormatter, SensitiveDataFilter, utc_now

from conftest import load_service_module


def test_cloudinit_template_contains_required_bootstrap_behaviors(monkeypatch):
    service = _make_cloudinit_service(monkeypatch)
    rendered = service.render_user_data(_make_record())

    assert rendered.startswith("#cloud-config")
    assert "set -euo pipefail" in rendered
    assert "ssh_import_id:" in rendered
    assert "- gh:test-user" in rendered
    assert "/usr/local/bin/bootstrap.sh" in rendered
    assert "/etc/systemd/system/bootstrap.service" in rendered
    assert "--authkey=tskey-auth-test" in rendered
    assert "--advertise-tags=tag:bootstrap" in rendered
    assert "/etc/bootstrap/secrets.env" in rendered
    assert "CLUSTER_BOOTSTRAP_API_URL" in rendered
    assert 'CLUSTER_NAME="homelab"' in rendered
    assert "microk8s enable dns hostpath-storage" in rendered
    assert "microk8s enable dns registry" not in rendered
    assert "403|409|425|502|503|504" in rendered


def test_cloudinit_template_omits_ssh_import_id_when_disabled(monkeypatch):
    service = _make_cloudinit_service(monkeypatch, BOOTSTRAP_SSH_IMPORT_ID="   ")
    rendered = service.render_user_data(_make_record())

    assert "ssh_import_id:" not in rendered


def _make_cloudinit_service(monkeypatch, **env_overrides):
    """Return a CloudInitService wired to test settings.

    Pass keyword arguments to override any individual env var, e.g.
    ``_make_cloudinit_service(monkeypatch, BOOTSTRAP_SSH_IMPORT_ID="   ")``.
    """
    defaults = {
        "TS_API_CLIENT_ID": "client-id",
        "TS_API_CLIENT_SECRET": "client-secret",
        "SECRET_API_URL": "https://secret-api.tailnet.example/v1/bootstrap-secrets",
        "CLUSTER_BOOTSTRAP_API_URL": "https://secret-api.tailnet.example/v1/bootstrap-cluster",
        "MICROK8S_CLUSTER_NAME": "homelab",
        "BOOTSTRAP_SSH_IMPORT_ID": "gh:test-user",
        "UBUNTU_PRO_TOKEN": "pro-token",
        "HOMELAB_REPO_URL": "https://github.com/CameronHall/homelab",
        "HOMELAB_REPO_REVISION": "master",
    }
    for key, val in {**defaults, **env_overrides}.items():
        monkeypatch.setenv(key, val)

    config_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "config", reload_package=True)
    cloudinit_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "services.cloudinit")
    config_module.get_settings.cache_clear()
    return cloudinit_module.CloudInitService(config_module.get_settings())


def _make_record(**overrides):
    defaults = dict(
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
    return ProvisioningRecord(**{**defaults, **overrides})


def test_bootstrap_script_survives_yaml_block_scalar_parsing(monkeypatch):
    """Regression: heredoc content at column 0 in the Jinja template silently truncates
    bootstrap.sh when the YAML block scalar parser reaches a line that is less indented
    than the established content indentation.  The fix is to indent every heredoc line
    (including EOF) by 6 spaces in the template so YAML strips them to column 0 in the
    rendered script.

    This test catches the regression by:
    1. Rendering user-data and parsing it as YAML (the same way cloud-init does).
    2. Extracting the bootstrap.sh content from write_files.
    3. Asserting that the full install_argocd() function — including the Application
       YAML heredoc — is present in the extracted string.

    If the block scalar is truncated, the Application YAML lines are missing from
    the parsed content even though they appear in the raw rendered string.
    """
    import yaml

    service = _make_cloudinit_service(monkeypatch)
    rendered = service.render_user_data(_make_record())

    doc = yaml.safe_load(rendered)
    write_files = {entry["path"]: entry["content"] for entry in doc.get("write_files", [])}
    bootstrap_sh = write_files.get("/usr/local/bin/bootstrap.sh", "")

    # The full install_argocd function must survive YAML block-scalar parsing.
    assert "install_argocd()" in bootstrap_sh, "install_argocd function missing from parsed bootstrap.sh"
    assert 'microk8s kubectl apply -n argocd -f' in bootstrap_sh
    assert "microk8s kubectl wait deployment argocd-server" in bootstrap_sh

    # The Application YAML heredoc content must be present after YAML parsing.
    # These lines would be absent if the block scalar was terminated early.
    assert "apiVersion: argoproj.io/v1alpha1" in bootstrap_sh, (
        "ArgoCD Application YAML missing — block scalar may have been truncated by "
        "column-0 heredoc content in the Jinja template"
    )
    assert "kind: Application" in bootstrap_sh
    assert "path: kube/clusters/homelab" in bootstrap_sh
    assert "selfHeal: true" in bootstrap_sh

    # The EOF terminator must be at column 0 in the rendered script so the heredoc
    # closes correctly.  After YAML strips 6 spaces of indentation it should appear
    # as a bare "EOF" on its own line.
    assert "\nEOF\n" in bootstrap_sh, "heredoc EOF terminator not at column 0 in rendered script"

    # install_argocd must be called from main()
    assert "install_argocd" in bootstrap_sh.split("main()")[1] or "install_argocd" in bootstrap_sh


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
