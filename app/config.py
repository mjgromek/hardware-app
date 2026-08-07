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
    # `@booksy.com`, not `admin@localhost`. Every account in the project is now on the
    # company domain, which is what lets creation-time domain validation apply with no
    # exemption for the bootstrap admin. Left as `admin@localhost`, a fresh local
    # database would bootstrap the one account that validation would reject.
    "ADMIN_EMAIL": "admin@booksy.com",
    "ADMIN_PASSWORD": "admin",
    # Not a secret by design: these are the credentials the README publishes, on a
    # `user`-role account that every admin route refuses.
    "DEMO_EMAIL": "demo@booksy.com",
    "DEMO_PASSWORD": "hardware-hub-demo",
    "DATABASE_URL": "sqlite:///./hardware_hub.db",
}


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build ``Settings`` from an environment mapping, or refuse.

    ``ENVIRONMENT`` selects the regime and is the only variable read before the
    guards run. Production is strict: ``SECRET_KEY`` and ``ADMIN_PASSWORD`` must
    both be present and non-empty. Anything else — including an unset
    ``ENVIRONMENT`` — is permissive and falls back to development defaults
    (ADR-0005).
    """
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
