"""Environment-backed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PITWALL_",
        extra="ignore",
    )

    fixture_path: Path = Path("data/samples/demo_race.json")
    knowledge_db: Path = Path("data/cache/knowledge.db")
    knowledge_path: Path = Path("knowledge/strategy-principles.md")
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        """Accept a comma-separated environment value."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one immutable configuration instance per process."""
    return Settings()
