"""Configuration: secrets from the root .env, settings from config.toml, validated at startup."""

import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"
ENV_PATH = ROOT / ".env"
JOURNAL_PATH = ROOT / "journal.db"
EXPORT_DIR = ROOT / "web" / "public" / "data"
REPORTS_DIR = ROOT / "reports"

# Raised while reading config.toml and .env: retrying cannot help.
CONFIG_ERRORS = (ValidationError, tomllib.TOMLDecodeError, OSError, RuntimeError)

PERCENT = 100.0
BPS_PER_UNIT = 10_000.0

Symbol = Annotated[str, StringConstraints(pattern=r"^[A-Z]{1,5}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketConfig(StrictModel):
    symbols: list[Symbol] = Field(min_length=1, max_length=20)
    feed: str = Field(pattern=r"^(iex|sip)$")
    history_days: int = Field(ge=7, le=365)
    max_bar_age_hours: float = Field(gt=0, le=48)
    max_gap_ratio: float = Field(ge=0, le=1)


class ForecastConfig(StrictModel):
    model: str = Field(min_length=3, max_length=100)
    context_length: int = Field(ge=64, le=4000)
    horizon: int = Field(ge=1, le=96)
    signal_strong: float = Field(gt=0)
    max_attempts: int = Field(ge=1, le=10)
    retry_delay_s: float = Field(gt=0, le=60)
    event_times: list[AwareDatetime] = Field(max_length=200)


class MacroConfig(StrictModel):
    series: dict[str, str] = Field(min_length=1, max_length=20)
    history_days: int = Field(ge=30, le=730)
    timeout_s: int = Field(ge=1, le=300)
    max_attempts: int = Field(ge=1, le=10)
    retry_delay_s: float = Field(gt=0, le=60)


class LlmConfig(StrictModel):
    model: str = Field(min_length=3, max_length=100)
    temperature: float = Field(ge=0, le=1)
    timeout_s: int = Field(ge=1, le=300)
    max_attempts: int = Field(ge=1, le=10)
    retry_delay_s: float = Field(gt=0, le=60)


class RiskConfig(StrictModel):
    enabled: bool
    allocated_capital: float = Field(gt=0)
    capital_floor: float = Field(ge=0)
    max_daily_loss_pct: float = Field(gt=0, le=100)
    max_position_pct: float = Field(gt=0, le=100)
    max_total_exposure_pct: float = Field(gt=0, le=100)
    min_order_pct: float = Field(gt=0, le=100)
    max_orders_per_cycle: int = Field(ge=1, le=50)
    min_signal_strength: float = Field(ge=0, le=1)
    max_uncertainty: float = Field(gt=0, le=1)
    forecast_guard: bool

    @model_validator(mode="after")
    def check_consistency(self) -> "RiskConfig":
        if self.capital_floor >= self.allocated_capital:
            raise ValueError("capital_floor must be below allocated_capital")
        if self.max_position_pct > self.max_total_exposure_pct:
            raise ValueError("max_position_pct must not exceed max_total_exposure_pct")
        return self


class BrokerConfig(StrictModel):
    timeout_s: int = Field(ge=1, le=300)
    max_attempts: int = Field(ge=1, le=10)
    retry_delay_s: float = Field(gt=0, le=60)
    fill_check_attempts: int = Field(ge=1, le=20)
    fill_check_interval_s: float = Field(gt=0, le=30)


class BacktestConfig(StrictModel):
    history_days: int = Field(ge=30, le=730)
    stride_bars: int = Field(ge=1, le=100)
    start: AwareDatetime
    compare_models: list[str]
    rule_signal_threshold: float = Field(gt=0, le=1)
    cost_bps: float = Field(ge=0, le=100)


class Config(StrictModel):
    market: MarketConfig
    forecast: ForecastConfig
    macro: MacroConfig
    llm: LlmConfig
    risk: RiskConfig
    broker: BrokerConfig
    backtest: BacktestConfig


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    alpaca_api_key: SecretStr = Field(min_length=1)
    alpaca_secret_key: SecretStr = Field(min_length=1)
    mistral_api_key: SecretStr = Field(min_length=1)
    fred_api_key: SecretStr = Field(min_length=1)


def load_config(path: Path = CONFIG_PATH) -> Config:
    with path.open("rb") as file:
        return Config.model_validate(tomllib.load(file))


def load_secrets() -> Secrets:
    return Secrets()
