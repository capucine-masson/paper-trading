"""Configuration: secrets from the root .env, settings from config.toml, validated at startup."""

import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"
ENV_PATH = ROOT / ".env"

Symbol = Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,5}$")]


class MarketConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[Symbol] = Field(min_length=1, max_length=20)
    feed: str = Field(pattern=r"^(iex|sip)$")
    history_days: int = Field(ge=7, le=365)
    max_bar_age_hours: float = Field(gt=0, le=48)
    max_gap_ratio: float = Field(ge=0, le=1)


class ForecastConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=3, max_length=100)
    context_length: int = Field(ge=64, le=4000)
    horizon: int = Field(ge=1, le=96)


class LlmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=3, max_length=100)
    temperature: float = Field(ge=0, le=1)
    timeout_s: int = Field(ge=1, le=300)
    max_attempts: int = Field(ge=1, le=10)
    retry_delay_s: float = Field(gt=0, le=60)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: MarketConfig
    forecast: ForecastConfig
    llm: LlmConfig


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    alpaca_api_key: SecretStr = Field(min_length=1)
    alpaca_secret_key: SecretStr = Field(min_length=1)
    mistral_api_key: SecretStr = Field(min_length=1)


def load_config(path: Path = CONFIG_PATH) -> Config:
    with path.open("rb") as file:
        return Config.model_validate(tomllib.load(file))


def load_secrets() -> Secrets:
    return Secrets()
