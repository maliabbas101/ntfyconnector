"""Authenticated durable signal intake. No trade execution."""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from app.parser import parse_signal

class Base(DeclarativeBase):
    pass

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(String(8192), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def make_engine():
    url = os.getenv("DATABASE_URL", "sqlite:///./ntfyconnector.db")
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite:") else {}, pool_pre_ping=True)

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as session:
        yield session

class IncomingEvent(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=8192)

router = APIRouter(prefix="/v1/ingest", tags=["ingestion"])

@router.post("/sources/{source_id}", status_code=status.HTTP_202_ACCEPTED)
def ingest(source_id: str, body: IncomingEvent, authorization: str | None = Header(default=None), db=Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid source credentials")
    token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Invalid source credentials")
    source = db.get(Source, source_id)
    if source is None or not source.enabled or not hmac.compare_digest(source.token_hash, token_digest(token)):
        raise HTTPException(status_code=401, detail="Invalid source credentials")
    existing = db.scalar(select(RawEvent).where(RawEvent.source_id == source.id, RawEvent.external_id == body.external_id))
    if existing:
        return {"event_id": existing.id, "status": existing.status, "duplicate": True, "execution_enabled": False}
    try:
        parse_signal(body.text)
        parse_status = "VALIDATED"
    except ValueError:
        parse_status = "REJECTED"
    event = RawEvent(id=str(uuid4()), tenant_id=source.tenant_id, source_id=source.id,
                     external_id=body.external_id, text=body.text, status=parse_status,
                     received_at=datetime.now(timezone.utc))
    db.add(event)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        # A concurrent request may have inserted the same external ID.
        existing = db.scalar(select(RawEvent).where(RawEvent.source_id == source.id, RawEvent.external_id == body.external_id))
        if existing:
            return {"event_id": existing.id, "status": existing.status, "duplicate": True, "execution_enabled": False}
        raise
    return {"event_id": event.id, "status": event.status, "duplicate": False, "execution_enabled": False}
