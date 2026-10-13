"""Optional integration point for an operator-managed Kali MCP endpoint."""

import os

import httpx

KALI_MCP_URL = os.getenv("KALI_MCP_URL", "").rstrip("/")


def health() -> dict:
    if not KALI_MCP_URL:
        return {"status": "disabled", "message": "KALI_MCP_URL não configurada"}
    try:
        response = httpx.get(f"{KALI_MCP_URL}/health", timeout=3, follow_redirects=False)
        if response.status_code >= 400:
            return {"status": "unhealthy", "http_status": response.status_code}
        return {"status": "ready", "endpoint": KALI_MCP_URL}
    except httpx.HTTPError:
        return {"status": "unreachable", "endpoint": KALI_MCP_URL}
