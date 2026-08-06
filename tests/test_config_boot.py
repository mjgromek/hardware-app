"""Phase 0 — the boot-time guard over the admin credential (ADR-0005).

The seed creates admin #1 from ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD``. Booting
production without ``ADMIN_PASSWORD`` reaches the zero-admin state the guard layer
exists to prevent, so the app refuses to start rather than coming up with an
invariant already violated.

The environment is passed in as a mapping, never read from ``os.environ``, so these
tests need no monkeypatching and cannot leak state between each other.
"""

from __future__ import annotations

import pytest

from app.config import ConfigurationError, Settings, load_settings
from app.main import create_app

PRODUCTION_ENV: dict[str, str] = {
    "ENVIRONMENT": "production",
    "SECRET_KEY": "not-the-real-key",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "not-the-real-password",
    "DATABASE_URL": "sqlite:///./hardware_hub.db",
}


def _production_env_without(key: str) -> dict[str, str]:
    env = dict(PRODUCTION_ENV)
    env.pop(key)
    return env


def test_app_refuses_to_boot_without_admin_password() -> None:
    """The application factory fails at boot, not at first request.

    ``create_app`` loads settings before it builds anything, so a production
    deployment missing ``ADMIN_PASSWORD`` never reaches a servable state.
    """
    with pytest.raises(ConfigurationError):
        create_app(_production_env_without("ADMIN_PASSWORD"))


@pytest.mark.parametrize(
    ("description", "env"),
    [
        ("absent", _production_env_without("ADMIN_PASSWORD")),
        ("empty", {**PRODUCTION_ENV, "ADMIN_PASSWORD": ""}),
    ],
)
def test_load_settings_rejects_production_without_admin_password(
    description: str, env: dict[str, str]
) -> None:
    """A production environment with no usable admin credential is refused.

    An empty string is not a password. Accepting it would bootstrap an admin
    nobody can log in as, which is the zero-admin state by another route.
    """
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(env)

    assert "ADMIN_PASSWORD" in str(excinfo.value), (
        "the refusal must name the missing variable, or an operator cannot fix the "
        f"deploy from the log line alone; got {str(excinfo.value)!r}"
    )


def test_load_settings_rejects_production_without_secret_key() -> None:
    """The admin-password check is one of a pair; the secret key is refused the same way."""
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(_production_env_without("SECRET_KEY"))

    assert "SECRET_KEY" in str(excinfo.value), (
        f"the refusal must name the missing variable; got {str(excinfo.value)!r}"
    )


def test_load_settings_allows_non_production_without_admin_password() -> None:
    """Local development still boots with an empty environment.

    The guard is scoped to production (ADR-0005). Without this, an implementation
    that raises unconditionally would satisfy every other test in this file while
    making the app impossible to run.
    """
    settings = load_settings({"ENVIRONMENT": "development"})

    assert isinstance(settings, Settings)
    assert settings.environment == "development"


def test_load_settings_accepts_a_complete_production_environment() -> None:
    """A fully specified production environment loads, and carries its values through."""
    settings = load_settings(dict(PRODUCTION_ENV))

    assert settings.environment == "production"
    assert settings.admin_email == "admin@example.com"
    assert settings.admin_password == "not-the-real-password"
    assert settings.secret_key == "not-the-real-key"
