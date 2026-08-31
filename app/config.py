"""Application configuration, loaded from environment / .env.

Secrets (the LinkedIn cookies) live only in the environment — never in the repo.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LinkedIn session — a single primary cookie (backward-compatible) …
    linkedin_li_at: str = ""
    linkedin_jsessionid: str = ""
    # … and/or a pool of throwaway-account cookies as a JSON array, e.g.
    #   [{"li_at":"AQ…","jsessionid":"\"ajax:123\""}, {"li_at":"…","jsessionid":"…"}]
    # The service rotates to the next cookie automatically when one is killed by LinkedIn.
    linkedin_cookies: str = ""

    # Networking
    outbound_proxy_url: str = ""

    # Server / behaviour
    api_key: str = ""
    linkedin_max_rpm: int = 8
    cache_ttl_seconds: int = 3600
    cors_origins: str = "*"
    log_level: str = "INFO"

    @property
    def csrf_token(self) -> str:
        """LinkedIn's CSRF token is the JSESSIONID value without surrounding quotes."""
        return self.linkedin_jsessionid.strip().strip('"')

    @property
    def has_session(self) -> bool:
        return bool(self.linkedin_li_at and self.linkedin_jsessionid)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]

    @property
    def proxies(self) -> str | None:
        return self.outbound_proxy_url or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
