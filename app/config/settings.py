from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_id: int = Field(..., alias="ADMIN_ID")

    # Comma-separated Gemini keys (legacy env name OPENAI_API_KEY)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    gemini_api_keys: str = Field(default="", alias="GEMINI_API_KEYS")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    database_url: str = Field(
        default="postgresql+asyncpg://tempo:tempo@localhost:5433/tempo",
        alias="DATABASE_URL",
    )
    postgres_user: str = Field(default="tempo", alias="POSTGRES_USER")
    postgres_password: str = Field(default="tempo", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="tempo", alias="POSTGRES_DB")

    timezone: str = Field(default="Europe/Moscow", alias="TIMEZONE")

    # Profile defaults (legacy DB columns)
    height_cm: int = Field(default=178, alias="HEIGHT_CM")
    weight_goal_min_kg: float = Field(default=80.0, alias="WEIGHT_GOAL_MIN_KG")
    weight_goal_max_kg: float = Field(default=85.0, alias="WEIGHT_GOAL_MAX_KG")

    wake_time: str = Field(default="06:30", alias="WAKE_TIME")
    sleep_time: str = Field(default="22:30", alias="SLEEP_TIME")

    push_start: str = Field(default="06:30", alias="PUSH_START")
    push_end: str = Field(default="22:00", alias="PUSH_END")

    motivation_time: str = Field(default="06:30", alias="MOTIVATION_TIME")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    logs_dir: Path = Field(default=BASE_DIR / "logs")
    backups_dir: Path = Field(default=BASE_DIR / "backups")
    assets_dir: Path = Field(default=BASE_DIR / "assets")

    @field_validator("admin_id", mode="before")
    @classmethod
    def _parse_admin(cls, value: object) -> int:
        return int(str(value).strip())

    def gemini_keys(self) -> list[str]:
        raw = self.gemini_api_keys or self.openai_api_key
        return [k.strip() for k in raw.replace(";", ",").split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
