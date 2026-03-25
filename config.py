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

    # NASA DONKI
    donki_base_url: str = "https://api.nasa.gov/DONKI"
    donki_sync_interval_mins: int = 60   # how often to poll for new events
    donki_lookback_days: int = 7         # how many days back per DONKI request

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/solar.db"

    # Prediction — decouple AI from ingestion
    prediction_horizon_mins: int = 30
    sequence_len: int = 60
    ingest_interval_secs: int = 60
    enable_ai_inference: bool = False   # ← set True when model is ready

    # API
    api_base_url: str = "http://localhost:8000"

    # Model
    model_checkpoint: str = "checkpoints/solar_lora"
    use_real_surya: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
