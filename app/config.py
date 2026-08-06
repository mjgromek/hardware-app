"""Application settings and the boot-time guards over them.

Standard library only, deliberately: the boot check must be exercisable without
importing the web framework or touching a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ConfigurationError(RuntimeError):
    """Raised when the environment cannot support a safe boot.

    The application refuses to start rather than coming up in a state where an
    invariant is already violated (ADR-0005).
    """


@dataclass(frozen=True)
class Settings:
    environment: str
    secret_key: str
    admin_email: str
    admin_password: str
    database_url: str


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build ``Settings`` from an environment mapping, or refuse.

    In production a missing ``ADMIN_PASSWORD`` or ``SECRET_KEY`` must raise
    ``ConfigurationError``. Booting without an admin credential reaches the
    zero-admin state the guard layer exists to prevent (ADR-0005).
    """
    raise NotImplementedError("load_settings is not implemented yet")
