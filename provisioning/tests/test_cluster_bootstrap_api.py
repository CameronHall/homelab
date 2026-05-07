from __future__ import annotations

from datetime import timedelta
from email.header import Header

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shared.models import Base, ClusterBootstrapLock, ClusterState, ProvisioningRecord, ProvisioningState
from shared.util import utc_now

from conftest import load_service_module


def create_record(database_url: str, *, node_id: str, hostname: str, approved: bool = True) -> None:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        session.add(
            ProvisioningRecord(
                node_id=node_id,
                seed_token=f"seed-{node_id}",
                instance_id=f"iid-{node_id}",
                hostname=hostname,
                tailscale_tags=["tag:bootstrap"],
                state=ProvisioningState.APPROVED.value if approved else ProvisioningState.USER_DATA_ISSUED.value,
                approved=approved,
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
        session.commit()


def load_client(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'cluster.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SECRET_API_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("TAILSCALE_AUTH_MODE", "serve_http")
    monkeypatch.setenv("TAILNET_NAME", "example-tailnet.ts.net")
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("BOOTSTRAP_CAPABILITY", "homelab.local/cap/bootstrap")
    monkeypatch.setenv("BOOTSTRAP_CAPABILITY_ROLE", "bootstrap-client")
    monkeypatch.setenv("BOOTSTRAP_TAG", "tag:bootstrap")
    monkeypatch.setenv("MICROK8S_CLUSTER_NAME", "homelab")

    main_module = load_service_module("secret-api", "secret_api_app", "main", reload_package=True)
    config_module = load_service_module("secret-api", "secret_api_app", "config")
    auth_module = load_service_module("secret-api", "secret_api_app", "authz")
    helper_module = load_service_module("secret-api", "secret_api_app", "tailscale_auth")
    control_module = load_service_module("secret-api", "secret_api_app", "tailscale_control")
    bootstrap_module = load_service_module("secret-api", "secret_api_app", "services.bootstrap")
    cluster_module = load_service_module("secret-api", "secret_api_app", "services.cluster_bootstrap")

    config_module.get_settings.cache_clear()
    auth_module.get_settings.cache_clear()
    helper_module.get_settings.cache_clear()
    helper_module.get_tailscale_auth_helper.cache_clear()
    control_module.get_settings.cache_clear()
    control_module.get_tailscale_control_client.cache_clear()
    bootstrap_module.get_bootstrap_service.cache_clear()
    cluster_module.get_cluster_bootstrap_service.cache_clear()

    def fake_find_device(self, *, hostname: str | None, node_name: str | None, tailnet_ip: str | None):
        return None

    monkeypatch.setattr(control_module.TailscaleControlClient, "find_device", fake_find_device)

    return TestClient(main_module.app), database_url, cluster_module


def bootstrap_capabilities_header() -> str:
    return Header(
        '{"homelab.local/cap/bootstrap":[{"role":"bootstrap-client"}]}',
        "utf-8",
    ).encode()


def test_first_node_claims_cluster_bootstrap(monkeypatch, tmp_path):
    client, database_url, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url, node_id="node-1", hostname="bootstrap-01")

    response = client.post(
        "/v1/bootstrap-cluster",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json={
            "node_id": "node-1",
            "hostname": "bootstrap-01",
            "instance_id": "iid-node-1",
            "cluster_name": "homelab",
            "api_endpoint": "10.0.0.10",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"role": "bootstrap", "cluster_name": "homelab", "join_command": None}

    engine = create_engine(database_url, future=True, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        state = session.execute(select(ClusterState).where(ClusterState.cluster_name == "homelab")).scalar_one()
        locks = session.execute(select(ClusterBootstrapLock)).scalars().all()

    assert state.established is True
    assert state.bootstrap_node == "bootstrap-01"
    assert state.api_endpoint == "10.0.0.10"
    assert locks == []


def test_bootstrap_node_remains_bootstrap_on_repeat_calls(monkeypatch, tmp_path):
    client, database_url, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url, node_id="node-1", hostname="bootstrap-01")

    payload = {
        "node_id": "node-1",
        "hostname": "bootstrap-01",
        "instance_id": "iid-node-1",
        "cluster_name": "homelab",
        "api_endpoint": "10.0.0.10",
    }
    first = client.post("/v1/bootstrap-cluster", headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()}, json=payload)
    second = client.post("/v1/bootstrap-cluster", headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()}, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["role"] == "bootstrap"
    assert second.json()["role"] == "bootstrap"


def test_existing_cluster_returns_fresh_join_command(monkeypatch, tmp_path):
    client, database_url, cluster_module = load_client(monkeypatch, tmp_path)
    create_record(database_url, node_id="node-1", hostname="bootstrap-01")
    create_record(database_url, node_id="node-2", hostname="worker-02")

    monkeypatch.setattr(
        cluster_module.MicroK8sJoinCommandProvider,
        "generate_join_command",
        lambda self, state: "microk8s join 10.0.0.10:25000/token/secret",
    )

    bootstrap_payload = {
        "node_id": "node-1",
        "hostname": "bootstrap-01",
        "instance_id": "iid-node-1",
        "cluster_name": "homelab",
        "api_endpoint": "10.0.0.10",
    }
    join_payload = {
        "node_id": "node-2",
        "hostname": "worker-02",
        "instance_id": "iid-node-2",
        "cluster_name": "homelab",
        "api_endpoint": "10.0.0.11",
    }

    bootstrap_response = client.post(
        "/v1/bootstrap-cluster",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json=bootstrap_payload,
    )
    join_response = client.post(
        "/v1/bootstrap-cluster",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json=join_payload,
    )

    assert bootstrap_response.status_code == 200
    assert join_response.status_code == 200
    assert join_response.json() == {
        "role": "join",
        "cluster_name": "homelab",
        "join_command": "microk8s join 10.0.0.10:25000/token/secret",
    }


def test_join_request_fails_when_service_cannot_generate_command(monkeypatch, tmp_path):
    client, database_url, cluster_module = load_client(monkeypatch, tmp_path)
    create_record(database_url, node_id="node-1", hostname="bootstrap-01")
    create_record(database_url, node_id="node-2", hostname="worker-02")

    monkeypatch.setattr(
        cluster_module.MicroK8sJoinCommandProvider,
        "generate_join_command",
        lambda self, state: (_ for _ in ()).throw(
            cluster_module.ClusterCommandError("failed to generate MicroK8s join command from bootstrap node")
        ),
    )

    client.post(
        "/v1/bootstrap-cluster",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json={
            "node_id": "node-1",
            "hostname": "bootstrap-01",
            "instance_id": "iid-node-1",
            "cluster_name": "homelab",
            "api_endpoint": "10.0.0.10",
        },
    )
    response = client.post(
        "/v1/bootstrap-cluster",
        headers={"Tailscale-App-Capabilities": bootstrap_capabilities_header()},
        json={
            "node_id": "node-2",
            "hostname": "worker-02",
            "instance_id": "iid-node-2",
            "cluster_name": "homelab",
            "api_endpoint": "10.0.0.11",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "failed to generate MicroK8s join command from bootstrap node"
