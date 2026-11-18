"""Configuracao PostgreSQL, no mesmo padrao de app/core do car_app."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


RAIZ = Path(__file__).resolve().parents[2]
SSLMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]


class Setting(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    POSTGRES_HOST: str = Field(min_length=1, repr=False)
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_DB: str = Field(default="jornalzinho", min_length=1)
    POSTGRES_USER: str = Field(min_length=1, repr=False)
    POSTGRES_PASSWORD: SecretStr = Field(repr=False)
    POSTGRES_SSLMODE: SSLMode = "require"
    POSTGRES_SSLROOTCERT: str | None = None
    POSTGRES_CONNECT_TIMEOUT: int = Field(default=10, ge=1, le=60)

    @field_validator("POSTGRES_HOST", "POSTGRES_USER", mode="before")
    @classmethod
    def limpar_identificador(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("POSTGRES_DB", mode="before")
    @classmethod
    def nome_do_banco(cls, value: object) -> object:
        return (value.strip() or "jornalzinho") if isinstance(value, str) else value

    @field_validator("POSTGRES_SSLMODE", mode="before")
    @classmethod
    def modo_tls(cls, value: object) -> object:
        return (value.strip().lower() or "require") if isinstance(value, str) else value

    @field_validator("POSTGRES_SSLROOTCERT", mode="before")
    @classmethod
    def certificado_opcional(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("POSTGRES_PASSWORD")
    @classmethod
    def senha_obrigatoria(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("POSTGRES_PASSWORD deve estar preenchida")
        return value

    @property
    def DATABASE_URL(self) -> URL:
        # URL.create preserva caracteres como @, %, # e / na senha.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @property
    def database_connect_args(self) -> dict[str, str | int]:
        args: dict[str, str | int] = {
            "sslmode": self.POSTGRES_SSLMODE,
            "connect_timeout": self.POSTGRES_CONNECT_TIMEOUT,
        }
        if self.POSTGRES_SSLROOTCERT:
            args["sslrootcert"] = self.POSTGRES_SSLROOTCERT
        return args
