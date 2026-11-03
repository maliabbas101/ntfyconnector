from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.tenant_context import set_tenant

def test_reject_non_postgres_backend():
    with Session(create_engine("sqlite://")) as session:
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            set_tenant(session, str(uuid4()))

def test_reject_invalid_tenant_id():
    with Session(create_engine("sqlite://")) as session:
        with pytest.raises(ValueError):
            set_tenant(session, "not-a-uuid")
