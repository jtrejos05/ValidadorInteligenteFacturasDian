"""Runtime configuration (env vars, prefixed with DIAN_)."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIAN_", env_file=".env", extra="ignore")

    # "mock" runs fully offline and deterministic (CI, demos without an API key).
    # "anthropic" calls Claude. "auto" picks anthropic when credentials exist.
    llm_provider: str = "auto"
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"  # classification/extraction workloads do well at low effort
    llm_timeout_s: float = 60.0

    # USD per 1M tokens, used for cost tracking in traces.
    price_input_per_mtok: float = 4.0
    price_output_per_mtok: float = 20.0

    # Postgres (e.g. Neon via the Vercel Marketplace). Read without the DIAN_ prefix
    # because the integration injects these names. When unset, SQLite is used.
    database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL")
    )
    # Serverless filesystems are read-only except /tmp.
    db_path: Path = (
        Path("/tmp/validator.db") if os.environ.get("VERCEL") else Path("data/validator.db")
    )
    # Technical keys (clave técnica) per numbering resolution. In production these
    # come from the DIAN enablement portal; here they live in a JSON catalog.
    resolutions_path: Path = Path(__file__).parent / "data" / "resolutions.json"

    # Tolerance for rounding differences in COP amounts.
    amount_tolerance: float = 1.0

    # Business-case assumptions shown on the metrics dashboard (editable).
    manual_minutes_per_invoice: float = 6.0
    analyst_cost_cop_per_hour: float = 35000.0
    max_upload_mb: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
