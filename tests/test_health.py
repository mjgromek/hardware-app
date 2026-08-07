"""The health endpoint — the deliberate second exception to ADR-0006.

`GET /` is open because nobody could log in otherwise; `GET /api/health` is open
because its caller is a load balancer, and a health check behind a session would
report every deploy as down. It touches nothing — no database, no session — so it can
answer while the volume is broken, which is exactly when somebody is asking.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/api/health")

    assert response.status_code == 200, (
        "the health endpoint answers everyone — a check behind a session reports "
        f"every deploy as down. Got {response.status_code}: {response.text}"
    )
    assert response.json() == {"status": "ok"}, (
        f"and it answers exactly {{'status': 'ok'}}; got {response.text}"
    )
    assert "set-cookie" not in response.headers, (
        "a health check must not mint sessions or touch state"
    )
