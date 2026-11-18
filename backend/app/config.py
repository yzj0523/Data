"""Environment configuration with value-free validation errors."""

from pathlib import Path
from typing import Literal

from pydantic import (
    Field,
    HttpUrl,
    IPvAnyAddress,
    SecretStr,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    host: IPvAnyAddress = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
    database_path: Path = Path("data/ai_query.sqlite3")
    default_model_base_url: HttpUrl | None = None
    default_model_name: str | None = None
    default_model_api_key: SecretStr | None = Field(default=None, repr=False)
    model_encryption_key: SecretStr | None = Field(default=None, repr=False)
    question_max_length: int = Field(default=2000, ge=1, le=20000)
    query_max_rows: int = Field(default=200, ge=1, le=5000)
    query_timeout_seconds: float = Field(default=2, gt=0, le=60)
    model_timeout_seconds: float = Field(default=15, gt=0, le=180)

    @field_validator("database_path", mode="before")
    @classmethod
    def validate_database_path(cls, value: object) -> object:
        if isinstance(value, str) and (not value.strip() or "\x00" in value):
            raise ValueError("Expected a database file path")
        try:
            if Path(value).is_dir():
                raise ValueError("Expected a database file path")
        except (OSError, TypeError):
            raise ValueError("Expected a database file path") from None
        return value

    @field_validator(
        "default_model_base_url",
        "default_model_name",
        "default_model_api_key",
        mode="before",
    )
    @classmethod
    def normalize_optional_model_value(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class ConfigurationError(ValueError):
    """Contains field names only, never raw environment values."""

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        names = ", ".join(fields) if fields else "environment configuration"
        super().__init__(f"Invalid server configuration: {names}")


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        fields = sorted(
            {
                f"AI_{error['loc'][0].upper()}"
                for error in exc.errors(include_input=False, include_context=False)
                if error["loc"] and error["loc"][0] in Settings.model_fields
            }
        )
        raise ConfigurationError(fields) from None
    except (SettingsError, OSError, UnicodeError):
        raise ConfigurationError([]) from None
