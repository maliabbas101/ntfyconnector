from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ingestion import Base, Source, token_digest
from app import provision_source


def test_provision_stores_hash_only(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(provision_source, "SessionLocal", sessionmaker(bind=engine))
    tenant_id = str(uuid4())
    source_id, token = provision_source.provision(tenant_id)
    assert source_id != tenant_id
    assert len(token) >= 48
    with sessionmaker(bind=engine)() as db:
        source = db.get(Source, source_id)
        assert source.tenant_id == tenant_id
        assert source.token_hash == token_digest(token)
        assert token not in source.token_hash


def test_reject_invalid_tenant_uuid():
    with pytest.raises(ValueError):
        provision_source.provision("not-a-uuid")
