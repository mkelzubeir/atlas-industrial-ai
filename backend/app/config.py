"""Application configuration, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings.

    Every value has a development-friendly default so the service starts with no
    configuration at all, but anything security-relevant can be locked down via
    the environment.
    """

    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"), env_prefix="ATLAS_", extra="ignore"
    )

    # Where the SQLite file lives. Overridden to an in-memory DB by the tests.
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'atlas.db'}"

    # Shared secret that the ElevenLabs webhook tools must present in the
    # `X-Atlas-Api-Key` header. When empty, auth is disabled (local development).
    api_key: str = ""

    # Demo-only endpoints (reset, fault injection) are refused unless this is on.
    # It exists so that the same image cannot be deployed "as production" with a
    # database-wiping endpoint quietly exposed.
    demo_mode: bool = True

    # CORS origins allowed to call the API directly from a browser.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    log_level: str = "INFO"

    # Seed the database at startup if it is empty. Off by default so running
    # locally never surprises you by writing data; on in the container image,
    # where the filesystem is ephemeral and each boot should give the demo a
    # clean, known state.
    seed_on_startup: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
