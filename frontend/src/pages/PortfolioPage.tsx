import { appHref } from "../lib/navigation";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Flipped, Flipper } from "react-flip-toolkit";
import { api, backend, error as messageError } from "../api";
import { preparar, type EditorialCatalog } from "../lib/editorial";
import type { Mural } from "../types";
import type { Participant } from "../types";
import {
  formatDate,
  recentGitChanges,
  healthOf,
  labelPriority,
  labelStatus,
  portfolioApi,
  textoInclui,
  urlSegura,
  type PortfolioHealth,
  type PortfolioItem,
  type PortfolioPriority,
  type PortfolioStatus,
} from "../lib/portfolio";
import "./PortfolioPage.css";

type Filters = {
  search: string;
  priority: string;
  health: string;
  area: string;
  status: string;
  owner: string;
};
type Draft = {
  priority: PortfolioPriority | "";
  status: PortfolioStatus | "";
  owner_id: string;
  due_date: string;
  objective: string;
  milestone_title: string;
  milestone_due_date: string;
  links: string;
};
const columns: Array<[PortfolioPriority | "none" | "completed", string]> = [
  ["high", "Alta"],
  ["medium", "Média"],
  ["low", "Baixa"],
  ["none", "Sem prioridade"],
  ["completed", "Finalizados"],
];
const newDraft = (item: PortfolioItem): Draft => ({
  priority: item.priority ?? "",
  status: item.status ?? "",
  owner_id: String(item.owner?.id ?? ""),
  due_date: item.due_date?.slice(0, 10) ?? "",
  objective: item.objective ?? "",
  milestone_title: item.milestone_title ?? "",
  milestone_due_date: item.milestone_due_date?.slice(0, 10) ?? "",
  links: item.links.map((link) => `${link.label} | ${link.url}`).join("\n"),
});
const healthLabels: Record<PortfolioHealth, string> = {
  finalizado: "Finalizado",
  atraso: "Em atraso",
  critico: "Crítico",
  aguardando: "Aguardando",
  "a-definir": "A definir",
  "em-dia": "Em dia",
};

function Card({
  item,
  edit,
  draggingDisabled,
  reducedMotion,
}: {
  item: PortfolioItem;
  edit: (item: PortfolioItem) => void;
  draggingDisabled: boolean;
  reducedMotion: boolean;
}) {
  const health = healthOf(item);
  const canEdit = item.role === "admin" || item.role === "manager";
  return (
    <Flipped flipId={`portfolio-${item.ref}`} shouldFlip={() => !reducedMotion}>
      <article
        className={`portfolio-card portfolio-card--${health.value}`}
        data-flip-id={`portfolio-${item.ref}`}
        draggable={!draggingDisabled && canEdit}
        onDragStartCapture={(event) => {
          event.dataTransfer.setData("text/plain", item.ref);
          event.dataTransfer.effectAllowed = "move";
        }}
      >
        <div className="portfolio-card__top">
          <span
            title={health.reason}
            className={`portfolio-health portfolio-health--${health.value}`}
          >
            {healthLabels[health.value]}
          </span>
          {item.status && (
            <span className="portfolio-status">{labelStatus[item.status]}</span>
          )}
          {canEdit && (
            <button
              className="quiet"
              disabled={draggingDisabled}
              onClick={() => edit(item)}
              aria-label={`Editar ${item.name}`}
            >
              Editar
            </button>
          )}
        </div>
        <h3 className="portfolio-card__title">{item.name}</h3>
        <p className="portfolio-card__summary">
          {item.objective || item.description || "Objetivo a definir."}
        </p>
        {health.value !== "a-definir" &&
          health.value !== "finalizado" &&
          health.value !== "em-dia" && (
            <p className="portfolio-card__reason">{health.reason}</p>
          )}
        <div className="portfolio-card__data">
          <div>
            <span>Responsável</span>
            <b>{item.owner?.name || "A definir"}</b>
          </div>
          <div>
            <span>Entrega</span>
            <b>{item.due_date ? formatDate(item.due_date) : "A definir"}</b>
          </div>
          {item.milestone_title && (
            <div>
              <span>Próximo marco</span>
              <b>
                {item.milestone_title}
                {item.milestone_due_date
                  ? ` · ${formatDate(item.milestone_due_date)}`
                  : ""}
              </b>
            </div>
          )}
        </div>
        <div className="portfolio-card__footer">
          <a
            href={
              item.project_id !== null
                ? appHref(`#/projects/${item.project_id}`)
                : item.git
                  ? appHref(`#/projects/git/${encodeURIComponent(item.git.id)}`)
                  : appHref("#/projects")
            }
          >
            Acompanhar projeto →
          </a>
          {item.board_id && (
            <a href={appHref(`#/board/${item.board_id}`)}>Quadro</a>
          )}
          {item.git && (
            <a href={appHref(`#/git/${encodeURIComponent(item.git.id)}`)}>
              Histórico Git
            </a>
          )}
        </div>
        {item.git?.erro && (
          <small>Coleta Git indisponível neste projeto.</small>
        )}
        {item.links
          .filter((link) => urlSegura(link.url))
          .map((link, index) => (
            <a
              className="portfolio-external-link"
              key={index}
              href={urlSegura(link.url)!}
              target="_blank"
              rel="noopener noreferrer"
            >
              {link.label} ↗
            </a>
          ))}
        {item.pending_tasks_total > 0 && (
          <details className="portfolio-pending">
            <summary>
              {item.pending_tasks_total} pendência
              {item.pending_tasks_total === 1 ? "" : "s"}
            </summary>
            <ul>
              {item.pending_tasks.map((task) => (
                <li key={task.id}>
                  <a
                    href={appHref(
                      `#/tasks/${task.id}?board=${item.board_id ?? ""}`,
                    )}
                  >
                    {task.code} · {task.title}
                  </a>
                </li>
              ))}
            </ul>
            {item.pending_tasks_total > item.pending_tasks.length && (
              <small>
                Mostrando {item.pending_tasks.length} de{" "}
                {item.pending_tasks_total}. Consulte o quadro completo.
              </small>
            )}
          </details>
        )}
      </article>
    </Flipped>
  );
}

