"""Application factory.

Single origin (ADR-0001): this one FastAPI app serves both the API and the built
Vue bundle from ``dist/``. There is no CORS configuration because there is no
cross-origin request to configure.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import load_settings
from app.storage import create_engine_for, create_schema, load_items, new_session

#: The built Vue bundle. Absent until the frontend has been built, which is why
#: the mount is conditional rather than assumed.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    """Build the application, or refuse to boot.

    Loads settings first, so a production environment missing ``ADMIN_PASSWORD``
    fails here rather than at first request (ADR-0005).
    """
    settings = load_settings(os.environ if env is None else env)

    # Under uvicorn the root logger has no handler, so application logs vanish
    # even though they are emitted. `caplog` captures propagated records, so tests
    # pass either way — this is what makes the boot-seed line visible in a real
    # deployment. `force=False` leaves an already-configured host alone.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s"
    )

    app = FastAPI(title="Hardware Hub")
    app.state.settings = settings

    # Once per process, not once per request (see app/storage.py).
    engine = create_engine_for(settings.database_url)
    create_schema(engine)
    app.state.engine = engine

    # Deploy shim, guarded by emptiness: a fresh volume gets the seed, a database
    # with anything in it is left alone. Imported here rather than at module level
    # so `app` does not depend on `scripts` just to be importable. See BACKLOG.md.
    from scripts.seed import seed_if_empty

    seed_if_empty(engine)

    @app.get("/api/hardware")
    def list_hardware() -> list[dict[str, Any]]:
        """The whole inventory. Eleven rows does not need pagination."""
        with new_session(engine) as session:
            return [asdict(item) for item in load_items(session)]

    # Single origin (ADR-0001): the same app serves the API and the bundle, so
    # there is no CORS middleware to configure. Mounted last, at the root, so it
    # never shadows an API route.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend"
        )

    return app
