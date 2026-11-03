"""Regression coverage for ingestion database failures."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.ingestion import Base, Source, RawEvent, get_db, token_digest

SIGNAL = "BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082"

@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(Source(
            id="source-test", tenant_id=str(uuid4()),
            token_hash=token_digest("secret"), enabled=True,
        ))
        db.commit()
    app.dependency_overrides[get_db] = lambda: Session()
    yield engine, Session
    app.dependency_overrides.clear()
    engine.dispose()

def test_unrelated_integrity_error_is_not_swallowed(database):
    engine, Session = database
    def reject_insert(mapper, connection, target):
        raise RuntimeError("simulated database failure")

    event.listen(RawEvent, "before_insert", reject_insert)
    try:
        client = TestClient(app, raise_server_exceptions=True)
        with pytest.raises(RuntimeError, match="simulated database failure"):
            client.post(
                "/v1/ingest/sources/source-test",
                json={"external_id": "event-1", "text": SIGNAL},
                headers={"Authorization": "Bearer secret"},
            )
        with Session() as db:
            assert db.scalar(select(RawEvent)) is None
    finally:
        event.remove(RawEvent, "before_insert", reject_insert)