export function PortfolioEditor({
  item,
  users,
  onClose,
  onSaved,
}: {
  item: PortfolioItem;
  users: Participant[];
  onClose: () => void;
  onSaved: (item: PortfolioItem) => void;
}) {
  const [draft, setDraft] = useState(() => newDraft(item));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [current, setCurrent] = useState(item);
  const [conflicted, setConflicted] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [eligible, setEligible] = useState<Participant[]>(users);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    return () => {
      element.close();
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    if (item.project_id === null) return;
    void backend
      .assignees(item.project_id)
      .then(setEligible)
      .catch(() => setEligible(users));
  }, [item.project_id, users]);
  async function reloadCurrent() {
    setBusy(true);
    try {
      const data = await portfolioApi.list();
      const latest = data.items.find(
        (value) =>
          value.ref === item.ref ||
          (item.project_id !== null && value.project_id === item.project_id),
      );
      if (!latest) throw new Error("Projeto ausente");
      setCurrent(latest);
      setConflicted(false);
      setReviewed(true);
      setNotice(
        "Dados atuais carregados. Seu rascunho foi mantido; compare os valores abaixo antes de salvar.",
      );
    } catch (failure) {
      setNotice(messageError(failure));
    } finally {
      setBusy(false);
    }
  }
  const change = (key: keyof Draft, value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || conflicted) return;
    setNotice("");
    const links = draft.links
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [label, ...rest] = line.split("|");
        const url = rest.join("|").trim() || label.trim();
        return { label: rest.length ? label.trim() : url, url };
      });
    if (links.some((link) => !urlSegura(link.url))) {
      setNotice("Use apenas links http(s), um por linha.");
      return;
    }
    setBusy(true);
    try {
      const saved = await portfolioApi.save(current, {
        version: current.version,
        priority: draft.priority || null,
        status: draft.status || null,
        owner_id: draft.owner_id ? Number(draft.owner_id) : null,
        due_date: draft.due_date || null,
        objective: draft.objective || null,
        milestone_title: draft.milestone_title || null,
        milestone_due_date: draft.milestone_due_date || null,
        links,
      });
      onSaved(saved);
    } catch (failure: unknown) {
      const conflict =
        typeof failure === "object" &&
        failure !== null &&
        "response" in failure &&
        (failure as { response?: { status?: number } }).response?.status ===
          409;
      setNotice(
        conflict
          ? "Este cartão foi alterado por outra pessoa. Seu rascunho foi preservado; recarregue antes de salvar."
          : messageError(failure),
      );
      setConflicted(conflict);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="portfolio-modal"
      aria-labelledby="portfolio-editor-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <section className="portfolio-editor">
        <div className="portfolio-editor__head">
          <h2 id="portfolio-editor-title">Editar projeto</h2>
          <button className="quiet" onClick={onClose} disabled={busy}>
            Fechar
          </button>
        </div>
        <p>{item.name}</p>
        {notice && (
          <div className="portfolio-editor__notice" role="alert">
            {notice}
            {conflicted && (
              <button
                className="quiet"
                disabled={busy}
                onClick={() => void reloadCurrent()}
              >
                Recarregar dados
              </button>
            )}
          </div>
        )}
        {reviewed && (
          <div className="portfolio-current-values">
            <strong>Valores atuais salvos</strong>
            <p>
              {labelPriority[current.priority ?? "none"]} ·{" "}
              {labelStatus[current.status ?? "none"]} ·{" "}
              {current.owner?.name ?? "Sem responsável"} ·{" "}
              {formatDate(current.due_date)}
            </p>
            <p>Objetivo: {current.objective || "A definir"}</p>
            <p>
              Marco: {current.milestone_title || "A definir"} ·{" "}
              {formatDate(current.milestone_due_date)}
            </p>
            <p>
              Links:{" "}
              {current.links
                .map((link) => `${link.label}: ${link.url}`)
                .join("; ") || "Nenhum"}
            </p>
          </div>
        )}
        <form onSubmit={submit}>
          <fieldset disabled={busy} className="portfolio-form-fields">
            <div className="portfolio-editor__grid">
              <label>
                Prioridade
                <select
                  value={draft.priority}
                  onChange={(e) => change("priority", e.target.value)}
                >
                  <option value="">A definir</option>
                  <option value="high">Alta</option>
                  <option value="medium">Média</option>
                  <option value="low">Baixa</option>
                </select>
              </label>
              <label>
                Status
                <select
                  value={draft.status}
                  onChange={(e) => change("status", e.target.value)}
                >
                  <option value="">A definir</option>
                  <option value="planned">Planejado</option>
                  <option value="in_progress">Em andamento</option>
                  <option value="waiting">Aguardando</option>
                  <option value="completed">Finalizado</option>
                </select>
              </label>
              <label>
                Responsável
                <select
                  value={draft.owner_id}
                  onChange={(e) => change("owner_id", e.target.value)}
                >
                  <option value="">Sem responsável</option>
                  {item.owner &&
                    !eligible.some((user) => user.id === item.owner!.id) && (
                      <option value={item.owner.id}>
                        {item.owner.name} (indisponível)
                      </option>
                    )}
                  {eligible.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name} · {user.email}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Prazo
                <input
                  type="date"
                  value={draft.due_date}
                  onChange={(e) => change("due_date", e.target.value)}
                />
              </label>
              <label>
                Próximo marco
                <input
                  value={draft.milestone_title}
                  maxLength={200}
                  onChange={(e) => change("milestone_title", e.target.value)}
                />
              </label>
              <label>
                Data do marco
                <input
                  type="date"
                  value={draft.milestone_due_date}
                  onChange={(e) => change("milestone_due_date", e.target.value)}
                />
              </label>
            </div>
            <label>
              Objetivo
              <textarea
                value={draft.objective}
                maxLength={10000}
                onChange={(e) => change("objective", e.target.value)}
              />
            </label>
            <label>
              Links <small>Um por linha: rótulo | https://…</small>
              <textarea
                value={draft.links}
                onChange={(e) => change("links", e.target.value)}
              />
            </label>
            <div className="portfolio-editor__actions">
              <button
                type="button"
                className="quiet"
                onClick={onClose}
                disabled={busy}
              >
                Cancelar
              </button>
              <button disabled={busy || conflicted}>
                {busy ? "Salvando…" : "Salvar alterações"}
              </button>
            </div>
          </fieldset>
        </form>
      </section>
    </dialog>
  );
}

