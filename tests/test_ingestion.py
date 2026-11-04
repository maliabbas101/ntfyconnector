from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.ingestion import Base, Source, RawEvent, get_db, token_digest

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)

def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = lambda: Session()
    with Session() as db:
        db.add(Source(id="source-a", tenant_id=str(uuid4()), token_hash=token_digest("secret-a"), enabled=True))
        db.add(Source(id="source-b", tenant_id=str(uuid4()), token_hash=token_digest("secret-b"), enabled=True))
        db.commit()

def teardown_function():
    app.dependency_overrides.clear()

SIGNAL = "BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082"

def test_authentication_and_tenant_isolation():
    client = TestClient(app)
    payload = {"external_id": "message-1", "text": SIGNAL}
    assert client.post("/v1/ingest/sources/source-a", json=payload).status_code == 401
    assert client.post("/v1/ingest/sources/source-a", json=payload, headers={"Authorization": "Bearer secret-b"}).status_code == 401
    r = client.post("/v1/ingest/sources/source-a", json=payload, headers={"Authorization": "Bearer secret-a"})
    assert r.status_code == 202
    assert r.json()["status"] == "VALIDATED"
    assert r.json()["execution_enabled"] is False
    with Session() as db:
        record = db.scalar(select(RawEvent))
        assert record.source_id == "source-a"
        assert record.tenant_id == db.get(Source, "source-a").tenant_id

def test_deduplication_and_rejection():
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret-a"}
    path = "/v1/ingest/sources/source-a"
    payload = {"external_id": "same", "text": SIGNAL}
    first = client.post(path, json=payload, headers=headers).json()
    second = client.post(path, json=payload, headers=headers).json()
    assert first["event_id"] == second["event_id"]
    assert second["duplicate"] is True
    rejected = client.post(path, json={"external_id": "bad", "text": "hello"}, headers=headers).json()
    assert rejected["status"] == "REJECTED"
    with Session() as db:
        assert len(db.scalars(select(RawEvent)).all()) == 2


def test_tenant_scoped_ingestion_requires_matching_source_and_token():
    client = TestClient(app)
    with Session() as db:
        tenant_a = db.get(Source, "source-a").tenant_id
        tenant_b = db.get(Source, "source-b").tenant_id
    payload = {"external_id": "tenant-scoped-1", "text": SIGNAL}
    url_a = f"/v1/ingest/tenants/{tenant_a}/sources/source-a"
    url_wrong = f"/v1/ingest/tenants/{tenant_b}/sources/source-a"
    headers = {"Authorization": "Bearer secret-a"}
    assert client.post(url_a, json=payload).status_code == 401
    assert client.post(url_wrong, json=payload, headers=headers).status_code == 401
    assert client.post(url_a, json=payload,
                       headers={"Authorization": "Bearer secret-b"}).status_code == 401
    success = client.post(url_a, json=payload, headers=headers)
    assert success.status_code == 202
    assert success.json()["status"] == "VALIDATED"
    repeat = client.post(url_a, json=payload, headers=headers)
    assert repeat.json()["duplicate"] is True
    assert repeat.json()["event_id"] == success.json()["event_id"]
    with Session() as db:
        event = db.scalar(select(RawEvent).where(
            RawEvent.external_id == "tenant-scoped-1"))
        assert event.tenant_id == tenant_a


def test_tenant_scoped_ingestion_rejects_malformed_tenant_identifier():
    client = TestClient(app)
    result = client.post(
        "/v1/ingest/tenants/not-a-uuid/sources/source-a",
        headers={"Authorization": "Bearer secret-a"},
        json={"external_id": "x", "text": SIGNAL})
    assert result.status_code == 404
