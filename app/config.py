"""Configuração local, sem integrações de repositório ou serviços externos."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Configuracao:
    modo: str
    repos_dir: Path | None
    mirrors_dir: Path | None
    repositorios: tuple[str, ...]
    github_token: str | None
    atualizar_remoto: bool
    intervalo_minutos: int
    arquivo_dados: Path
    webhook_secret: str | None = None

    def __str__(self) -> str:
        return "Configuracao(local=True, integracoes_externas=off)"

    @property
    def webhook_habilitado(self) -> bool:
        return False


class ConfiguracaoInvalida(RuntimeError):
    """Compatibilidade para comandos opcionais de integração."""


def _booleano(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "sim", "yes", "on"}


def carregar() -> Configuracao:
    load_dotenv(RAIZ / ".env", override=False, encoding="utf-8")
    modo = os.getenv("MODO", "disabled").strip().lower()
    if modo not in {"disabled", "local", "mirror"}:
        raise ConfiguracaoInvalida("MODO deve ser disabled, local ou mirror.")
    arquivo_dados = Path(os.getenv("ARQUIVO_DADOS", "/dados/releases.json"))
    arquivo_dados.parent.mkdir(parents=True, exist_ok=True)
    repositorios = tuple(item.strip() for item in os.getenv("REPOSITORIOS", "").split(",") if item.strip())
    repos_dir = Path(os.environ["REPOS_DIR"]).expanduser() if modo == "local" and os.getenv("REPOS_DIR") else None
    mirrors_dir = Path(os.environ["MIRRORS_DIR"]).expanduser() if modo == "mirror" and os.getenv("MIRRORS_DIR") else None
    token = os.getenv("GITHUB_TOKEN", "").strip() or None
    if modo == "local" and repos_dir is None:
        raise ConfiguracaoInvalida("REPOS_DIR é obrigatório quando MODO=local.")
    if modo == "mirror" and (mirrors_dir is None or not repositorios or not token):
        raise ConfiguracaoInvalida("MIRRORS_DIR, REPOSITORIOS e GITHUB_TOKEN são obrigatórios quando MODO=mirror.")
    return Configuracao(
        modo=modo,
        repos_dir=repos_dir,
        mirrors_dir=mirrors_dir,
        repositorios=repositorios,
        github_token=token if modo == "mirror" else None,
        atualizar_remoto=modo == "mirror" or _booleano(os.getenv("ATUALIZAR_REMOTO", "false")),
        intervalo_minutos=max(1, int(os.getenv("INTERVALO_MINUTOS", "10"))),
        arquivo_dados=arquivo_dados,
    )