export default function PortfolioPage() {
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const [items, setItems] = useState<PortfolioItem[] | null>(null);
  const [users, setUsers] = useState<Participant[]>([]);
  const [collectedAt, setCollectedAt] = useState("");
  const [failure, setFailure] = useState("");
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const [filters, setFilters] = useState<Filters>({
    search: "",
    priority: "",
    health: "",
    area: "",
    status: "",
    owner: "",
  });
  const [editing, setEditing] = useState<PortfolioItem | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [moving, setMoving] = useState<string | null>(null);
  const [activityDays, setActivityDays] = useState<7 | 15 | 30>(7);
  const loadVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    setRefreshing(true);
    setFailure("");
    try {
      const [data, catalog] = await Promise.all([
        portfolioApi.list(),
        api
          .get<EditorialCatalog>("api/editorial.json")
          .then((response) => response.data),
      ]);
      if (version !== loadVersion.current) return;
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
          const contextual = item.git ? apps.get(item.git.id) : undefined;
          return contextual && item.git
            ? {
                ...item,
                name:
                  item.name === item.git.nome
                    ? contextual.nomeEditorial
                    : item.name,
                description: item.description ?? contextual.descricaoEditorial,
                git: { ...item.git, areas: contextual.areas },
              }
            : item;
        }),
      );
      setUsers([
        ...new Map(
          data.items
            .filter((item) => item.owner)
            .map((item) => [item.owner!.id, item.owner!] as const),
        ).values(),
      ]);
      setCollectedAt(data.git_collected_at);
    } catch (cause) {
      if (version === loadVersion.current) setFailure(messageError(cause));
    } finally {
      if (version === loadVersion.current) setRefreshing(false);
    }
  }, []);
  useEffect(() => {
    void load();
    return () => {
      loadVersion.current += 1;
    };
  }, [load]);
  const areas = useMemo(
    () =>
      [
        ...new Set((items ?? []).flatMap((item) => item.git?.areas ?? [])),
      ].sort(),
    [items],
  );
  const visible = useMemo(
    () =>
      (items ?? []).filter((item) => {
        const health = healthOf(item);
        const area = item.git?.areas ?? [];
        return (
          textoInclui(
            [
              item.name,
              item.description,
              item.objective,
              item.owner?.name,
              area.join(" "),
            ]
              .filter(Boolean)
              .join(" "),
            filters.search,
          ) &&
          (!filters.priority ||
            (item.priority ?? "none") === filters.priority) &&
          (!filters.status || (item.status ?? "none") === filters.status) &&
          (!filters.health || health.value === filters.health) &&
          (!filters.area || area.includes(filters.area)) &&
          (!filters.owner || String(item.owner?.id ?? "none") === filters.owner)
        );
      }),
    [items, filters],
  );
  const activity = recentGitChanges(visible, activityDays);

  const activityByDay = new Map<string, typeof activity>();
  const localDay = new Intl.DateTimeFormat("fr-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  for (const entry of activity) {
    const day = localDay.format(new Date(entry.date));
    activityByDay.set(day, [...(activityByDay.get(day) ?? []), entry]);
  }

  function replaceItem(updated: PortfolioItem) {
    loadVersion.current += 1;
    setRefreshing(false);
    setItems(
      (current) =>
        current?.map((item) =>
          item.ref === updated.ref
            ? {
                ...updated,
                name: item.name,
                description: updated.description ?? item.description,
                git: updated.git
                  ? { ...updated.git, areas: item.git?.areas }
                  : null,
              }
            : item,
        ) ?? [],
    );
  }
  async function move(ref: string, column: (typeof columns)[number][0]) {
    if (moving || refreshing || editing) return;
    const item = items?.find((value) => value.ref === ref);
    if (!item || !["admin", "manager"].includes(item.role ?? "")) return;
    const currentColumn =
      item.status === "completed" ? "completed" : (item.priority ?? "none");
    if (currentColumn === column) return;
    setMoving(ref);
    setFailure("");
    try {
      const updated = await portfolioApi.save(
        item,
        column === "completed"
          ? { version: item.version, status: "completed" }
          : {
              version: item.version,
              priority: column === "none" ? null : column,
              status: item.status === "completed" ? "in_progress" : item.status,
            },
      );
      replaceItem(updated);
    } catch (failure) {
      await load();
      setFailure(`Não foi possível mover o projeto. ${messageError(failure)}`);
    } finally {
      setMoving(null);
    }
  }
  if (!items && !failure)
    return (
      <section className="portfolio-page">
        <div
          className="portfolio-content"
          role="region"
          aria-label="Lista de prioridades"
          tabIndex={0}
        >
          <div
            className="portfolio-skeleton"
            role="status"
            aria-label="Carregando projetos"
          >
            <i />
            <i />
            <i />
          </div>
        </div>
      </section>
    );
  if (!items)
    return (
      <section className="portfolio-page">
        <div
          className="portfolio-content"
          role="region"
          aria-label="Lista de prioridades"
          tabIndex={0}
        >
          <section className="portfolio-error" role="alert">
            <h1>Não foi possível carregar o painel</h1>
            <p>{failure}</p>
            <button onClick={() => void load()}>Tentar novamente</button>
          </section>
        </div>
      </section>
    );
  const set = (key: keyof Filters, value: string) =>
    setFilters((current) => ({ ...current, [key]: value }));
  const save = (updated: PortfolioItem) => {
    replaceItem(updated);
    setEditing(null);
  };
  return (
    <section className="portfolio-page">
      <section className="requests-entry" aria-label="Solicitações da equipe">
        <p>Para avaliar</p>
        <h2>Solicitações da equipe</h2>
        <a href={appHref("#/requests")} className="projects-button">
          Ver solicitações
        </a>
      </section>
      <div className="portfolio-controls">
        <section className="portfolio-opening">
          <p>Direção da equipe</p>
          <div className="portfolio-opening__head">
            <h1>Quadro de projetos.</h1>
            <div className="portfolio-opening__actions">
              <a href={appHref("#/projects")}>Criar projeto novo →</a>
              <button
                className="portfolio-refresh"
                disabled={refreshing || !!moving}
                onClick={() => void load()}
              >
                {refreshing ? "Atualizando…" : "Atualizar painel"}
              </button>
            </div>
          </div>
          <span>
            Cada projeto com suas últimas atualizações, responsáveis, status,
            resumo e pendências, na ordem de prioridade.
          </span>
        </section>
        {failure && (
          <aside className="portfolio-error" role="alert">
            <p>Não foi possível atualizar os dados. {failure}</p>
            <button onClick={() => void load()}>Tentar novamente</button>
          </aside>
        )}
        <div className="portfolio-filter-panel">
          <div className="portfolio-filter-panel__body">
            <section
              className="portfolio-filters"
              aria-label="Filtros do painel"
            >
              <label>
                Busca
                <input
                  type="search"
                  value={filters.search}
                  onChange={(e) => set("search", e.target.value)}
                  placeholder="Projeto, objetivo ou pessoa"
                />
              </label>
              <label>
                Prioridade
                <select
                  value={filters.priority}
                  onChange={(e) => set("priority", e.target.value)}
                >
                  <option value="">Todas</option>
                  <option value="high">Alta</option>
                  <option value="medium">Média</option>
                  <option value="low">Baixa</option>
                  <option value="none">Sem prioridade</option>
                </select>
              </label>
              <label>
                Área
                <select
                  value={filters.area}
                  onChange={(e) => set("area", e.target.value)}
                >
                  <option value="">Todas</option>
                  {areas.map((area) => (
                    <option key={area}>{area}</option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select
                  value={filters.status}
                  onChange={(e) => set("status", e.target.value)}
                >
                  <option value="">Todos</option>
                  {Object.entries(labelStatus).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Responsável
                <select
                  value={filters.owner}
                  onChange={(e) => set("owner", e.target.value)}
                >
                  <option value="">Todos</option>
                  <option value="none">Sem responsável</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="quiet"
                onClick={() =>
                  setFilters({
                    search: "",
                    priority: "",
                    health: "",
                    area: "",
                    status: "",
                    owner: "",
                  })
                }
              >
                Limpar filtros
              </button>
            </section>
            <div className="portfolio-summary" aria-label="Resumo">
              {(["high", "medium", "low"] as const).map((priority) => (
                <button
                  key={priority}
                  className={`portfolio-chip portfolio-chip--${priority}`}
                  aria-pressed={filters.priority === priority}
                  onClick={() =>
                    set(
                      "priority",
                      filters.priority === priority ? "" : priority,
                    )
                  }
                >
                  {labelPriority[priority]}{" "}
                  <b>
                    {items.filter((item) => item.priority === priority).length}
                  </b>
                </button>
              ))}
              {Object.entries(healthLabels).map(([key, label]) => (
                <button
                  key={key}
                  aria-pressed={filters.health === key}
                  className={`portfolio-chip portfolio-chip--${key}`}
                  onClick={() =>
                    set("health", filters.health === key ? "" : key)
                  }
                >
                  {label}{" "}
                  <b>
                    {
                      items.filter((item) => healthOf(item).value === key)
                        .length
                    }
                  </b>
                </button>
              ))}
            </div>
          </div>
        </div>
        {moving && <p role="status">Salvando a mudança de prioridade…</p>}
        {visible.some((item) => item.git?.erro) && (
          <p className="portfolio-git-warning" role="status">
            A última coleta do Git teve falhas em alguns projetos; os dados
            disponíveis foram mantidos.
          </p>
        )}
      </div>
      <div className="portfolio-toolbar">
        <h2>Projetos</h2>
        <p>
          {visible.length} {visible.length === 1 ? "projeto" : "projetos"} no
          recorte · Git coletado em {formatDate(collectedAt)}
        </p>
        <div role="group" aria-label="Modo de visualização">
          <button
            aria-pressed={view === "kanban"}
            className={
              view === "kanban"
                ? "portfolio-mode portfolio-mode--active"
                : "portfolio-mode"
            }
            onClick={() => setView("kanban")}
          >
            Kanban
          </button>
          <button
            aria-pressed={view === "table"}
            className={
              view === "table"
                ? "portfolio-mode portfolio-mode--active"
                : "portfolio-mode"
            }
            onClick={() => setView("table")}
          >
            Tabela
          </button>
        </div>
      </div>
      <div
        className="portfolio-content"
        role="region"
        aria-label="Lista de prioridades"
        tabIndex={0}
      >
        <section
          className="portfolio-activity"
          aria-label="Atividade Git recente"
        >
          <details open>
            <summary className="sr-only">Entregas recentes</summary>
            <div className="portfolio-activity__body">
              <div className="portfolio-activity__header">
                <h2>Entregas dos últimos {activityDays} dias</h2>
                <div role="group" aria-label="Período de atividade">
                  {([7, 15, 30] as const).map((days) => (
                    <button
                      key={days}
                      aria-pressed={activityDays === days}
                      className="portfolio-mode"
                      onClick={() => setActivityDays(days)}
                    >
                      {days} dias
                    </button>
                  ))}
                </div>
              </div>
              <p>
                {activity.length} registro{activity.length === 1 ? "" : "s"} nos
                projetos filtrados · origem Git · coleta{" "}
                {formatDate(collectedAt)}.
              </p>
              <small>
                Releases e commits registrados no repositório; não indicam
                implantação em produção.
              </small>
              {activity.length ? (
                <ol className="portfolio-activity__list">
                  {[...activityByDay].map(([day, entries]) => (
                    <li className="portfolio-activity__day" key={day}>
                      <div className="portfolio-activity__date">
                        <time dateTime={day}>{formatDate(day)}</time>
                        <span>
                          {entries.length}{" "}
                          {entries.length === 1 ? "entrega" : "entregas"}
                        </span>
                      </div>
                      <ul className="portfolio-activity__entries">
                        {entries.map((entry) => (
                          <li key={entry.key}>
                            <a
                              href={appHref(
                                `#/git/${encodeURIComponent(entry.appId)}`,
                              )}
                            >
                              {entry.projectName}
                            </a>
                            <span className="portfolio-activity__kind">
                              {entry.kind === "release" ? "Release" : "Commit"}
                            </span>
                            <span>{entry.title}</span>
                            {entry.url && (
                              <a
                                href={entry.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                ver ↗
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>
                  Nenhum registro nesta janela. Experimente ampliar o período.
                </p>
              )}
            </div>
          </details>
        </section>
        {!visible.length ? (
          <section className="portfolio-empty">
            <h2>Nenhum projeto neste recorte</h2>
            <p>
              Ajuste os filtros. Se ainda não tiver acesso, solicite um vínculo
              ao administrador ou gestor.
            </p>
            <button
              onClick={() =>
                setFilters({
                  search: "",
                  priority: "",
                  health: "",
                  area: "",
                  status: "",
                  owner: "",
                })
              }
            >
              Limpar filtros
            </button>
          </section>
        ) : view === "kanban" ? (
          <div className="portfolio-lanes">
            <Flipper
              flipKey={visible
                .map((item) => `${item.ref}:${item.status}:${item.priority}`)
                .join("|")}
              spring={{ stiffness: 280, damping: 26 }}
            >
              <div
                className="portfolio-kanban"
                role="region"
                aria-label="Quadro de projetos"
              >
                {columns.map(([key, title]) => {
                  const cards = visible.filter((item) =>
                    key === "completed"
                      ? item.status === "completed"
                      : (item.priority ?? "none") === key &&
                        item.status !== "completed",
                  );
                  return (
                    <section
                      className={`portfolio-column portfolio-column--${key}`}
                      key={key}
                      aria-label={`Prioridade ${title}`}
                      onDragOver={(event) => {
                        if (
                          !moving &&
                          !refreshing &&
                          visible.some(
                            (item) =>
                              item.role === "admin" || item.role === "manager",
                          )
                        )
                          event.preventDefault();
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        void move(
                          event.dataTransfer.getData("text/plain"),
                          key,
                        );
                      }}
                    >
                      <header className="portfolio-column__header">
                        <h2>{title}</h2>
                        <span>{cards.length}</span>
                      </header>
                      {cards.length ? (
                        <div className="portfolio-column__cards">
                          {cards.map((item) => (
                            <Card
                              key={item.ref}
                              item={item}
                              edit={setEditing}
                              draggingDisabled={!!moving || refreshing}
                              reducedMotion={reducedMotion}
                            />
                          ))}
                        </div>
                      ) : (
                        <p>Nenhum projeto</p>
                      )}
                    </section>
                  );
                })}
              </div>
            </Flipper>
          </div>
        ) : (
          <div className="portfolio-table-wrap">
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th className="portfolio-table__corner" />
                  {visible.map((item) => {
                    const health = healthOf(item);
                    return (
                      <th
                        className="portfolio-table__project"
                        key={item.ref}
                        scope="col"
                      >
                        <span
                          className={`portfolio-priority portfolio-priority--${item.priority ?? "none"}`}
                        >
                          {labelPriority[item.priority ?? "none"]}
                        </span>
                        <span
                          className={`portfolio-health portfolio-health--${health.value}`}
                          title={health.reason}
                        >
                          {healthLabels[health.value]}
                        </span>
                        <a
                          className="portfolio-table__project-link"
                          href={
                            item.project_id !== null
                              ? appHref(`#/projects/${item.project_id}`)
                              : item.git
                                ? appHref(
                                    `#/projects/git/${encodeURIComponent(item.git.id)}`,
                                  )
                                : appHref("#/projects")
                          }
                        >
                          {item.name}
                        </a>
                        <small>
                          {item.git?.erro
                            ? "Git sem atualização"
                            : item.git
                              ? "Origem Git"
                              : "Origem quadro"}
                        </small>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Responsável</th>
                  {visible.map((item) => (
                    <td key={item.ref}>{item.owner?.name ?? "A definir"}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Status</th>
                  {visible.map((item) => (
                    <td key={item.ref}>{labelStatus[item.status ?? "none"]}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Objetivo</th>
                  {visible.map((item) => (
                    <td key={item.ref}>
                      {item.objective || item.description || "A definir"}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Prazo</th>
                  {visible.map((item) => (
                    <td key={item.ref}>{formatDate(item.due_date)}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Pendências</th>
                  {visible.map((item) => (
                    <td key={item.ref}>
                      {item.pending_tasks_total ? (
                        <a
                          href={
                            item.pending_tasks[0]
                              ? appHref(
                                  `#/tasks/${item.pending_tasks[0].id}?board=${item.board_id ?? ""}`,
                                )
                              : appHref("#/tasks")
                          }
                        >
                          {item.pending_tasks_total} aberta
                          {item.pending_tasks_total === 1 ? "" : "s"}
                        </a>
                      ) : (
                        "Nenhuma"
                      )}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">Ações</th>
                  {visible.map((item) => (
                    <td key={item.ref}>
                      {(item.role === "admin" || item.role === "manager") && (
                        <button
                          className="quiet"
                          disabled={!!moving || refreshing}
                          onClick={() => setEditing(item)}
                        >
                          Editar
                        </button>
                      )}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
      {editing && (editing.role === "admin" || editing.role === "manager") && (
        <PortfolioEditor
          key={editing.ref}
          item={editing}
          users={users}
          onClose={() => setEditing(null)}
          onSaved={save}
        />
      )}
    </section>
  );
}
