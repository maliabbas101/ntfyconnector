"""Build authentication headers for a private ntfy subscription.

The token is sent only to the configured ntfy origin; redirects are disabled.
"""
import os

def subscription_headers(access_token: str | None = None) -> dict[str, str]:
    token = access_token if access_token is not None else os.getenv("NTFY_ACCESS_TOKEN")
    if token is None or token == "":
        return {}
    if not token.strip() or "\r" in token or "\n" in token:
        raise ValueError("Invalid NTFY_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {token}"}
