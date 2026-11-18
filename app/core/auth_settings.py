"""Configuracao exclusiva da autenticacao do Jornalzinho."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


RAIZ = Path(__file__).resolve().parents[2]


class AuthSettings(BaseSettings):
    """Valores de seguranca; nenhum segredo de JWT possui valor padrao."""

    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    JWT_SECRET_KEY: SecretStr = Field(repr=False)
    APP_ORIGIN: str
    APP_ROOT_PATH: str = ""
    SESSION_COOKIE_SECURE: bool = True

    JWT_ISSUER: str = "jornalzinho"
    JWT_AUDIENCE: str = "jornalzinho-api"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def jwt_secret_longo(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY deve ter ao menos 32 caracteres")
        return value

    @field_validator("APP_ORIGIN")
    @classmethod
    def origem_exata(cls, value: str) -> str:
        origin = value.strip()
        try:
            parsed = urlsplit(origin)
            port = parsed.port
        except ValueError as error:
            raise ValueError("APP_ORIGIN deve conter porta valida") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("APP_ORIGIN deve conter scheme e host, sem caminho")
        return origin

    @field_validator("APP_ROOT_PATH")
    @classmethod
    def root_path_valido(cls, value: str) -> str:
        path = value.strip()
        if path in {"", "/"}:
            return ""
        if (
            not path.startswith("/")
            or path.endswith("/")
            or "//" in path
            or "\\" in path
            or "?" in path
            or "#" in path
            or any(part in {".", ".."} for part in path.split("/"))
        ):
            raise ValueError("APP_ROOT_PATH deve ser vazio ou um caminho absoluto sem barra final")
        return path

    @field_validator("SESSION_COOKIE_SECURE")
    @classmethod
    def cookie_inseguro_so_loopback_http(cls, value: bool, info: ValidationInfo) -> bool:
        if value:
            return value
        origin = info.data.get("APP_ORIGIN")
        parsed = urlsplit(origin) if isinstance(origin, str) else None
        if (
            parsed is None
            or parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        ):
            raise ValueError("SESSION_COOKIE_SECURE=false so e permitido para APP_ORIGIN HTTP de loopback")
        return value

    @property
    def refresh_cookie_path(self) -> str:
        return f"{self.APP_ROOT_PATH}/api/v1/auth"


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
