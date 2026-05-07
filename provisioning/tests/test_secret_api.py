from __future__ import annotations

from datetime import timedelta
from email.header import Header

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shared.models import Base, ProvisioningRecord, ProvisioningState
from shared.util import utc_now

from conftest import load_service_module


def create_record(database_url: str, approved: bool = False) -> None:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        session.add(
            ProvisioningRecord(
                node_id="node-123",
                seed_token="seed-123",
                instance_id="iid-123",
                hostname="bootstrap-01",
                tailscale_tags=["tag:bootstrap"],
                state=ProvisioningState.APPROVED.value if approved else ProvisioningState.USER_DATA_ISSUED.value,
                approved=approved,
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
        session.commit()


def load_client(monkeypatch, tmp_path, auth_mode: str = "serve_http"):
    database_url = f"sqlite:///{tmp_path / 'secret.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SECRET_API_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("TAILSCALE_AUTH_MODE", auth_mode)
    monkeypatch.setenv("TAILNET_NAME", "example-tailnet.ts.net")
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("BOOTSTRAP_CAPABILITY", "homelab.local/cap/bootstrap")
    monkeypatch.setenv("BOOTSTRAP_CAPABILITY_ROLE", "bootstrap-client")
    monkeypatch.setenv("BOOTSTRAP_TAG", "tag:bootstrap")
    monkeypatch.setenv("BOOTSTRAP_ENV_JSON", '{"EXAMPLE_TOKEN":"value-123"}')
    monkeypatch.setenv(
        "BOOTSTRAP_FILES_JSON",
        '[{"path":"/etc/example/app.conf","content":"configured=true\\n"}]',
    )
    monkeypatch.setenv("BOOTSTRAP_CONFIG_JSON", '{"service":"example","mode":"bootstrap","profile":"bootstrap"}')

    monkeypatch.setenv("INFISICAL_CLIENT_ID", "")
    monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "")
    monkeypatch.setenv("INFISICAL_PROJECT_ID", "")

    main_module = load_service_module("secret-api", "secret_api_app", "main", reload_package=True)
    service_module = load_service_module("secret-api", "secret_api_app", "services.bootstrap")
    infisical_module = load_service_module("secret-api", "secret_api_app", "services.infisical")
    config_module = load_service_module("secret-api", "secret_api_app", "config")
    auth_module = load_service_module("secret-api", "secret_api_app", "authz")
    helper_module = load_service_module("secret-api", "secret_api_app", "tailscale_auth")
    control_module = load_service_module("secret-api", "secret_api_app", "tailscale_control")
    config_module.get_settings.cache_clear()
    service_module.get_bootstrap_service.cache_clear()
    infisical_module.get_infisical_client.cache_clear()
    auth_module.get_settings.cache_clear()
    helper_module.get_settings.cache_clear()
    helper_module.get_tailscale_auth_helper.cache_clear()
    control_module.get_settings.cache_clear()
    control_module.get_tailscale_control_client.cache_clear()

    return TestClient(main_module.app), database_url, helper_module, control_module


def bootstrap_capabilities_header() -> str:
    return Header(
        '{"homelab.local/cap/bootstrap":[{"role":"bootstrap-client"}]}',
        "utf-8",
    ).encode()


def test_secret_api_refuses_before_approval(monkeypatch, tmp_path):
    client, database_url, _, control_module = load_client(monkeypatch, tmp_path)
    create_record(database_url, approved=False)

    def fake_find_device(self, *, hostname: str | None, node_name: str | None, tailnet_ip: str | None):
        return control_module.TailnetDevice(
            device_id="dev-1",
            name="bootstrap-01",
            hostname="bootstrap-01",
            addresses=["100.99.0.10"],
            tags=["tag:bootstrap"],
            authorized=False,
            created=None,
        )

    monkeypatch.setattr(control_module.TailscaleControlClient, "find_device", fake_find_device)

    response = client.post(
        "/v1/bootstrap-secrets",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 425

    engine = create_engine(database_url, future=True, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        stored = session.execute(select(ProvisioningRecord).where(ProvisioningRecord.node_id == "node-123")).scalar_one()

    assert stored.state == ProvisioningState.WAITING_FOR_APPROVAL.value
    assert stored.secrets_retrieved_at is None


def test_secret_api_succeeds_after_approval(monkeypatch, tmp_path):
    client, database_url, _, control_module = load_client(monkeypatch, tmp_path)
    create_record(database_url, approved=False)

    def fake_find_device(self, *, hostname: str | None, node_name: str | None, tailnet_ip: str | None):
        return control_module.TailnetDevice(
            device_id="dev-1",
            name="bootstrap-01",
            hostname="bootstrap-01",
            addresses=["100.99.0.10"],
            tags=["tag:bootstrap"],
            authorized=True,
            created=None,
        )

    monkeypatch.setattr(control_module.TailscaleControlClient, "find_device", fake_find_device)

    response = client.post(
        "/v1/bootstrap-secrets",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "env": {"EXAMPLE_TOKEN": "value-123"},
        "files": [{"path": "/etc/example/app.conf", "content": "configured=true\n"}],
        "config": {"service": "example", "mode": "bootstrap", "profile": "bootstrap"},
    }

    engine = create_engine(database_url, future=True, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        stored = session.execute(select(ProvisioningRecord).where(ProvisioningRecord.node_id == "node-123")).scalar_one()

    assert stored.approved is True
    assert stored.state == ProvisioningState.SECRETS_DELIVERED.value
    assert stored.secrets_retrieved_at is not None


def test_malformed_capabilities_header_is_rejected(monkeypatch, tmp_path):
    client, database_url, _, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url, approved=True)

    response = client.post(
        "/v1/bootstrap-secrets",
        headers={"Tailscale-App-Capabilities": "not-json"},
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "invalid tailscale app capabilities header"


def test_missing_header_in_serve_mode_is_rejected(monkeypatch, tmp_path):
    client, database_url, _, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url, approved=True)

    response = client.post(
        "/v1/bootstrap-secrets",
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "missing tailscale app capabilities header"


def test_direct_whois_mode_with_resolvable_caller_ip_succeeds(monkeypatch, tmp_path):
    client, database_url, helper_module, control_module = load_client(monkeypatch, tmp_path, auth_mode="direct_whois")
    create_record(database_url, approved=False)

    def fake_lookup(self, remote_addr: str):
        return helper_module.BootstrapCallerIdentity(
            tailnet_ip="100.99.0.10",
            node_name="bootstrap-01",
            tags=["tag:bootstrap"],
            capabilities={"homelab.local/cap/bootstrap": [{"role": "bootstrap-client"}]},
            auth_source="direct_whois",
        )

    monkeypatch.setattr(helper_module.TailscaleAuthHelper, "lookup_whois_identity", fake_lookup)

    def fake_find_device(self, *, hostname: str | None, node_name: str | None, tailnet_ip: str | None):
        return control_module.TailnetDevice(
            device_id="dev-2",
            name="bootstrap-01",
            hostname="bootstrap-01",
            addresses=["100.99.0.10"],
            tags=["tag:bootstrap"],
            authorized=True,
            created=None,
        )

    monkeypatch.setattr(control_module.TailscaleControlClient, "find_device", fake_find_device)

    response = client.post(
        "/v1/bootstrap-secrets",
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 200
    assert response.json()["env"] == {"EXAMPLE_TOKEN": "value-123"}


def test_direct_whois_mode_with_unresolvable_caller_ip_is_rejected(monkeypatch, tmp_path):
    client, database_url, helper_module, _ = load_client(monkeypatch, tmp_path, auth_mode="direct_whois")
    create_record(database_url, approved=True)

    def fake_lookup(self, remote_addr: str):
        raise helper_module.TailscaleAuthorizationError("unable to resolve caller via tailscale whois")

    monkeypatch.setattr(helper_module.TailscaleAuthHelper, "lookup_whois_identity", fake_lookup)

    response = client.post(
        "/v1/bootstrap-secrets",
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "unable to resolve caller via tailscale whois"


def test_node_provisioning_mismatch_is_rejected(monkeypatch, tmp_path):
    client, database_url, helper_module, control_module = load_client(monkeypatch, tmp_path, auth_mode="direct_whois")
    create_record(database_url, approved=True)

    def fake_lookup(self, remote_addr: str):
        return helper_module.BootstrapCallerIdentity(
            tailnet_ip="100.99.0.30",
            node_name="other-node",
            tags=["tag:bootstrap"],
            capabilities={"homelab.local/cap/bootstrap": [{"role": "bootstrap-client"}]},
            auth_source="direct_whois",
        )

    monkeypatch.setattr(helper_module.TailscaleAuthHelper, "lookup_whois_identity", fake_lookup)

    def fake_find_device(self, *, hostname: str | None, node_name: str | None, tailnet_ip: str | None):
        return control_module.TailnetDevice(
            device_id="dev-3",
            name="other-node",
            hostname="other-node",
            addresses=["100.99.0.30"],
            tags=["tag:bootstrap"],
            authorized=True,
            created=None,
        )

    monkeypatch.setattr(control_module.TailscaleControlClient, "find_device", fake_find_device)

    response = client.post(
        "/v1/bootstrap-secrets",
        json={"node_id": "node-123", "hostname": "bootstrap-01", "instance_id": "iid-123"},
    )

    assert response.status_code == 404
