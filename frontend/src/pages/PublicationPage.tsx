import { FormEvent, useEffect, useRef, useState } from "react";
import { api, error } from "../api";
import type {
  PublicationDetail,
  PublicationNews,
  PublicationProject,
} from "../lib/public";
import type { User } from "../types";
import "./PublicationPage.css";

const root = "api/v1/publication";
const statuses = ["planned", "in_progress", "waiting"] as const;
const names: Record<string, string> = {
  planned: "Planejado",
  in_progress: "Em andamento",
  waiting: "Aguardando",
  completed: "Concluído",
};
const manager = {
  projects: () =>
    api
      .get<{ items: PublicationProject[] }>(`${root}/projects`)
      .then((r) => r.data.items),
  project: (id: number) =>
    api.get<PublicationDetail>(`${root}/projects/${id}`).then((r) => r.data),
  saveProject: (
    id: number,
    data: {
      name: string;
      summary: string | null;
      published: boolean;
      version: number;
    },
  ) => api.put(`${root}/projects/${id}`, data),
  saveTask: (
    id: number,
    data: {
      title: string;
      summary: string | null;
      published: boolean;
      version: number;
    },
  ) => api.put(`${root}/tasks/${id}`, data),
  saveColumn: (id: number, status: string) =>
    api.put(`${root}/columns/${id}`, { status }),
  news: () =>
    api
      .get<{ items: PublicationNews[] }>(`${root}/news`)
      .then((r) => r.data.items),
  saveNews: (data: PublicationNews) => {
    const body = {
      title: data.title,
      summary: data.summary,
      body: data.body || "",
      project_id: data.project_id,
      published: data.published,
    };
    return data.id
      ? api.put(`${root}/news/${data.id}`, { ...body, version: data.version })
      : api.post(`${root}/news`, body);
  },
};
const blankNews = (): PublicationNews => ({
  id: 0,
  title: "",
  summary: null,
  body: "",
  project_name: null,
  project_id: null,
  published: false,
  published_at: null,
  version: 0,
});

