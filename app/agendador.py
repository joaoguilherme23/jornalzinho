"""Mural local estático para a edição pública, sem leitura de Git."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .config import Configuracao
from .modelos import Mural


class Servico:
    def __init__(self, cfg: Configuracao) -> None:
        self.cfg = cfg
        self.mural = Mural(gerado_em=datetime.now(timezone.utc).isoformat(), duracao_ms=0, apps=[])
        self.corpo = json.dumps(self.mural.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        self.etag = '"' + hashlib.sha256(self.corpo).hexdigest()[:16] + '"'
        self.ultima_coleta = self.mural.gerado_em

    def carregar_cache(self) -> None:
        return None

    def iniciar(self) -> None:
        return None

    async def parar(self) -> None:
        return None

    async def atualizar(self, *_: object, **__: object) -> list[str]:
        return []

    def saude(self) -> dict[str, object]:
        return {"ok": True, "modo": "local", "apps": 0, "ultima_coleta": self.ultima_coleta}
