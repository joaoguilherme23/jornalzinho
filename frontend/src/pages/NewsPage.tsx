import {
  navigate,
  appHref,
  currentWorkspaceRoute,
  NAVIGATION_EVENT,
} from "../lib/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, error as mensagemDeErro } from "../api";
import {
  preparar,
  type DadosDoApp,
  type EditorialCatalog,
  type EditorialPreparado,
  type Mudancas,
  type Noticia,
} from "../lib/editorial";
import type { Mural } from "../types";
import "./NewsPage.css";

const POR_PAGINA = 7;
const SECOES: Array<[keyof Mudancas, string]> = [
  ["novidades", "Novidades"],
  ["correcoes", "Correções"],
  ["melhorias", "Melhorias"],
  ["outros", "Outros registros"],
];

type Rota =
  { tipo: "inicio" | "git-lista" } | { tipo: "noticia" | "git"; id: string };
type Filtros = { busca: string; area: string; tipo: string };

function rotaAtual(): Rota {
  const raw = currentWorkspaceRoute().split("?")[0];
  try {
    if (!raw || raw === "news") return { tipo: "inicio" };
    if (raw === "git") return { tipo: "git-lista" };
    if (raw.startsWith("news/"))
      return { tipo: "noticia", id: decodeURIComponent(raw.slice(5)) };
    if (raw.startsWith("git/"))
      return { tipo: "git", id: decodeURIComponent(raw.slice(4)) };
  } catch {
    return { tipo: "inicio" };
  }
  return { tipo: "inicio" };
}

function navegar(destino: string): void {
  navigate(`#/${destino}`);
}
function normalizar(valor: string): string {
  return valor
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}
function data(valor: string): string {
  return Number.isFinite(Date.parse(valor))
    ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
        new Date(valor),
      )
    : "Data não informada";
}
function linkDaFonte(_: string | undefined): string | null {
  // Esta edição pública não inclui links nem leitura de repositórios externos.
  return null;
}
function nomeTipo(tipo: string): string {
  return (
    (
      {
        novidade: "Novidades",
        correcao: "Correções",
        melhoria: "Melhorias",
        comunicado: "Outros registros",
      } as Record<string, string>
    )[tipo] ?? "Registro"
  );
}
function mudancasDaFonte(fonte: Noticia["fonte"]): Mudancas {
  const release = fonte as { mudancas?: Mudancas };
  return release.mudancas ?? (fonte as Mudancas);
}

