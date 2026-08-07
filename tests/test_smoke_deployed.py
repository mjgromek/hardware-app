"""The smoke check that runs against a *deployed* URL, not the local app.

`brainstorm.md` §3 listed `smoke_deployed_login_and_rent_flow` in Phase 3 and it was never
written. That omission is why a rollback went unnoticed: the live instance served a Phase 0
image — no authentication, the whole inventory readable anonymously, including the `notes`
and `history` ADR-0006 exists to keep off a public wire — and every one of the 152 local
tests passed throughout, because they test *source*, not the thing that is running.

**This is the only test in the project that can fail while the code is correct**, which is
precisely its job. Every assertion below is one the rolled-back build would have failed:

| Assertion | What the Phase 0 image did |
| --- | --- |
| anonymous `GET /api/hardware` → `401` | returned `200` with all items |
| `POST /api/login` accepts real credentials | `404` — the route did not exist |
| `GET /api/health` → `200` | `404` — the route did not exist |
| a signed-in caller can read the inventory | n/a, but proves the deploy is usable |

Skipped unless `SMOKE_URL` is set, so it never runs in the ordinary suite and never turns
a laptop's `pytest` red because the internet is unreachable. Run it as:

    SMOKE_URL=https://… SMOKE_EMAIL=admin@booksy.com SMOKE_PASSWORD=… \\
      .venv/bin/python -m pytest tests/test_smoke_deployed.py -v

`CLAUDE.md` makes a deploy incomplete until this passes against the live URL.
"""

from __future__ import annotations

import os

import pytest

try:  # httpx ships with the test client; it is the only HTTP client already present.
    import httpx
except ImportError:  # pragma: no cover - httpx is a dev dependency
    httpx = None

SMOKE_URL = os.environ.get("SMOKE_URL", "").rstrip("/")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "")
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")

pytestmark = pytest.mark.skipif(
    not SMOKE_URL or httpx is None,
    reason="deployed smoke check — set SMOKE_URL, SMOKE_EMAIL and SMOKE_PASSWORD to run",
)


@pytest.fixture(scope="module")
def client():
    # A generous timeout: this crosses the internet to a container that may be waking.
    with httpx.Client(base_url=SMOKE_URL, timeout=30.0, follow_redirects=False) as http:
        yield http


def test_smoke_deployed_login_and_rent_flow(client) -> None:
    """The deployed URL is serving a build with auth, health and a readable inventory.

    One test rather than four, deliberately. A rollback fails *all* of these at once, and
    four separate failures reporting one cause is noise at the moment somebody is trying
    to read a deploy log quickly. Each assertion names what its failure means.
    """
    anonymous = client.get("/api/hardware")
    assert anonymous.status_code == 401, (
        "ANONYMOUS READ: the deployed instance served the inventory without a session — "
        f"got {anonymous.status_code}. This is the ADR-0006 failure, and it is what a "
        "rolled-back pre-auth build looks like. Check which image is deployed before "
        f"anything else. Body: {anonymous.text[:200]}"
    )

    health = client.get("/api/health")
    assert health.status_code == 200, (
        f"HEALTH: GET /api/health returned {health.status_code}. A 404 here means the "
        "deployed build predates Phase 3 — the endpoint is not missing, the *build* is "
        "old."
    )

    signed_in = client.post(
        "/api/login", json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD}
    )
    assert signed_in.status_code == 200, (
        f"LOGIN: POST /api/login returned {signed_in.status_code} for {SMOKE_EMAIL}. A "
        "404 means the route does not exist in the deployed build; a 401 means the "
        "credentials are wrong or that account has been migrated or soft-deleted. "
        f"Body: {signed_in.text[:200]}"
    )

    inventory = client.get("/api/hardware")
    assert inventory.status_code == 200, (
        f"SIGNED-IN READ: the session from /api/login could not read the inventory; got "
        f"{inventory.status_code}. Auth answers but the deploy is not usable."
    )
    items = inventory.json()
    assert items, (
        "EMPTY INVENTORY: the deployed database has no hardware. Either the volume was "
        "replaced or the boot seed did not run — see the demo reset route in the README."
    )
