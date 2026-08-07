"""Application settings and the boot-time guards over them.

Standard library only, deliberately: the boot check must be exercisable without
importing the web framework or touching a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ConfigurationError(RuntimeError):
    """The app refuses to boot rather than come up with an invariant already broken."""


@dataclass(frozen=True)
class Settings:
    environment: str
    secret_key: str
    admin_email: str
    admin_password: str
    #: The read-only account whose credentials the README publishes. Created at boot on
    #: a database with no accounts, so a replaced volume cannot leave the documented
    #: credentials pointing at nothing (ADR-0005).
    demo_email: str
    demo_password: str
    database_url: str


PRODUCTION = "production"

#: Required in production, and the order they are reported in.
REQUIRED_IN_PRODUCTION = ("SECRET_KEY", "ADMIN_PASSWORD")

#: Development-only fallbacks, so a fresh clone runs with no environment set.
DEVELOPMENT_DEFAULTS = {
    "SECRET_KEY": "dev-secret-key-not-for-production",
    # On the company domain, or a fresh database bootstraps the one account that
    # creation-time domain validation would reject (ADR-0019).
    "ADMIN_EMAIL": "admin@booksy.com",
    "ADMIN_PASSWORD": "admin",
    # Not a secret by design: the README publishes these, on a user-role account.
    "DEMO_EMAIL": "demo@booksy.com",
    "DEMO_PASSWORD": "hardware-hub-demo",
    "DATABASE_URL": "sqlite:///./hardware_hub.db",
}


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build ``Settings`` or refuse. Production is strict; anything else falls back
    to development defaults (ADR-0005)."""
    environment = env.get("ENVIRONMENT") or "development"

    if environment == PRODUCTION:
        # An empty string is not a credential. Accepting one would bootstrap an
        # admin nobody can log in as — the zero-admin state by another route.
        missing = [key for key in REQUIRED_IN_PRODUCTION if not env.get(key)]
        if missing:
            raise ConfigurationError(
                f"refusing to boot in production: {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} unset or empty"
            )

    def value(key: str) -> str:
        return env.get(key) or DEVELOPMENT_DEFAULTS[key]

    return Settings(
        environment=environment,
        secret_key=value("SECRET_KEY"),
        admin_email=value("ADMIN_EMAIL"),
        admin_password=value("ADMIN_PASSWORD"),
        demo_email=value("DEMO_EMAIL"),
        demo_password=value("DEMO_PASSWORD"),
        database_url=value("DATABASE_URL"),
    )
