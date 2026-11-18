"""Configuração isolada da geração editorial; nunca expõe a chave em repr/logs."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.settings import RAIZ


class NewsGenerationError(RuntimeError):
    """Erro operacional sanitizado, seguro para o relatório do job."""


class NewsWriterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env", env_file_encoding="utf-8", extra="ignore",
        populate_by_name=True, hide_input_in_errors=True,
    )

    enabled: bool = Field(default=False, validation_alias="NEWS_GENERATION_ENABLED")
    api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY", repr=False)
    api_key_file: Path | None = Field(default=None, validation_alias="OPENAI_API_KEY_FILE", repr=False)
    model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=100, validation_alias="OPENAI_NEWS_MODEL")
    auto_publish: bool = Field(default=False, validation_alias="NEWS_AUTO_PUBLISH")
    batch_size: int = Field(default=50, ge=1, le=100, validation_alias="NEWS_BATCH_SIZE")
    max_batches: int = Field(default=10, ge=1, le=50, validation_alias="NEWS_MAX_BATCHES")
    bootstrap_days: int = Field(default=7, ge=1, le=90, validation_alias="NEWS_BOOTSTRAP_DAYS")
    timeout_seconds: int = Field(default=60, ge=5, le=120, validation_alias="OPENAI_NEWS_TIMEOUT_SECONDS")
    max_output_tokens: int = Field(default=4096, ge=500, le=8000, validation_alias="OPENAI_NEWS_MAX_OUTPUT_TOKENS")

    @field_validator("api_key_file", mode="before")
    @classmethod
    def empty_path(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    def require_api_key(self) -> str:
        if self.api_key and self.api_key.get_secret_value().strip():
            key = self.api_key.get_secret_value().strip()
        elif self.api_key_file:
            try:
                with self.api_key_file.open(encoding="utf-8") as stream:
                    key = stream.read(4097).strip()
            except (OSError, UnicodeError):
                raise NewsGenerationError("Não foi possível ler OPENAI_API_KEY_FILE.") from None
        else:
            raise NewsGenerationError("Configure OPENAI_API_KEY ou OPENAI_API_KEY_FILE para gerar notícias.")
        if not key or len(key) > 4096 or any(char.isspace() for char in key):
            raise NewsGenerationError("A chave OpenAI está vazia ou possui formato inválido.")
        return key
