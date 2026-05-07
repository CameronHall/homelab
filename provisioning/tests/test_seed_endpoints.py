from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shared.models import Base, ProvisioningRecord, ProvisioningState
from shared.util import utc_now

from conftest import load_service_module


def create_record(database_url: str, **overrides) -> ProvisioningRecord:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    record = ProvisioningRecord(
        node_id=overrides.get("node_id", "node-123"),
        seed_token=overrides.get("seed_token", "seed-123"),
        instance_id=overrides.get("instance_id", "iid-123"),
        hostname=overrides.get("hostname", "bootstrap-01"),
        tailscale_tags=["tag:bootstrap"],
        state=ProvisioningState.CREATED.value,
        approved=False,
        expires_at=overrides.get("expires_at", utc_now() + timedelta(hours=1)),
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
    return record


def load_client(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'seed.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("TS_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TS_API_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SECRET_API_URL", "https://secret-api.example.ts.net/v1/bootstrap-secrets")
    monkeypatch.setenv("CLUSTER_BOOTSTRAP_API_URL", "https://secret-api.example.ts.net/v1/bootstrap-cluster")
    monkeypatch.setenv("USER_DATA_REUSE_TTL_SECONDS", "300")
    monkeypatch.setenv("AUTH_KEY_EXPIRY_MINUTES", "10")
    monkeypatch.setenv("UBUNTU_PRO_TOKEN", "pro-token")

    main_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "main", reload_package=True)
    provisioning_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "services.provisioning")
    schema_module = load_service_module("nocloud-bootstrap", "nocloud_bootstrap_app", "schemas")
    provisioning_module.get_provisioning_service.cache_clear()

    call_counter = {"count": 0}

    def fake_create_bootstrap_auth_key(self, node_id: str, expiry_minutes: int):
        call_counter["count"] += 1
        return schema_module.AuthKeyResult(
            key="tskey-auth-test",
            key_id="key-1",
            created_at=utc_now(),
            expires_at=utc_now() + timedelta(minutes=expiry_minutes),
            tags=["tag:bootstrap"],
        )

    monkeypatch.setattr(
        provisioning_module.TailscaleOAuthClient,
        "create_bootstrap_auth_key",
        fake_create_bootstrap_auth_key,
    )
    return TestClient(main_module.app), database_url, call_counter


def test_meta_data_rendering(monkeypatch, tmp_path):
    client, database_url, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url)

    response = client.get("/seed/seed-123/meta-data")

    assert response.status_code == 200
    assert "instance-id: iid-123" in response.text
    assert "local-hostname: bootstrap-01" in response.text


def test_seed_root_lists_child_endpoints(monkeypatch, tmp_path):
    client, database_url, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url)

    response = client.get("/seed/seed-123/")

    assert response.status_code == 200
    assert "/seed/seed-123/meta-data" in response.text
    assert "/seed/seed-123/user-data" in response.text


def test_first_user_data_hit_generates_and_persists_key(monkeypatch, tmp_path):
    client, database_url, call_counter = load_client(monkeypatch, tmp_path)
    create_record(database_url)

    response = client.get("/seed/seed-123/user-data")

    assert response.status_code == 200
    assert "--authkey=tskey-auth-test" in response.text
    assert "--advertise-tags=tag:bootstrap" in response.text
    assert call_counter["count"] == 1

    engine = create_engine(database_url, future=True, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        stored = session.execute(select(ProvisioningRecord).where(ProvisioningRecord.seed_token == "seed-123")).scalar_one()

    assert stored.tailscale_auth_key == "tskey-auth-test"
    assert stored.state == ProvisioningState.USER_DATA_ISSUED.value
    assert stored.user_data_rendered_at is not None


def test_repeated_user_data_hit_reuses_rendered_payload_within_ttl(monkeypatch, tmp_path):
    client, database_url, call_counter = load_client(monkeypatch, tmp_path)
    create_record(database_url)

    first = client.get("/seed/seed-123/user-data")
    second = client.get("/seed/seed-123/user-data")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text == second.text
    assert call_counter["count"] == 1


def test_expired_token_returns_410(monkeypatch, tmp_path):
    client, database_url, _ = load_client(monkeypatch, tmp_path)
    create_record(database_url, expires_at=utc_now() - timedelta(minutes=1))

    response = client.get("/seed/seed-123/user-data")

    assert response.status_code == 410
