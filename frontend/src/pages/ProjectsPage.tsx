import { appHref, navigate } from "../lib/navigation";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, backend, error } from "../api";
import { preparar, type EditorialCatalog } from "../lib/editorial";
import {
  formatDate,
  healthOf,
  labelPriority,
  labelStatus,
  portfolioApi,
  recentGitChanges,
  textoInclui,
  urlSegura,
  type PortfolioItem,
} from "../lib/portfolio";
import { PortfolioEditor } from "./PortfolioPage";
import type { Mural } from "../types";
import "./ProjectsPage.css";

type Props = {
  autoOpen?: boolean;
  canCreate?: boolean;
  projectId?: number;
  gitId?: string;
};
const healthLabels = {
  finalizado: "Finalizado",
  atraso: "Em atraso",
  critico: "Crítico",
  aguardando: "Aguardando",
  "a-definir": "A definir",
  "em-dia": "Em dia",
};
const projectLink = (item: PortfolioItem) =>
  item.project_id !== null
    ? appHref(`#/projects/${item.project_id}`)
    : appHref(
        `#/projects/git/${encodeURIComponent(item.git?.id ?? item.legacy_app_id ?? "")}`,
      );

export function ProjectsPage({
  autoOpen = false,
  canCreate = false,
  projectId,
  gitId,
}: Props) {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [area, setArea] = useState("");
  const [period, setPeriod] = useState("all");
  const [editing, setEditing] = useState<PortfolioItem | null>(null);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const expected = ++generation.current;
    setLoading(true);
    setNotice("");
    try {
      if (autoOpen) {
        const projects = await backend.projects();
        if (generation.current !== expected) return;
        const first = projects.find((project) => project.default_board_id);
        if (first) {
          navigate(`#/board/${first.default_board_id}`);
          return;
        }
      }
      const [data, catalog] = await Promise.all([
        portfolioApi.list(),
        api
          .get<EditorialCatalog>("api/editorial.json")
          .then((response) => response.data),
      ]);
      if (generation.current !== expected) return;
      const editorial = preparar(
        {
          gerado_em: data.git_collected_at,
          apps: data.items.flatMap((item) => (item.git ? [item.git] : [])),
        } as Mural,
        catalog,
      );
      const apps = new Map(editorial.apps.map((app) => [app.id, app]));
      setItems(
        data.items.map((item) => {
          const context = item.git && apps.get(item.git.id);
          return context && item.git
            ? {
                ...item,
                name:
                  item.name === item.git.nome
                    ? context.nomeEditorial
                    : item.name,
                description: item.description ?? context.descricaoEditorial,
                git: { ...item.git, areas: context.areas },
              }
            : item;
        }),
      );
    } catch (failure) {
      if (expected === generation.current) setNotice(error(failure));
    } finally {
      if (expected === generation.current) setLoading(false);
    }
  }, [autoOpen]);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  const areas = useMemo(
    () =>
      [...new Set(items.flatMap((item) => item.git?.areas ?? []))].sort(
        (a, b) => a.localeCompare(b, "pt-BR"),
      ),
    [items],
  );
  const filtered = items.filter((item) => {
    const timestamp = Date.parse(
      item.git?.ultimo_commit?.data ?? item.git?.versao_data ?? "",
    );
    return (
      textoInclui(`${item.name} ${item.description ?? ""}`, search) &&
      (!area || item.git?.areas?.includes(area)) &&
      (period === "all" ||
        (Number.isFinite(timestamp) &&
          timestamp <= Date.now() &&
          timestamp >= Date.now() - Number(period) * 86400000))
    );
  });
  const selected =
    projectId !== undefined
      ? items.find((item) => item.project_id === projectId)
      : gitId
        ? items.find((item) => encodeURIComponent(item.git?.id ?? "") === gitId)
        : undefined;
  const detail = projectId !== undefined || gitId !== undefined;
  return (
    <section className="prototype-projects">
      {detail && (
        <a className="projects-back" href={appHref("#/projects")}>
          ← Ver todos os projetos
        </a>
      )}
      {!detail && (
        <header className="projects-opening">
          <p className="projects-eyebrow">Nossos projetos</p>
          <h1>Projetos que movem a rede.</h1>
          <p>
            Encontre cada projeto e acompanhe as atualizações registradas para
            ele.
          </p>
        </header>
      )}
      {notice && (
        <div className="error" role="alert">
          <p>{notice}</p>
          <button className="quiet" onClick={() => void load()}>
            Tentar novamente
          </button>
        </div>
      )}
      {loading ? (
        <p className="projects-empty" role="status">
          Carregando projetos…
        </p>
      ) : detail ? (
        selected ? (
          <ProjectDetails
            item={selected}
            canCreate={canCreate}
            edit={() => setEditing(selected)}
          />
        ) : (
          <div className="projects-empty" role="alert">
            <h1>Projeto indisponível</h1>
            <p>O projeto não está disponível para sua conta.</p>
          </div>
        )
      ) : (
        <>
          <section
            className="projects-filters"
            aria-label="Filtros dos projetos"
          >
            <label>
              Busca
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Buscar uma notícia ou projeto"
                autoComplete="off"
              />
            </label>
            <label>
              Área
              <select
                value={area}
                onChange={(event) => setArea(event.target.value)}
              >
                <option value="">Todas as áreas</option>
                {areas.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <div className="projects-chips" role="group" aria-label="Período">
              {[
                ["all", "Todo período"],
                ["7", "7 dias"],
                ["30", "30 dias"],
                ["90", "90 dias"],
              ].map(([value, title]) => (
                <button
                  key={value}
                  aria-pressed={period === value}
                  onClick={() => setPeriod(value)}
                >
                  {title}
                </button>
              ))}
            </div>
          </section>
          <div className="projects-section-title">
            <h2>Em acompanhamento</h2>
            <span>
              {filtered.length} {filtered.length === 1 ? "projeto" : "projetos"}
            </span>
          </div>
          {filtered.length ? (
            <div className="projects-catalog" aria-label="Projetos">
              {filtered.map((item) => (
                <a
                  className="projects-catalog-card"
                  key={item.ref}
                  href={projectLink(item)}
                >
                  <span className="projects-category">
                    {item.git?.areas?.join(" · ") || "Sem área definida"}
                  </span>
                  <h3>{item.name}</h3>
                  <p>
                    {item.description ||
                      "Acompanhe as tarefas e os próximos passos deste projeto."}
                  </p>
                  {item.git?.erro && (
                    <span className="projects-warning">Leitura pendente</span>
                  )}
                  <span className="projects-read">Acompanhar projeto →</span>
                </a>
              ))}
            </div>
          ) : (
            <div className="projects-empty">
              <h2>
                {items.length
                  ? "Nenhum projeto encontrado"
                  : "Aguardando acesso a um projeto"}
              </h2>
              <p>
                {items.length
                  ? "Ajuste a busca ou os filtros para ver outros projetos."
                  : canCreate
                    ? "Cadastre o primeiro projeto para começar a organizar as tarefas."
                    : "Peça ao administrador ou gestor que vincule sua conta a um projeto."}
              </p>
              {items.length > 0 && (
                <button
                  className="quiet"
                  onClick={() => {
                    setSearch("");
                    setArea("");
                    setPeriod("all");
                  }}
                >
                  Limpar filtros
                </button>
              )}
            </div>
          )}
          {canCreate && <NewProject />}
        </>
      )}
      {editing && (
        <PortfolioEditor
          item={editing}
          users={editing.owner ? [editing.owner] : []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      )}
    </section>
  );
}

function ProjectDetails({
  item,
  canCreate,
  edit,
}: {
  item: PortfolioItem;
  canCreate: boolean;
  edit: () => void;
}) {
  const [preparing, setPreparing] = useState(false);
  const [failure, setFailure] = useState("");
  async function addFirstTask() {
    if (preparing) return;
    setPreparing(true);
    setFailure("");
    try {
      const registered = await portfolioApi.save(item, {
        version: item.version,
      });
      if (!registered.board_id)
        throw new Error("Não foi possível abrir o quadro do projeto.");
      navigate(`#/board/${registered.board_id}?newTask=1`);
    } catch (cause) {
      setFailure(error(cause));
    } finally {
      setPreparing(false);
    }
  }
  const health = healthOf(item);
  const canWrite = ["admin", "manager", "member"].includes(item.role ?? "");
  const canManage = ["admin", "manager"].includes(item.role ?? "");
  const changes = recentGitChanges([item], 30).slice(0, 20);
  const links = [
    ...item.links,
    ...(item.git?.url_github
      ? [{ label: "Código do projeto", url: item.git.url_github }]
      : []),
  ].flatMap((link) => {
    const url = urlSegura(link.url);
    return url ? [{ ...link, url }] : [];
  });
  return (
    <>
      <header className="projects-opening">
        <p className="projects-eyebrow">Projeto em acompanhamento</p>
        <h1>{item.name}</h1>
        <p>
          {item.description ||
            "Acompanhe as tarefas e os próximos passos deste projeto."}
        </p>
      </header>
      <div className="projects-actions">
        <a
          className="projects-read"
          href={
            item.project_id
              ? appHref(`#/request?projeto=${item.project_id}`)
              : appHref("#/request")
          }
        >
          Solicitar uma alteração →
        </a>
        {item.board_id && (
          <a
            className="projects-button"
            href={appHref(`#/board/${item.board_id}`)}
          >
            Abrir quadro de tarefas
          </a>
        )}
        {canWrite && item.board_id && (
          <a
            className="projects-button projects-button--outline"
            href={appHref(`#/board/${item.board_id}?newTask=1`)}
          >
            Adicionar tarefa
          </a>
        )}
        {(canManage || (canCreate && item.project_id === null)) && (
          <button className="quiet" onClick={edit}>
            Editar direção
          </button>
        )}
        {item.project_id && canManage && (
          <a
            className="projects-read"
            href={appHref(`#/projects/${item.project_id}/team`)}
          >
            Equipe do projeto
          </a>
        )}
      </div>
      {canCreate && !item.board_id && (
        <button
          className="projects-button"
          disabled={preparing}
          onClick={() => void addFirstTask()}
        >
          {preparing ? "Preparando quadro…" : "Adicionar tarefa"}
        </button>
      )}
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      <dl className="project-facts">
        <div>
          <dt>Prioridade</dt>
          <dd>{labelPriority[item.priority ?? "none"]}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <span className="project-status">
              {labelStatus[item.status ?? "none"]}
            </span>
          </dd>
        </div>
        <div>
          <dt>Responsáveis</dt>
          <dd>{item.owner?.name ?? "A definir"}</dd>
        </div>
        <div>
          <dt>Saúde</dt>
          <dd>
            <span className={`project-health project-health--${health.value}`}>
              {healthLabels[health.value]}
            </span>
            <small>{health.reason}</small>
          </dd>
        </div>
        <div>
          <dt>Próximo marco</dt>
          <dd>
            {item.milestone_title || "Marco a definir"}
            {item.milestone_due_date && (
              <small>Até {formatDate(item.milestone_due_date)}</small>
            )}
          </dd>
        </div>
        <div>
          <dt>Objetivo</dt>
          <dd>{item.objective || "Objetivo a definir"}</dd>
        </div>
      </dl>
      <div className="projects-section-title">
        <h2>Links</h2>
      </div>
      {links.length ? (
        <ul className="project-links">
          {links.map((link, index) => (
            <li key={`${link.url}:${index}`}>
              <a href={link.url} target="_blank" rel="noopener noreferrer">
                {link.label || link.url} ↗
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="projects-undefined">Nenhum link cadastrado.</p>
      )}
      <div className="projects-section-title">
        <h2>Pendências</h2>
        <span>{item.pending_tasks_total} tarefas em aberto</span>
      </div>
      {item.pending_tasks.length ? (
        <ol className="project-pending">
          {item.pending_tasks.map((task) => (
            <li key={task.id}>
              <a
                href={appHref(
                  `#/tasks/${task.id}${item.board_id ? `?board=${item.board_id}` : ""}`,
                )}
              >
                <span>{task.code}</span> {task.title}
              </a>
              <small>
                {task.due_date
                  ? `Prazo: ${formatDate(task.due_date)}`
                  : "Sem prazo definido"}
              </small>
            </li>
          ))}
        </ol>
      ) : (
        <p className="projects-undefined">Nenhuma pendência cadastrada.</p>
      )}
      {item.board_id &&
        item.pending_tasks_total > item.pending_tasks.length && (
          <a
            className="projects-read"
            href={appHref(`#/board/${item.board_id}`)}
          >
            Ver todas as tarefas →
          </a>
        )}
      <div className="projects-section-title">
        <h2>Linha do tempo</h2>
        <span>Últimos 30 dias</span>
      </div>
      {changes.length ? (
        <ol className="project-timeline">
          {changes.map((change) => (
            <li key={change.key}>
              <time dateTime={change.date}>{formatDate(change.date)}</time>
              <div>
                <span>
                  {change.kind === "release"
                    ? "Versão registrada"
                    : "Atualização"}
                </span>
                {change.title}
                {change.url && (
                  <a
                    href={change.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Ver registro ↗
                  </a>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="projects-undefined">
          Sem atualizações registradas neste período.
        </p>
      )}
      {item.git && (
        <a
          className="projects-read"
          href={appHref(`#/git/${encodeURIComponent(item.git.id)}`)}
        >
          Notícias do projeto →
        </a>
      )}
    </>
  );
}

function NewProject() {
  const [draft, setDraft] = useState({ name: "", key: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const request = useRef({ payload: "", key: "" });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = {
      name: draft.name.trim(),
      key: draft.key.trim().toUpperCase(),
      description: draft.description.trim() || null,
      legacy_app_id: null,
    };
    const payload = JSON.stringify(data);
    if (request.current.payload !== payload)
      request.current = { payload, key: crypto.randomUUID() };
    setBusy(true);
    setNotice("");
    try {
      const created = await backend.createProject(data, request.current.key);
      request.current = { payload: "", key: "" };
      navigate(`#/projects/${created.id}`);
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="projects-create">
      <summary>Novo projeto</summary>
      <form onSubmit={submit}>
        <div className="projects-create-grid">
          <label>
            Chave do projeto
            <input
              required
              pattern="[A-Z][A-Z0-9_]*"
              maxLength={32}
              placeholder="DEV"
              value={draft.key}
              onChange={(event) =>
                setDraft({ ...draft, key: event.target.value.toUpperCase() })
              }
            />
          </label>
          <label>
            Nome do projeto
            <input
              required
              maxLength={200}
              placeholder="Nome do projeto"
              value={draft.name}
              onChange={(event) =>
                setDraft({ ...draft, name: event.target.value })
              }
            />
          </label>
        </div>
        <label>
          Descrição
          <textarea
            maxLength={10000}
            value={draft.description}
            onChange={(event) =>
              setDraft({ ...draft, description: event.target.value })
            }
          />
        </label>
        {notice && (
          <p className="error" role="alert">
            {notice}
          </p>
        )}
        <button disabled={busy}>{busy ? "Criando…" : "Criar projeto"}</button>
      </form>
    </details>
  );
}
