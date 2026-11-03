"""Standalone ntfy subscriber that forwards messages to authenticated ingestion.

Run on a trusted machine. Does not connect to MetaTrader or place orders.
"""
import json
import logging
import os
import time
from urllib.parse import quote, urlparse

import httpx
from pydantic import BaseModel, Field
from app.ntfy_cursor import CursorStore
from app.ntfy_delivery import forward_event, PermanentDeliveryError
from app.ntfy_auth import subscription_headers

log = logging.getLogger(__name__)

class NtfyMessage(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    event: str
    topic: str
    message: str = Field(min_length=1, max_length=8192)

def normalize_ntfy_line(line: str, expected_topic: str) -> dict | None:
    """Only forward real messages from the configured topic."""
    try:
        raw = json.loads(line)
        if not isinstance(raw, dict) or raw.get("event") != "message":
            return None
        event = NtfyMessage.model_validate(raw)
        if event.topic != expected_topic:
            return None
        return {"external_id": event.id, "text": event.message}
    except (ValueError, TypeError):
        return None

def require_https(url: str, *, allow_local_http: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password:
        return url.rstrip("/")
    if allow_local_http and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        return url.rstrip("/")
    raise ValueError("HTTPS is required (HTTP permitted only for localhost development)")

def run_bridge() -> None:
    topic = os.environ["NTFY_TOPIC"]
    source_id = os.environ["SOURCE_ID"]
    token = os.environ["SOURCE_TOKEN"]
    ntfy_url = require_https(os.getenv("NTFY_URL", "https://ntfy.sh"))
    api_url = require_https(os.environ["API_URL"], allow_local_http=os.getenv("ALLOW_LOCAL_HTTP") == "1")
    if not topic or "/" in topic or not source_id or not token:
        raise ValueError("Invalid bridge configuration")
    subscribe = f"{ntfy_url}/{quote(topic, safe='')}/json"
    destination = f"{api_url}/v1/ingest/sources/{quote(source_id, safe='')}"
    # The cursor advances only after a successful API response. Replayed events
    # are harmless because ingestion deduplicates by source and external ID.
    with CursorStore(os.getenv("NTFY_CURSOR_DB", "./ntfy-bridge-cursor.sqlite"), topic) as cursor:
        with httpx.Client(timeout=httpx.Timeout(30.0, read=90.0), follow_redirects=False) as client:
            while True:
                try:
                    since = cursor.get() or "all"
                    with client.stream("GET", subscribe, params={"since": since},
                                       headers=subscription_headers()) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            payload = normalize_ntfy_line(line, topic)
                            if payload is None:
                                continue
                            forward_event(client, destination, token, payload, cursor)
                            log.info("Acknowledged ntfy event id=%s", payload["external_id"])
                except PermanentDeliveryError:
                    log.error("Permanent ingestion failure; stopping bridge without acknowledging event")
                    raise
                except (httpx.HTTPError, OSError) as exc:
                    log.warning("Bridge connection error: %s; retrying", type(exc).__name__)
                    time.sleep(5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bridge()