export function PublicationPage({ user }: { user: User }) {
  const [projects, setProjects] = useState<PublicationProject[] | null>(null);
  const [selected, setSelected] = useState<PublicationDetail | null>(null);
  const [news, setNews] = useState<PublicationNews[] | null>(null);
  const [draft, setDraft] = useState(blankNews);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const allowed =
    user.global_role === "admin" ||
    Boolean(projects?.some((item) => item.can_publish));
  const load = async () => {
    setBusy(true);
    setNotice("");
    try {
      const [items, editorial] = await Promise.all([
        manager.projects(),
        manager.news(),
      ]);
      setProjects(items);
      setNews(editorial);
      if (user.global_role !== "admin") {
        const permitted = items.find((item) => item.can_publish);
        if (permitted)
          setDraft((current) =>
            current.id || current.project_id
              ? current
              : { ...current, project_id: permitted.id },
          );
      }
    } catch (cause) {
      setProjects([]);
      setNews([]);
      setNotice(error(cause));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const select = async (id: number) => {
    const current = ++generation.current;
    setBusy(true);
    setNotice("");
    try {
      const detail = await manager.project(id);
      if (current === generation.current) setSelected(detail);
    } catch (cause) {
      if (current === generation.current) setNotice(error(cause));
    } finally {
      if (current === generation.current) setBusy(false);
    }
  };
  const refresh = async (id: number) => {
    const detail = await manager.project(id);
    if (selected?.project.id === id) setSelected(detail);
  };
  async function saveProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await manager.saveProject(selected.project.id, {
        name: String(form.get("name")).trim(),
        summary: String(form.get("summary")).trim() || null,
        published: form.get("published") === "on",
        version: selected.project.version,
      });
      await refresh(selected.project.id);
      setNotice("Projeto atualizado.");
    } catch (cause) {
      setNotice(error(cause));
    } finally {
      setBusy(false);
    }
  }
  async function saveTask(
    event: FormEvent<HTMLFormElement>,
    task: PublicationDetail["tasks"][number],
  ) {
    event.preventDefault();
    if (!selected || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await manager.saveTask(task.id, {
        title: String(form.get("title")).trim(),
        summary: String(form.get("summary")).trim() || null,
        published: form.get("published") === "on",
        version: task.version,
      });
      await refresh(selected.project.id);
      setNotice("Entrega atualizada.");
    } catch (cause) {
      setNotice(error(cause));
    } finally {
      setBusy(false);
    }
  }
  async function updateColumn(id: number, status: string) {
    if (!selected || busy) return;
    const projectId = selected.project.id;
    setBusy(true);
    try {
      await manager.saveColumn(id, status);
      await refresh(projectId);
    } catch (cause) {
      setNotice(error(cause));
    } finally {
      setBusy(false);
    }
  }
  async function saveNews(event: FormEvent) {
    event.preventDefault();
    if (
      busy ||
      !draft.title.trim() ||
      !draft.body?.trim() ||
      (user.global_role !== "admin" && !draft.project_id)
    ) {
      setNotice(
        user.global_role !== "admin" && !draft.project_id
          ? "Escolha um projeto permitido para publicar a notícia."
          : "Informe título e texto da notícia.",
      );
      return;
    }
    setBusy(true);
    try {
      await manager.saveNews({
        ...draft,
        title: draft.title.trim(),
        body: draft.body.trim(),
        summary: draft.summary?.trim() || null,
      });
      setNews(await manager.news());
      setDraft(
        user.global_role === "admin"
          ? blankNews()
          : { ...blankNews(), project_id: choices[0]?.id || null },
      );
      setNotice("Notícia atualizada.");
    } catch (cause) {
      setNotice(error(cause));
    } finally {
      setBusy(false);
    }
  }
  if (projects === null)
    return (
      <section className="publication-page">
        <div className="publication-skeleton" role="status">
          <i />
          <i />
          <i />
        </div>
      </section>
    );
  if (!allowed)
    return (
      <section className="publication-page">
        <div className="publication-message" role="alert">
          <h1>Publicação indisponível</h1>
          <p>{notice || "Você não tem permissão para publicar conteúdo."}</p>
          <button disabled={busy} onClick={() => void load()}>
            Tentar novamente
          </button>
        </div>
      </section>
    );
  const choices = projects.filter(
    (item) => user.global_role === "admin" || item.can_publish,
  );
  return (
    <section className="publication-page">
      <header className="publication-header">
        <p>Portal público</p>
        <h1>Publicação</h1>
        <span>Controle o que aparece no acompanhamento e nas notícias.</span>
      </header>
      {notice && (
        <p className="publication-message" role="status">
          {notice}
        </p>
      )}
      <div className="publication-layout">
        <aside>
          <h2>Projetos</h2>
          {choices.map((item) => (
            <button
              key={item.id}
              className={
                selected?.project.id === item.id
                  ? "publication-project active"
                  : "publication-project"
              }
              disabled={busy}
              onClick={() => void select(item.id)}
            >
              {item.name}
            </button>
          ))}
        </aside>
        <div>
          {selected ? (
            <>
              <form
                key={`${selected.project.id}-${selected.project.version}`}
                className="publication-form"
                onSubmit={(event) => void saveProject(event)}
              >
                <h2>Projeto</h2>
                <label>
                  Nome
                  <input
                    name="name"
                    defaultValue={selected.project.name}
                    disabled={busy}
                    required
                  />
                </label>
                <label>
                  Resumo
                  <textarea
                    name="summary"
                    defaultValue={selected.project.summary || ""}
                    disabled={busy}
                  />
                </label>
                <label className="publication-check">
                  <input
                    name="published"
                    type="checkbox"
                    defaultChecked={selected.project.published}
                    disabled={busy}
                  />{" "}
                  Publicar projeto no portal
                </label>
                <button disabled={busy}>Salvar projeto</button>
              </form>
              <section className="publication-columns">
                <h2>Status das colunas</h2>
                {selected.columns.map((column) => (
                  <label key={`${column.id}-${column.status}`}>
                    {column.name}
                    <select
                      value={
                        column.is_done
                          ? "completed"
                          : column.status || "planned"
                      }
                      disabled={busy || column.is_done}
                      onChange={(event) =>
                        void updateColumn(column.id, event.target.value)
                      }
                    >
                      <option
                        value={
                          column.is_done
                            ? "completed"
                            : column.status || "planned"
                        }
                      >
                        {
                          names[
                            column.is_done
                              ? "completed"
                              : column.status || "planned"
                          ]
                        }
                      </option>
                      {!column.is_done &&
                        statuses
                          .filter((status) => status !== column.status)
                          .map((status) => (
                            <option key={status} value={status}>
                              {names[status]}
                            </option>
                          ))}
                    </select>
                  </label>
                ))}
              </section>
              <section className="publication-tasks">
                <h2>Entregas</h2>
                {selected.tasks.map((task) => (
                  <form
                    key={`${task.id}-${task.version}`}
                    className="publication-task"
                    onSubmit={(event) => void saveTask(event, task)}
                  >
                    <small>
                      {task.code} · interno: {task.internal_title}
                    </small>
                    <label>
                      Título público
                      <input
                        name="title"
                        defaultValue={task.title || ""}
                        disabled={busy}
                        required
                      />
                    </label>
                    <label>
                      Resumo público
                      <textarea
                        name="summary"
                        defaultValue={task.summary || ""}
                        disabled={busy}
                      />
                    </label>
                    <label className="publication-check">
                      <input
                        name="published"
                        type="checkbox"
                        defaultChecked={task.published}
                        disabled={busy}
                      />{" "}
                      Publicar entrega
                    </label>
                    <button disabled={busy}>Salvar entrega</button>
                  </form>
                ))}
              </section>
            </>
          ) : (
            <div className="publication-message">
              Escolha um projeto para editar sua publicação.
            </div>
          )}
        </div>
      </div>
      <section className="publication-news">
        <form
          className="publication-form"
          onSubmit={(event) => void saveNews(event)}
        >
          <h2>{draft.id ? "Editar notícia" : "Nova notícia"}</h2>
          <label>
            Título
            <input
              value={draft.title}
              onChange={(event) =>
                setDraft({ ...draft, title: event.target.value })
              }
              disabled={busy}
              required
            />
          </label>
          <label>
            Resumo
            <textarea
              value={draft.summary || ""}
              onChange={(event) =>
                setDraft({ ...draft, summary: event.target.value })
              }
              disabled={busy}
            />
          </label>
          <label>
            Texto
            <textarea
              value={draft.body || ""}
              onChange={(event) =>
                setDraft({ ...draft, body: event.target.value })
              }
              disabled={busy}
              required
            />
          </label>
          <label>
            Projeto
            <select
              value={
                draft.project_id ||
                (user.global_role === "admin" ? "" : choices[0]?.id || "")
              }
              disabled={busy}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  project_id: event.target.value
                    ? Number(event.target.value)
                    : null,
                })
              }
            >
              {user.global_role === "admin" && (
                <option value="">Sem projeto</option>
              )}
              {choices.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="publication-check">
            <input
              type="checkbox"
              checked={draft.published}
              disabled={busy}
              onChange={(event) =>
                setDraft({ ...draft, published: event.target.checked })
              }
            />{" "}
            Publicar notícia
          </label>
          <button disabled={busy}>Salvar notícia</button>
        </form>
        <div>
          <h2>Notícias</h2>
          {news?.length ? (
            news.map((item) => (
              <article
                key={`${item.id}-${item.version}`}
                className="publication-news-item"
              >
                <small>{item.published ? "Publicada" : "Rascunho"}</small>
                <h3>{item.title}</h3>
                <p>{item.summary}</p>
                <button disabled={busy} onClick={() => setDraft(item)}>
                  Editar
                </button>
              </article>
            ))
          ) : (
            <p>Nenhuma notícia criada.</p>
          )}
        </div>
      </section>
    </section>
  );
}
