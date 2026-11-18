"""Leitura dos repositorios Git e montagem do mural.

Toda a informacao vem do proprio Git: as tags anotadas dao a versao e o resumo,
e os commits entre duas tags dao a lista de mudancas.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .config import Configuracao
from .modelos import SECAO_PADRAO, SECOES, App, Commit, Mudanca, Mudancas, Mural, Release

log = logging.getLogger("mural.coletor")

SEP_CAMPO = "\x1f"
SEP_REGISTRO = "\x1e"
LIMITE_COMMITS = 2000
TIMEOUT_LEITURA = 30
TIMEOUT_REDE = 120

PADRAO_CONVENTIONAL = re.compile(
    r"^(?P<tipo>[a-zA-Z]+)(?:\((?P<escopo>[^)]*)\))?(?P<quebra>!)?:\s*(?P<titulo>.+)$"
)
PADRAO_MERGE_AUTO = re.compile(r"^Merge (branch|pull request|remote-tracking)\b", re.I)


class ErroGit(RuntimeError):
    """Comando git falhou."""


# --------------------------------------------------------------------------
# Execucao de git
# --------------------------------------------------------------------------


def _git(repo: Path, *args: str, timeout: int = TIMEOUT_LEITURA) -> str:
    resultado = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if resultado.returncode != 0:
        erro = resultado.stderr.decode("utf-8", errors="replace").strip()
        raise ErroGit(f"git {' '.join(args)}: {erro}")
    return resultado.stdout.decode("utf-8", errors="replace")


def _git_opcional(repo: Path, *args: str) -> str | None:
    try:
        return _git(repo, *args).strip()
    except (ErroGit, subprocess.TimeoutExpired):
        return None


# --------------------------------------------------------------------------
# Descoberta e metadados do repositorio
# --------------------------------------------------------------------------


def descobrir_apps(cfg: Configuracao) -> list[tuple[str, Path]]:
    """Lista (id, caminho) dos repositorios a coletar."""
    if cfg.modo == "mirror":
        assert cfg.mirrors_dir is not None
        return [
            (nome.split("/")[-1], cfg.mirrors_dir / f"{nome.split('/')[-1]}.git")
            for nome in cfg.repositorios
        ]

    assert cfg.repos_dir is not None
    apps: list[tuple[str, Path]] = []
    for item in sorted(cfg.repos_dir.iterdir()):
        if item.is_dir() and (item / ".git").exists():
            apps.append((item.name, item))
    return apps


def _url_base(repo: Path) -> tuple[str | None, str | None]:
    """Retorna (repositorio 'owner/nome', url do GitHub) a partir do remoto."""
    url = _git_opcional(repo, "remote", "get-url", "origin")
    if not url:
        return None, None

    url = url.strip()
    if url.startswith("git@"):  # git@github.com:owner/repo.git
        _, _, caminho = url.partition(":")
        host = url[4:].partition(":")[0]
        url = f"https://{host}/{caminho}"
    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")

    partes = url.split("/")
    repositorio = "/".join(partes[-2:]) if len(partes) >= 2 else None
    return repositorio, url


def _branch_padrao(repo: Path) -> str | None:
    """Descobre a branch padrao pelo origin/HEAD, sem assumir 'master'."""
    cabeca = _git_opcional(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if cabeca:
        return cabeca.split("/", 1)[1] if cabeca.startswith("origin/") else cabeca

    atual = _git_opcional(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if atual and atual != "HEAD":
        return atual
    return None


def _ref_da_branch(repo: Path, branch: str, modo: str) -> str | None:
    """Ref que representa o estado publicado da branch."""
    candidatas = (
        [f"refs/heads/{branch}"]
        if modo == "mirror"
        else [f"refs/remotes/origin/{branch}", f"refs/heads/{branch}"]
    )
    for ref in candidatas:
        if _git_opcional(repo, "rev-parse", "--verify", "--quiet", ref):
            return ref
    return None


def assinatura(repo: Path) -> str:
    """Impressao digital de todas as refs — muda quando ha commit ou tag novos."""
    refs = _git_opcional(repo, "show-ref") or ""
    return hashlib.sha256(refs.encode("utf-8")).hexdigest()


def atualizar_remoto(repo: Path, token: str | None = None) -> None:
    """Traz commits e tags novos do remoto.

    Em modo mirror o token entra na URL apenas no argumento do comando; nada e
    gravado no .git/config nem em log.
    """
    if token:
        url = _git_opcional(repo, "remote", "get-url", "origin") or ""
        if url.startswith("https://"):
            url = "https://x-access-token:" + token + "@" + url[len("https://") :]
            _git(repo, "fetch", "--prune", "--tags", "--force", url,
                 "+refs/heads/*:refs/heads/*", timeout=TIMEOUT_REDE)
            return
    _git(repo, "fetch", "--prune", "--tags", "origin", timeout=TIMEOUT_REDE)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def classificar(assunto: str) -> tuple[str, str | None, str]:
    """Quebra o assunto do commit em (tipo, escopo, titulo)."""
    assunto = assunto.strip()
    if PADRAO_MERGE_AUTO.match(assunto):
        return "merge", None, assunto

    casamento = PADRAO_CONVENTIONAL.match(assunto)
    if not casamento:
        return "outro", None, assunto

    tipo = casamento.group("tipo").lower()
    if tipo not in SECOES:
        return "outro", None, assunto

    return tipo, casamento.group("escopo") or None, casamento.group("titulo").strip()


def _secao(tipo: str) -> str:
    return SECOES.get(tipo, SECAO_PADRAO)


def _agrupar(mudancas: list[Mudanca]) -> Mudancas:
    grupos = Mudancas()
    for mudanca in mudancas:
        getattr(grupos, _secao(mudanca.tipo)).append(mudanca)
    return grupos


def _ler_commits(
    repo: Path, faixa: str, url_base: str | None, limite: int = LIMITE_COMMITS
) -> list[Mudanca]:
    formato = SEP_CAMPO.join(["%H", "%h", "%aI", "%s"]) + SEP_REGISTRO
    try:
        saida = _git(repo, "log", f"--pretty=format:{formato}", f"-n{limite}", faixa)
    except (ErroGit, subprocess.TimeoutExpired):
        return []

    mudancas: list[Mudanca] = []
    for registro in saida.split(SEP_REGISTRO):
        registro = registro.strip("\n")
        if not registro:
            continue
        campos = registro.split(SEP_CAMPO)
        if len(campos) != 4:
            continue
        sha_completo, sha_curto, data, assunto = campos
        tipo, escopo, titulo = classificar(assunto)
        mudancas.append(
            Mudanca(
                sha=sha_curto,
                tipo=tipo,
                escopo=escopo,
                titulo=titulo,
                data=data,
                url=f"{url_base}/commit/{sha_completo}" if url_base else None,
            )
        )
    return mudancas


def _ler_tags(repo: Path) -> list[dict]:
    formato = SEP_CAMPO.join(
        ["%(refname:short)", "%(creatordate:iso-strict)", "%(contents:subject)"]
    ) + SEP_REGISTRO
    try:
        saida = _git(repo, "for-each-ref", "refs/tags", "--sort=creatordate",
                     f"--format={formato}")
    except (ErroGit, subprocess.TimeoutExpired):
        return []

    tags: list[dict] = []
    for registro in saida.split(SEP_REGISTRO):
        registro = registro.strip("\n")
        if not registro:
            continue
        campos = registro.split(SEP_CAMPO)
        if len(campos) != 3:
            continue
        nome, data, resumo = campos
        tags.append({"nome": nome, "data": data, "resumo": resumo.strip() or None})
    return tags


# --------------------------------------------------------------------------
# Coleta
# --------------------------------------------------------------------------


def coletar_app(app_id: str, repo: Path, cfg: Configuracao) -> App:
    if not repo.exists():
        return App(id=app_id, nome=app_id, erro="repositorio nao encontrado")

    try:
        repositorio, url_base = _url_base(repo)
        branch = _branch_padrao(repo)
        tags = _ler_tags(repo)

        releases: list[Release] = []
        for indice, tag in enumerate(tags):
            anterior = tags[indice - 1]["nome"] if indice > 0 else None
            faixa = f"{anterior}..{tag['nome']}" if anterior else tag["nome"]
            mudancas = _ler_commits(repo, faixa, url_base)
            if url_base and anterior:
                comparacao = f"{url_base}/compare/{anterior}...{tag['nome']}"
            elif url_base:
                comparacao = f"{url_base}/commits/{tag['nome']}"
            else:
                comparacao = None
            releases.append(
                Release(
                    versao=tag["nome"],
                    data=tag["data"],
                    resumo=tag["resumo"],
                    url_comparacao=comparacao,
                    total_mudancas=len(mudancas),
                    mudancas=_agrupar(mudancas),
                )
            )
        releases.reverse()  # mais recente primeiro

        versao_atual = tags[-1]["nome"] if tags else None
        versao_data = tags[-1]["data"] if tags else None

        nao_versionadas: list[Mudanca] = []
        ultimo_commit: Commit | None = None
        ref = _ref_da_branch(repo, branch, cfg.modo) if branch else None
        if ref:
            faixa = f"{versao_atual}..{ref}" if versao_atual else ref
            nao_versionadas = _ler_commits(repo, faixa, url_base)

            cabeca = _ler_commits(repo, ref, url_base, limite=1)
            if cabeca:
                topo = cabeca[0]
                ultimo_commit = Commit(
                    sha=topo.sha,
                    data=topo.data,
                    assunto=f"{topo.tipo}({topo.escopo}): {topo.titulo}"
                    if topo.escopo
                    else topo.titulo,
                    url=topo.url,
                )

        return App(
            id=app_id,
            nome=app_id,
            repositorio=repositorio,
            url_github=url_base,
            branch=branch,
            versao_atual=versao_atual,
            versao_data=versao_data,
            commits_desde_versao=len(nao_versionadas),
            nao_versionadas=_agrupar(nao_versionadas),
            ultimo_commit=ultimo_commit,
            releases=releases,
        )
    except (ErroGit, subprocess.TimeoutExpired, OSError) as erro:
        log.warning("falha ao coletar %s: %s", app_id, erro)
        return App(id=app_id, nome=app_id, erro=str(erro))


class Coletor:
    """Mantem o cache por repositorio e so reprocessa o que mudou."""

    def __init__(self, cfg: Configuracao) -> None:
        self.cfg = cfg
        self._cache: dict[str, tuple[str, App]] = {}

    def coletar(self, forcar: bool = False, apenas: str | None = None) -> tuple[Mural, list[str]]:
        """Retorna (mural, ids que mudaram nesta passada)."""
        inicio = time.monotonic()
        alvos = descobrir_apps(self.cfg)
        if apenas:
            alvos = [item for item in alvos if item[0] == apenas] or alvos

        mudaram: list[str] = []

        def processar(par: tuple[str, Path]) -> App:
            app_id, repo = par
            if self.cfg.atualizar_remoto and repo.exists():
                try:
                    atualizar_remoto(repo, self.cfg.github_token)
                except (ErroGit, subprocess.TimeoutExpired) as erro:
                    log.warning("fetch falhou em %s: %s", app_id, erro)

            impressao = assinatura(repo) if repo.exists() else "ausente"
            anterior = self._cache.get(app_id)
            if not forcar and anterior and anterior[0] == impressao:
                return anterior[1]

            app = coletar_app(app_id, repo, self.cfg)
            self._cache[app_id] = (impressao, app)
            mudaram.append(app_id)
            return app

        trabalhadores = min(8, max(1, len(alvos)))
        with ThreadPoolExecutor(max_workers=trabalhadores) as executor:
            apps = list(executor.map(processar, alvos))

        apps.sort(key=lambda item: item.nome.lower())
        mural = Mural(
            gerado_em=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            duracao_ms=int((time.monotonic() - inicio) * 1000),
            apps=apps,
        )
        return mural, mudaram


# --------------------------------------------------------------------------
# Persistencia
# --------------------------------------------------------------------------


def escrever(mural: Mural, destino: Path) -> None:
    """Grava o JSON de forma atomica — a tela nunca le um arquivo pela metade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    temporario.write_text(
        json.dumps(mural.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporario, destino)


def ler(origem: Path) -> Mural | None:
    if not origem.is_file():
        return None
    try:
        return Mural.model_validate_json(origem.read_text(encoding="utf-8"))
    except (ValueError, OSError) as erro:
        log.warning("cache invalido em %s: %s", origem, erro)
        return None