function Fonte({
  noticia,
  app,
}: {
  noticia: Noticia;
  app: DadosDoApp | undefined;
}) {
  const mudancas = mudancasDaFonte(noticia.fonte);
  const linkDaAplicacao = linkDaFonte(app?.url_github);
  return (
    <details className="news-source">
      <summary>Ver detalhes da fonte</summary>
      <p>
        {noticia.pendente
          ? "Mudanças que ainda não têm uma versão marcada."
          : `Versão registrada: ${noticia.versao ?? "não informada"}.`}
      </p>
      <p>
        O registro de uma versão não confirma que ela já esteja disponível para
        uso.
      </p>
      {SECOES.map(([secao, rotulo]) => {
        const itens = mudancas[secao] ?? [];
        return itens.length ? (
          <section key={secao}>
            <h3>{rotulo}</h3>
            <ul>
              {itens.map((item, index) => {
                const url = linkDaFonte(item.url);
                return (
                  <li key={`${item.sha ?? index}:${item.titulo ?? ""}`}>
                    <span>{item.titulo || "Mudança registrada"}</span>
                    {url && (
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        Ver registro
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null;
      })}
      {linkDaAplicacao && (
        <a
          className="news-source__github"
          href={linkDaAplicacao}
          target="_blank"
          rel="noopener noreferrer"
        >
          Consultar projeto
        </a>
      )}
    </details>
  );
}

function Card({
  noticia,
  app,
  destaque = false,
}: {
  noticia: Noticia;
  app: DadosDoApp | undefined;
  destaque?: boolean;
}) {
  return (
    <a
      className={`news-card${destaque ? " news-card--feature" : ""}`}
      href={appHref(`#/news/${encodeURIComponent(noticia.id)}`)}
    >
      {destaque && (
        <span className="news-card__monogram" aria-hidden="true">
          {app?.sigla ?? "M"}
        </span>
      )}
      <div>
        <p className="news-card__category">
          {noticia.pendente ? "Em preparação" : nomeTipo(noticia.tipo)}
        </p>
        <h2>{noticia.titulo}</h2>
        <p className="news-card__meta">
          {data(noticia.data)} ·{" "}
          {noticia.areas.join(" · ") || "Sem área definida"}
        </p>
        <p>{noticia.resumo}</p>
        <span className="news-card__more">Ler notícia →</span>
      </div>
    </a>
  );
}

function FiltrosNoticias({
  filtros,
  areas,
  onChange,
}: {
  filtros: Filtros;
  areas: string[];
  onChange: (filtros: Filtros) => void;
}) {
  return (
    <section className="news-filters" aria-label="Filtros das notícias">
      <label>
        Busca
        <input
          type="search"
          value={filtros.busca}
          placeholder="Buscar uma notícia ou projeto"
          onChange={(event) =>
            onChange({ ...filtros, busca: event.target.value })
          }
        />
      </label>
      <label>
        Área
        <select
          value={filtros.area}
          onChange={(event) =>
            onChange({ ...filtros, area: event.target.value })
          }
        >
          <option value="">Todas as áreas</option>
          {areas.map((area) => (
            <option value={area} key={area}>
              {area}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tipo
        <select
          value={filtros.tipo}
          onChange={(event) =>
            onChange({ ...filtros, tipo: event.target.value })
          }
        >
          <option value="">Todos os tipos</option>
          <option value="novidade">Novidades</option>
          <option value="correcao">Correções</option>
          <option value="melhoria">Melhorias</option>
          <option value="comunicado">Outros registros</option>
          <option value="pendente">Em preparação</option>
        </select>
      </label>
    </section>
  );
}

function ListaProjetos({ dados }: { dados: EditorialPreparado }) {
  return (
    <>
      <section className="news-opening">
        <p>Projetos Git</p>
        <h1>Projetos que movem a rede.</h1>
        <span>
          Encontre cada projeto e acompanhe as atualizações registradas para
          ele.
        </span>
      </section>
      <section className="news-projects" aria-label="Projetos Git">
        {dados.apps.map((app) => (
          <a
            href={appHref(`#/git/${encodeURIComponent(app.id)}`)}
            key={app.id}
            className="news-project"
          >
            <span>{app.areas.join(" · ") || "Sem área definida"}</span>
            <h2>{app.nomeEditorial}</h2>
            <p>{app.descricaoEditorial}</p>
            {app.erro && <strong>Leitura pendente</strong>}
            <b>Acompanhar projeto →</b>
          </a>
        ))}
      </section>
    </>
  );
}

function ProjetoGit({ dados, id }: { dados: EditorialPreparado; id: string }) {
  const app = dados.apps.find((item) => item.id === id);
  if (!app) return <EstadoVazio titulo="Projeto não encontrado" />;
  const noticias = dados.noticias.filter((noticia) => noticia.appId === id);
  return (
    <>
      <a className="news-back" href={appHref("#/git")}>
        ← Ver todos os projetos
      </a>
      <section className="news-opening">
        <p>Projeto em acompanhamento</p>
        <h1>{app.nomeEditorial}</h1>
        <span>{app.descricaoEditorial}</span>
      </section>
      {app.erro && (
        <p className="news-warning">
          A última leitura deste projeto não foi concluída. Os registros
          anteriores continuam disponíveis.
        </p>
      )}
      <section className="news-timeline">
        <h2>Linha do tempo de releases</h2>
        {app.releases.length ? (
          app.releases.map((release, index) => (
            <article key={`${release.versao ?? index}:${release.data ?? ""}`}>
              <time>{data(release.data ?? "")}</time>
              <h3>{release.versao || "Versão não informada"}</h3>
              <p>
                {release.resumo ||
                  "Atualização registrada a partir da fonte do projeto."}
              </p>
            </article>
          ))
        ) : (
          <p>Este projeto ainda não tem releases registradas.</p>
        )}
      </section>
      <section className="news-list">
        <h2>Notícias do projeto</h2>
        {noticias.length ? (
          noticias.map((noticia) => (
            <Card key={noticia.id} noticia={noticia} app={app} />
          ))
        ) : (
          <p>Este projeto ainda não tem atualizações registradas.</p>
        )}
      </section>
    </>
  );
}

function DetalheNoticia({
  dados,
  id,
}: {
  dados: EditorialPreparado;
  id: string;
}) {
  const noticia = dados.noticias.find((item) => item.id === id);
  if (!noticia) return <EstadoVazio titulo="Notícia não encontrada" />;
  const app = dados.apps.find((item) => item.id === noticia.appId);
  return (
    <article className="news-detail">
      <a className="news-back" href={appHref("#/news")}>
        ← Voltar às notícias
      </a>
      <p>{noticia.pendente ? "Em preparação" : nomeTipo(noticia.tipo)}</p>
      <h1>{noticia.titulo}</h1>
      <span>
        {data(noticia.data)} ·{" "}
        {noticia.areas.join(" · ") || "Sem área definida"}
      </span>
      <p className="news-detail__summary">{noticia.resumo}</p>
      <ul>
        {noticia.pontos.map((ponto) => (
          <li key={ponto}>{ponto}</li>
        ))}
      </ul>
      <a
        className="news-project-link"
        href={appHref(`#/git/${encodeURIComponent(noticia.appId)}`)}
      >
        Acompanhar {app?.nomeEditorial ?? "projeto"} →
      </a>
      <Fonte noticia={noticia} app={app} />
    </article>
  );
}
function EstadoVazio({ titulo }: { titulo: string }) {
  return (
    <section className="news-empty">
      <h1>{titulo}</h1>
      <p>Este endereço não corresponde a uma notícia ou projeto do mural.</p>
      <a href={appHref("#/news")}>Voltar às notícias</a>
    </section>
  );
}
function Esqueleto() {
  return (
    <section className="news-skeleton" aria-label="Carregando notícias">
      <i />
      <i />
      <i />
    </section>
  );
}

export default function NewsPage() {
  const [dados, setDados] = useState<EditorialPreparado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [rota, setRota] = useState<Rota>(rotaAtual);
  const [filtros, setFiltros] = useState<Filtros>({
    busca: "",
    area: "",
    tipo: "",
  });
  const [limite, setLimite] = useState(POR_PAGINA);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const [mural, catalogo] = await Promise.all([
        api.get<Mural>("/api/releases.json"),
        api.get<EditorialCatalog>("/api/editorial.json"),
      ]);
      setDados(preparar(mural.data, catalogo.data));
      setErro(null);
    } catch (cause) {
      setErro(mensagemDeErro(cause));
    } finally {
      setCarregando(false);
    }
  }, []);
  useEffect(() => {
    void carregar();
  }, [carregar]);
  useEffect(() => {
    const atualizar = () => setRota(rotaAtual());
    addEventListener(NAVIGATION_EVENT, atualizar);
    return () => removeEventListener(NAVIGATION_EVENT, atualizar);
  }, []);
  useEffect(() => {
    setLimite(POR_PAGINA);
  }, [filtros]);

  const areas = useMemo(
    () =>
      dados
        ? [...new Set(dados.apps.flatMap((app) => app.areas))].sort((a, b) =>
            a.localeCompare(b, "pt-BR"),
          )
        : [],
    [dados],
  );
  const noticias = useMemo(
    () =>
      dados?.noticias.filter((noticia) => {
        const alvo = [
          noticia.titulo,
          noticia.resumo,
          noticia.appId,
          ...noticia.areas,
        ].join(" ");
        return (
          (!filtros.busca ||
            normalizar(alvo).includes(normalizar(filtros.busca))) &&
          (!filtros.area || noticia.areas.includes(filtros.area)) &&
          (!filtros.tipo ||
            (filtros.tipo === "pendente"
              ? noticia.pendente
              : noticia.tipo === filtros.tipo))
        );
      }) ?? [],
    [dados, filtros],
  );

  if (carregando && !dados)
    return (
      <section className="news-page">
        <Esqueleto />
      </section>
    );
  if (!dados)
    return (
      <section className="news-page">
        <section className="news-error" role="alert">
          <h1>Não foi possível carregar as notícias</h1>
          <p>{erro ?? "Confira a conexão e tente novamente."}</p>
          <button onClick={() => void carregar()}>Tentar novamente</button>
        </section>
      </section>
    );

  const cards = noticias
    .slice(1, limite)
    .map((noticia) => (
      <Card
        key={noticia.id}
        noticia={noticia}
        app={dados.apps.find((app) => app.id === noticia.appId)}
      />
    ));
  const inicio = (
    <>
      <section className="news-opening">
        <p>Notícias internas</p>
        <h1>A rede em movimento.</h1>
        <span>
          O que está evoluindo nos nossos projetos, em uma leitura para quem
          acompanha e faz a rede acontecer.
        </span>
        <button onClick={() => navegar("git")}>Projetos Git</button>
      </section>
      <FiltrosNoticias filtros={filtros} areas={areas} onChange={setFiltros} />
      <div className="news-heading">
        <h2>Últimas notícias</h2>
        <span>
          {noticias.length} {noticias.length === 1 ? "notícia" : "notícias"}
        </span>
      </div>
      {noticias.length ? (
        <>
          <Card
            noticia={noticias[0]}
            app={dados.apps.find((app) => app.id === noticias[0].appId)}
            destaque
          />
          <section className="news-list">{cards}</section>
          {noticias.length > limite && (
            <button
              className="news-more"
              onClick={() => setLimite((atual) => atual + 6)}
            >
              Ver mais notícias
            </button>
          )}
        </>
      ) : (
        <section className="news-empty">
          <h2>Nenhuma notícia encontrada</h2>
          <p>Ajuste a busca ou os filtros para ver outras atualizações.</p>
          <button onClick={() => setFiltros({ busca: "", area: "", tipo: "" })}>
            Limpar filtros
          </button>
        </section>
      )}
    </>
  );
  const corpo =
    rota.tipo === "noticia" ? (
      <DetalheNoticia dados={dados} id={rota.id} />
    ) : rota.tipo === "git" ? (
      <ProjetoGit dados={dados} id={rota.id} />
    ) : rota.tipo === "git-lista" ? (
      <ListaProjetos dados={dados} />
    ) : (
      inicio
    );
  return (
    <section className="news-page">
      {erro && (
        <aside className="news-error" role="alert">
          <p>
            Não foi possível atualizar as novidades. Os últimos registros
            carregados foram mantidos.
          </p>
          <button onClick={() => void carregar()}>Tentar novamente</button>
        </aside>
      )}
      {corpo}
    </section>
  );
}
