"""Application factory.

Single origin (ADR-0001): this one FastAPI app serves both the API and the built
Vue bundle from ``dist/``. There is no CORS configuration because there is no
cross-origin request to configure.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import load_settings

#: The built Vue bundle. Absent until the frontend has been built, which is why
#: the mount is conditional rather than assumed.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    """Build the application, or refuse to boot.

    Loads settings first, so a production environment missing ``ADMIN_PASSWORD``
    fails here rather than at first request (ADR-0005).
    """
    settings = load_settings(os.environ if env is None else env)

    app = FastAPI(title="Hardware Hub")
    app.state.settings = settings

    # Single origin (ADR-0001): the same app serves the API and the bundle, so
    # there is no CORS middleware to configure. Mounted last, at the root, so it
    # never shadows an API route.
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend"
        )

    return app
