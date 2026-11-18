"""Contrato de dados servido em /api/releases.json."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Prefixo de conventional commit -> secao exibida na tela.
SECOES = {
    "feat": "novidades",
    "feature": "novidades",
    "fix": "correcoes",
    "hotfix": "correcoes",
    "bugfix": "correcoes",
    "perf": "melhorias",
    "refactor": "melhorias",
    "style": "melhorias",
    "docs": "outros",
    "chore": "outros",
    "test": "outros",
    "tests": "outros",
    "build": "outros",
    "ci": "outros",
    "revert": "outros",
    "merge": "outros",
}

SECAO_PADRAO = "outros"
ORDEM_SECOES = ("novidades", "correcoes", "melhorias", "outros")

ROTULOS_SECOES = {
    "novidades": "Novidades",
    "correcoes": "Correcoes",
    "melhorias": "Melhorias",
    "outros": "Outros",
}


class Mudanca(BaseModel):
    sha: str
    tipo: str
    escopo: str | None = None
    titulo: str
    data: str
    url: str | None = None


class Mudancas(BaseModel):
    novidades: list[Mudanca] = Field(default_factory=list)
    correcoes: list[Mudanca] = Field(default_factory=list)
    melhorias: list[Mudanca] = Field(default_factory=list)
    outros: list[Mudanca] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.novidades) + len(self.correcoes) + len(self.melhorias) + len(self.outros)


class Commit(BaseModel):
    sha: str
    data: str
    assunto: str
    url: str | None = None


class Release(BaseModel):
    versao: str
    data: str
    resumo: str | None = None
    url_comparacao: str | None = None
    total_mudancas: int = 0
    mudancas: Mudancas = Field(default_factory=Mudancas)


class App(BaseModel):
    id: str
    nome: str
    repositorio: str | None = None
    url_github: str | None = None
    branch: str | None = None
    versao_atual: str | None = None
    versao_data: str | None = None
    commits_desde_versao: int = 0
    nao_versionadas: Mudancas = Field(default_factory=Mudancas)
    ultimo_commit: Commit | None = None
    releases: list[Release] = Field(default_factory=list)
    erro: str | None = None


class Mural(BaseModel):
    gerado_em: str
    duracao_ms: int = 0
    apps: list[App] = Field(default_factory=list)
