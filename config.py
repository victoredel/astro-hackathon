"""
Shared application configuration loaded from environment variables.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # NOAA
    noaa_base_url: str = "https://services.swpc.noaa.gov/json/rtsw"

    # NASA
    nasa_api_key: str = "DEMO_KEY"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/solar.db"

    # Prediction
    prediction_horizon_mins: int = 30
    sequence_len: int = 60  # number of 1-min samples for model input
    ingest_interval_secs: int = 60

    # API
    api_base_url: str = "http://localhost:8000"

    # Model
    model_checkpoint: str = "checkpoints/solar_lora"
    use_real_surya: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
