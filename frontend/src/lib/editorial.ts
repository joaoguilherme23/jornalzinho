import type { Mural } from "../types";

const SECOES = ["novidades", "correcoes", "melhorias", "outros"] as const;
type Secao = (typeof SECOES)[number];
type TipoNoticia = "novidade" | "correcao" | "melhoria" | "comunicado";
type Registro = { sha?: string; titulo?: string; data?: string; url?: string };
export type Mudancas = Partial<Record<Secao, Registro[]>>;

export type CatalogoApp = {
  nomeEditorial?: string;
  descricaoEditorial?: string;
  areas?: string[];
  sigla?: string;
  tom?: string;
  assinatura?: string;
  release?: [string, string, string[]];
};
export type CuradoriaInicial = {
  resumoOriginal?: string;
  titulo?: string;
  resumo?: string;
};
export type EditorialCatalog = {
  apps: Record<string, CatalogoApp>;
  curadoria: Record<string, CuradoriaInicial>;
};
export type FonteRelease = {
  versao?: string;
  data?: string;
  resumo?: string;
  mudancas?: Mudancas;
};
export type DadosDoApp = {
  id: string;
  nome: string;
  nomeEditorial: string;
  descricaoEditorial: string;
  areas: string[];
  sigla: string;
  tom: string;
  assinatura?: string;
  release?: [string, string, string[]];
  releases: FonteRelease[];
  nao_versionadas: Mudancas;
  ultimo_commit?: { data?: string };
  versao_data?: string;
  url_github?: string;
  erro?: boolean;
};
export type Noticia = {
  id: string;
  appId: string;
  titulo: string;
  resumo: string;
  data: string;
  tipo: TipoNoticia;
  areas: string[];
  pendente: boolean;
  versao: string | null;
  pontos: string[];
  fonte: FonteRelease | Mudancas;
  contextualizada: boolean;
};
export type EditorialPreparado = {
  apps: DadosDoApp[];
  noticias: Noticia[];
  /** Compatibilidade com o consumidor React inicial. */ news: Noticia[];
};

const catalogoVazio: EditorialCatalog = { apps: {}, curadoria: {} };

