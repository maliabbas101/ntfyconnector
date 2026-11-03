"""Non-trading API: validates text, returns a dry-run result."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.parser import parse_signal

app = FastAPI(title="ntfyconnector", version="0.1.0")

class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8192)

@app.get("/health")
def health():
    return {"status": "ok", "execution_enabled": False}

@app.post("/v1/signals/validate")
def validate_signal(body: ParseRequest):
    try:
        signal = parse_signal(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "DRY_RUN", "execution_enabled": False, "signal": signal.model_dump(mode="json")}

from app.ingestion import router as ingestion_router
app.include_router(ingestion_router)

from app.agent_api import router as agent_router
app.include_router(agent_router)