function registro(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function texto(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}
function lista(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function mudancasDe(value: unknown): Mudancas {
  const source = registro(value);
  return Object.fromEntries(
    SECOES.map((secao) => [
      secao,
      lista(source[secao]).map((item) => {
        const change = registro(item);
        return {
          sha: texto(change.sha, ""),
          titulo: texto(change.titulo, ""),
          data: texto(change.data, ""),
          url: texto(change.url, ""),
        };
      }),
    ]),
  ) as Mudancas;
}
function fonteRelease(value: unknown): FonteRelease {
  const release = registro(value);
  return {
    versao: texto(release.versao, ""),
    data: texto(release.data, ""),
    resumo: texto(release.resumo, ""),
    mudancas: mudancasDe(release.mudancas),
  };
}
function total(mudancas: Mudancas): number {
  return SECOES.reduce(
    (soma, secao) => soma + (mudancas[secao]?.length ?? 0),
    0,
  );
}
function tipoDe(mudancas: Mudancas): TipoNoticia {
  const tipos: Record<Secao, TipoNoticia> = {
    novidades: "novidade",
    correcoes: "correcao",
    melhorias: "melhoria",
    outros: "comunicado",
  };
  const secao = SECOES.find((item) => (mudancas[item]?.length ?? 0) > 0);
  return secao ? tipos[secao] : "comunicado";
}
export function assinaturaDe(mudancas: Mudancas): string {
  const linhas = SECOES.flatMap((secao) =>
    (mudancas[secao] ?? []).map(
      (mudanca) => `${texto(mudanca.sha, "")}|${texto(mudanca.titulo, "")}`,
    ),
  ).sort();
  let hash = 2166136261;
  for (const caractere of linhas.join("\n")) {
    hash ^= caractere.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}
function dataPendente(app: DadosDoApp, mudancas: Mudancas): string {
  const candidatas = [
    ...SECOES.flatMap((secao) =>
      (mudancas[secao] ?? []).map((mudanca) => mudanca.data ?? ""),
    ),
    app.ultimo_commit?.data ?? "",
    app.versao_data ?? "",
  ];
  return candidatas.reduce((maisRecente, candidata) => {
    const instante = Date.parse(candidata);
    if (!Number.isFinite(instante)) return maisRecente;
    return !maisRecente || instante > Date.parse(maisRecente)
      ? candidata
      : maisRecente;
  }, "");
}
function instanteValido(data: string): number | null {
  const instante = Date.parse(data);
  return Number.isFinite(instante) ? instante : null;
}
function id(...partes: string[]): string {
  return partes
    .map((parte) => encodeURIComponent(texto(parte, "sem-id")))
    .join(":");
}

export function dadosDoApp(
  value: unknown,
  catalogo: EditorialCatalog = catalogoVazio,
): DadosDoApp {
  const original = registro(value);
  const appId = texto(original.id, "sem-id");
  const conhecido = catalogo.apps[appId];
  const nome = texto(original.nome, appId || "Aplicação");
  const curadoria = conhecido?.release;
  const release =
    Array.isArray(curadoria) &&
    curadoria.length === 3 &&
    typeof curadoria[0] === "string" &&
    typeof curadoria[1] === "string" &&
    Array.isArray(curadoria[2])
      ? ([
          texto(curadoria[0], ""),
          texto(curadoria[1], ""),
          curadoria[2].filter(
            (item): item is string => typeof item === "string",
          ),
        ] as [string, string, string[]])
      : undefined;
  const ultimoCommit = registro(original.ultimo_commit);
  return {
    id: appId,
    nome,
    nomeEditorial: texto(conhecido?.nomeEditorial, nome),
    descricaoEditorial: texto(
      conhecido?.descricaoEditorial,
      "Atualizações registradas neste sistema.",
    ),
    areas: lista(conhecido?.areas).filter(
      (item): item is string => typeof item === "string",
    ),
    sigla: texto(conhecido?.sigla, nome.slice(0, 2).toUpperCase() || "AP"),
    tom: texto(conhecido?.tom, "areia"),
    assinatura: texto(conhecido?.assinatura, "") || undefined,
    release,
    releases: lista(original.releases).map(fonteRelease),
    nao_versionadas: mudancasDe(original.nao_versionadas),
    ultimo_commit: Object.keys(ultimoCommit).length
      ? { data: texto(ultimoCommit.data, "") }
      : undefined,
    versao_data: texto(original.versao_data, "") || undefined,
    url_github: texto(original.url_github, "") || undefined,
    erro: Boolean(original.erro),
  };
}
function noticiaDeRelease(
  app: DadosDoApp,
  fonte: FonteRelease,
  catalogo: EditorialCatalog,
): Noticia {
  const versao = texto(fonte.versao, "sem versão");
  const porAssinatura = Boolean(
    app.assinatura &&
    app.assinatura === assinaturaDe(fonte.mudancas ?? {}) &&
    app.release,
  );
  const inicial = catalogo.curadoria[app.id];
  const inicialConfirmada = Boolean(
    inicial &&
    versao === "v1.0.0" &&
    fonte.resumo === texto(inicial.resumoOriginal, ""),
  );
  return {
    id: id("release", app.id, versao),
    appId: app.id,
    titulo:
      porAssinatura && app.release
        ? app.release[0]
        : inicialConfirmada
          ? texto(
              inicial?.titulo,
              `Atualização registrada em ${app.nomeEditorial}`,
            )
          : `Atualização registrada em ${app.nomeEditorial}`,
    resumo:
      porAssinatura && app.release
        ? app.release[1]
        : inicialConfirmada
          ? texto(inicial?.resumo, app.descricaoEditorial)
          : texto(fonte.resumo, app.descricaoEditorial),
    data: texto(fonte.data, app.versao_data ?? ""),
    tipo: tipoDe(fonte.mudancas ?? {}),
    areas: app.areas.slice(),
    pendente: false,
    versao,
    pontos:
      porAssinatura && app.release
        ? app.release[2].slice()
        : ["A atualização foi registrada a partir da fonte do projeto."],
    fonte,
    contextualizada: porAssinatura || inicialConfirmada,
  };
}
function noticiaPendente(app: DadosDoApp): Noticia | null {
  const mudancas = app.nao_versionadas;
  if (!total(mudancas)) return null;
  return {
    id: id("preparacao", app.id),
    appId: app.id,
    titulo: `Atualização em preparação para ${app.nomeEditorial}`,
    resumo:
      "Há novas mudanças registradas para este aplicativo. A disponibilidade ainda não foi confirmada.",
    data: dataPendente(app, mudancas),
    tipo: tipoDe(mudancas),
    areas: app.areas.slice(),
    pendente: true,
    versao: null,
    pontos: [
      "Os detalhes técnicos permanecem disponíveis na fonte da atualização.",
    ],
    fonte: mudancas,
    contextualizada: false,
  };
}
export function preparar(
  mural: Mural | unknown,
  catalogo: EditorialCatalog = catalogoVazio,
): EditorialPreparado {
  const apps = lista(registro(mural).apps).map((app) =>
    dadosDoApp(app, catalogo),
  );
  const noticias = apps
    .flatMap((app) => {
      const releases = app.releases.map((release) =>
        noticiaDeRelease(app, release, catalogo),
      );
      const pendente = noticiaPendente(app);
      return pendente ? [...releases, pendente] : releases;
    })
    .sort((primeira, segunda) => {
      const dataPrimeira = instanteValido(primeira.data);
      const dataSegunda = instanteValido(segunda.data);
      if (
        dataPrimeira !== null &&
        dataSegunda !== null &&
        dataPrimeira !== dataSegunda
      )
        return dataSegunda - dataPrimeira;
      if (dataPrimeira !== null && dataSegunda === null) return -1;
      if (dataPrimeira === null && dataSegunda !== null) return 1;
      return primeira.appId.localeCompare(segunda.appId, "pt-BR");
    });
  return { apps, noticias, news: noticias };
}
