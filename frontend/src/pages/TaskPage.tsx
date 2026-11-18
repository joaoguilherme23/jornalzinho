import { appHref } from "../lib/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { AxiosError } from "axios";
import { backend, error } from "../api";
import { TaskDialog } from "../components/TaskDialog";
import { TaskReferences } from "../components/TaskReferences";
import type {
  Column,
  Comment,
  History,
  Label,
  Participant,
  Task,
  User,
} from "../types";
type Draft = {
  title: string;
  description: string;
  priority: Task["priority"];
  type: Task["type"];
  assigneeId: string;
  dueDate: string;
  labelIds: number[];
};
export type TaskPageProps = {
  taskId: number;
  users: User[];
  back: (boardId?: number) => void;
  onChanged?: () => void;
};
export const toDraft = (t: Task): Draft => ({
  title: t.title,
  description: t.description || "",
  priority: t.priority,
  type: t.type,
  assigneeId: t.assignee ? String(t.assignee.id) : "",
  dueDate: t.due_date || "",
  labelIds: t.labels.map((label) => label.id),
});
const fmt = (v: string | null) =>
  v
    ? new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "America/Sao_Paulo",
      }).format(new Date(v))
    : "—";
const dueDate = (value: string) =>
  new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
    new Date(`${value}T12:00:00`),
  );
const fieldLabel: Record<string, string> = {
  title: "título",
  description: "descrição",
  priority: "prioridade",
  type: "tipo",
  task_type: "tipo",
  label_ids: "etiquetas",
  assignee_id: "responsável",
  due_date: "prazo",
  column_id: "status",
};
const valueLabel: Record<string, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  critical: "Crítica",
  task: "Tarefa",
  bug: "Erro",
  improvement: "Melhoria",
};
const readableValue = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "sem valor";
  if (typeof value === "string" || typeof value === "number")
    return valueLabel[String(value)] || String(value);
  return "valor atualizado";
};
const values = (h: History) => {
  const oldValue = h.old_value || {};
  const newValue = h.new_value || {};
  const key =
    Object.keys(newValue).find((item) => item in oldValue) ||
    Object.keys(newValue)[0] ||
    Object.keys(oldValue)[0];
  if (!key) return "";
  return `: ${fieldLabel[key] || "campo"} de ${readableValue(oldValue[key])} para ${readableValue(newValue[key])}`;
};
const event = (v: string) =>
  ({
    created: "criou a tarefa",
    updated: "atualizou a tarefa",
    moved: "moveu a tarefa",
    completed: "concluiu a tarefa",
    reopened: "reabriu a tarefa",
    commented: "adicionou um comentário",
    task_created: "criou a tarefa",
    task_updated: "atualizou a tarefa",
    task_moved: "moveu a tarefa",
    task_completed: "concluiu a tarefa",
    task_reopened: "reabriu a tarefa",
    comment_created: "adicionou um comentário",
  })[v] || "fez uma alteração";
const writableRoles = new Set(["member", "manager", "admin"]);

export function TaskPage({ taskId, users, back, onChanged }: TaskPageProps) {
  const mounted = useRef(true),
    requestId = useRef(0),
    commentKey = useRef<{ body: string; key: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [task, setTask] = useState<Task | null>(null),
    [draft, setDraft] = useState<Draft | null>(null),
    [columns, setColumns] = useState<Column[]>([]),
    [labels, setLabels] = useState<Label[]>([]),
    [people, setPeople] = useState<Participant[]>(users),
    [comments, setComments] = useState<Comment[]>([]),
    [history, setHistory] = useState<History[]>([]),
    [ct, setCt] = useState(0),
    [ht, setHt] = useState(0),
    [comment, setComment] = useState(""),
    [notice, setNotice] = useState(""),
    [loadError, setLoadError] = useState(""),
    [saving, setSaving] = useState(false),
    [moving, setMoving] = useState(false),
    [commenting, setCommenting] = useState(false),
    [loadingMoreComments, setLoadingMoreComments] = useState(false),
    [loadingMoreHistory, setLoadingMoreHistory] = useState(false);
  const reload = useCallback(
    async (preserve = true) => {
      const request = ++requestId.current;
      try {
        const [t, c, h, u] = await Promise.all([
          backend.task(taskId),
          backend.comments(taskId),
          backend.history(taskId),
          users.length
            ? Promise.resolve(users)
            : backend
                .task(taskId)
                .then((value) => backend.board(value.board_id))
                .then((value) => backend.assignees(value.project.id)),
        ]);
        const b = await backend.board(t.board_id);
        const taskLabels = await backend.labels(b.project.id, true);
        if (!mounted.current || request !== requestId.current) return;
        setTask(t);
        setDraft((old) => (preserve && old ? old : toDraft(t)));
        setColumns(b.columns);
        setLabels(taskLabels);
        setPeople(u);
        setComments(c.items);
        setHistory(h.items);
        setCt(c.total);
        setHt(h.total);
        setLoadError("");
      } catch (e) {
        if (mounted.current && request === requestId.current)
          setLoadError(error(e));
      }
    },
    [taskId, users],
  );
  useEffect(() => {
    mounted.current = true;
    void reload(false);
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [reload]);
  const change = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));
  async function copy(value: string, success: string) {
    try {
      if (!navigator.clipboard?.writeText)
        throw new Error("A cópia não é suportada neste navegador.");
      await navigator.clipboard.writeText(value);
      if (mounted.current) setNotice(success);
    } catch (failure) {
      if (mounted.current)
        setNotice(`Não foi possível copiar. ${error(failure)}`);
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!task || !draft) return;
    setSaving(true);
    try {
      const n = await backend.patchTask(task.id, {
        version: task.version,
        title: draft.title,
        description: draft.description || null,
        priority: draft.priority,
        type: draft.type,
        assignee_id: draft.assigneeId ? Number(draft.assigneeId) : null,
        due_date: draft.dueDate || null,
        label_ids: draft.labelIds,
      });
      if (!mounted.current) return;
      setTask(n);
      onChanged?.();
      setDraft(toDraft(n));
      setEditing(false);
      setNotice("Alterações salvas.");
      await reload(false);
    } catch (e) {
      if (e instanceof AxiosError && e.response?.status === 409) {
        setNotice(
          "A tarefa mudou em outra sessão. A versão atual foi recarregada; seu rascunho foi preservado.",
        );
        await reload(true);
      } else setNotice(error(e));
    } finally {
      if (mounted.current) setSaving(false);
    }
  }
  async function move(id: number) {
    if (!task || saving || moving) return;
    setMoving(true);
    try {
      const n = await backend.move(task.id, id, 0, task.version);
      if (!mounted.current) return;
      setTask(n);
      onChanged?.();
      setNotice("Status atualizado.");
      await reload(true);
    } catch (e) {
      if (e instanceof AxiosError && e.response?.status === 409) {
        setNotice(
          "Conflito de versão. Dados recarregados sem perder seu rascunho.",
        );
        await reload(true);
      } else setNotice(error(e));
    } finally {
      if (mounted.current) setMoving(false);
    }
  }
  async function sendComment(e: FormEvent) {
    e.preventDefault();
    const body = comment.trim();
    if (!body || commenting) return;
    if (!commentKey.current || commentKey.current.body !== body)
      commentKey.current = { body, key: crypto.randomUUID() };
    setCommenting(true);
    try {
      await backend.addComment(taskId, body, commentKey.current.key);
      if (!mounted.current) return;
      setComment("");
      commentKey.current = null;
      setNotice("Comentário publicado.");
      await reload(true);
    } catch (e) {
      setNotice(error(e));
    } finally {
      if (mounted.current) setCommenting(false);
    }
  }
  async function moreComments() {
    if (loadingMoreComments) return;
    setLoadingMoreComments(true);
    try {
      const p = await backend.comments(taskId, comments.length);
      if (mounted.current)
        setComments((v) => [
          ...v,
          ...p.items.filter((x) => !v.some((y) => y.id === x.id)),
        ]);
    } catch (e) {
      if (mounted.current) setNotice(error(e));
    } finally {
      if (mounted.current) setLoadingMoreComments(false);
    }
  }
  async function moreHistory() {
    if (loadingMoreHistory) return;
    setLoadingMoreHistory(true);
    try {
      const p = await backend.history(taskId, history.length);
      if (mounted.current)
        setHistory((v) => [
          ...v,
          ...p.items.filter((x) => !v.some((y) => y.id === x.id)),
        ]);
    } catch (e) {
      if (mounted.current) setNotice(error(e));
    } finally {
      if (mounted.current) setLoadingMoreHistory(false);
    }
  }
  if (!task || !draft)
    return (
      <TaskDialog onClose={back}>
        <section
          className={loadError ? "error" : "loading"}
          role={loadError ? "alert" : "status"}
        >
          {loadError || "Carregando tarefa…"}
          {loadError && (
            <button className="quiet" onClick={() => void reload(false)}>
              Tentar novamente
            </button>
          )}
        </section>
      </TaskDialog>
    );
  const canWrite = writableRoles.has(task.role ?? "viewer");
  const unavailableAssignee =
    task.assignee && !people.some((person) => person.id === task.assignee!.id)
      ? task.assignee
      : null;
  const formId = `task-edit-${task.id}`;
  const dirty = JSON.stringify(draft) !== JSON.stringify(toDraft(task));
  const close = () => {
    if (saving || moving || commenting) {
      setNotice("Aguarde a operação terminar antes de fechar a tarefa.");
      return;
    }
    if (
      (dirty || comment.trim()) &&
      !window.confirm(
        "Há alterações ou um comentário não salvos. Descartar e fechar a tarefa?",
      )
    )
      return;
    back(task.board_id);
  };
  return (
    <TaskDialog onClose={close} code={task.code}>
      <section className="task-detail">
        <aside className="task-sidebar" aria-label="Propriedades da tarefa">
          <h2>Detalhes</h2>
          <div className="task-sidebar__status">
            {canWrite ? (
              <label>
                Status
                <select
                  aria-label="Mover para"
                  disabled={saving || moving}
                  value={task.column_id}
                  onChange={(e) => void move(Number(e.target.value))}
                >
                  {columns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <dl>
                <div>
                  <dt>Status</dt>
                  <dd>{task.column.name}</dd>
                </div>
              </dl>
            )}
            <p className="readonly">
              {task.completed_at
                ? `Concluída em ${fmt(task.completed_at)}`
                : "Em andamento"}
            </p>
          </div>
          <dl>
            <div>
              <dt>Relator</dt>
              <dd>{task.reporter.name}</dd>
            </div>
          </dl>
          <div className="task-sidebar__fields" style={{ marginTop: 20 }}>
            {canWrite && editing ? (
              <>
                <label>
                  Responsável
                  <select
                    aria-label="Responsável"
                    form={formId}
                    value={draft.assigneeId}
                    onChange={(e) => change("assigneeId", e.target.value)}
                  >
                    <option value="">Sem responsável</option>
                    {unavailableAssignee && (
                      <option value={unavailableAssignee.id} disabled>
                        {unavailableAssignee.name} (indisponível)
                      </option>
                    )}
                    {people.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Prioridade
                  <select
                    aria-label="Prioridade"
                    form={formId}
                    value={draft.priority}
                    onChange={(e) =>
                      change("priority", e.target.value as Task["priority"])
                    }
                  >
                    {[
                      ["low", "Baixa"],
                      ["medium", "Média"],
                      ["high", "Alta"],
                      ["critical", "Crítica"],
                    ].map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Tipo
                  <select
                    aria-label="Tipo"
                    form={formId}
                    value={draft.type}
                    onChange={(e) =>
                      change("type", e.target.value as Task["type"])
                    }
                  >
                    {[
                      ["task", "Tarefa"],
                      ["bug", "Erro"],
                      ["improvement", "Melhoria"],
                    ].map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Prazo
                  <input
                    form={formId}
                    type="date"
                    value={draft.dueDate}
                    onChange={(e) => change("dueDate", e.target.value)}
                  />
                </label>
              </>
            ) : (
              <dl>
                <div>
                  <dt>Responsável</dt>
                  <dd>
                    {task.assignee?.name ?? "Sem responsável"}
                    {unavailableAssignee ? " (indisponível)" : ""}
                  </dd>
                </div>
                <div>
                  <dt>Prioridade</dt>
                  <dd>{valueLabel[task.priority]}</dd>
                </div>
                <div>
                  <dt>Tipo</dt>
                  <dd>{valueLabel[task.type]}</dd>
                </div>
                <div>
                  <dt>Prazo</dt>
                  <dd>
                    {task.due_date ? dueDate(task.due_date) : "Sem prazo"}
                  </dd>
                </div>
              </dl>
            )}
          </div>
          <div className="task-sidebar__dates">
            <dl>
              <div>
                <dt>Criada em</dt>
                <dd>{fmt(task.created_at)}</dd>
              </div>
              <div>
                <dt>Atualizada em</dt>
                <dd>{fmt(task.updated_at)}</dd>
              </div>
            </dl>
          </div>
        </aside>
        <div className="task-content">
          {notice && (
            <p className="error" role="status">
              {notice}
            </p>
          )}
          {loadError && (
            <p className="error" role="alert">
              {loadError}
              <button className="quiet" onClick={() => void reload(true)}>
                Tentar novamente
              </button>
            </p>
          )}
          <div className="task-detail__actions">
            {canWrite && !editing && (
              <button onClick={() => setEditing(true)}>Editar tarefa</button>
            )}
            <button
              className="quiet"
              type="button"
              onClick={() => void copy(task.code, "Código copiado.")}
            >
              Copiar código
            </button>
            <button
              className="quiet"
              type="button"
              onClick={() =>
                void copy(
                  new URL(
                    appHref(
                      `#/task/${encodeURIComponent(task.code)}?board=${task.board_id}`,
                    ),
                    window.location.href,
                  ).href,
                  "Link copiado.",
                )
              }
            >
              Copiar link
            </button>
          </div>
          {canWrite && editing ? (
            <>
              <form id={formId} onSubmit={save} hidden />
              <div className="task-content__edit">
                <label>
                  Título
                  <input
                    form={formId}
                    required
                    value={draft.title}
                    onChange={(e) => change("title", e.target.value)}
                  />
                </label>
                <label>
                  Descrição
                  <textarea
                    form={formId}
                    value={draft.description}
                    onChange={(e) => change("description", e.target.value)}
                  />
                </label>
                <fieldset>
                  <legend>Etiquetas</legend>
                  <div className="task-labels">
                    {labels
                      .filter(
                        (label) =>
                          !label.is_archived ||
                          task.labels.some(
                            (applied) => applied.id === label.id,
                          ),
                      )
                      .map((label) => (
                        <label key={label.id} className="check-field">
                          <input
                            form={formId}
                            type="checkbox"
                            checked={draft.labelIds.includes(label.id)}
                            onChange={(e) =>
                              change(
                                "labelIds",
                                e.target.checked
                                  ? [...draft.labelIds, label.id]
                                  : draft.labelIds.filter(
                                      (id) => id !== label.id,
                                    ),
                              )
                            }
                          />
                          <span
                            className={`task-label task-label--${label.color}`}
                          >
                            {label.name}
                            {label.is_archived ? " (arquivada)" : ""}
                          </span>
                        </label>
                      ))}
                    {labels.length === 0 && (
                      <p className="readonly">
                        Nenhuma etiqueta cadastrada neste projeto.
                      </p>
                    )}
                  </div>
                </fieldset>
                <div className="task-detail__actions">
                  <button
                    type="submit"
                    form={formId}
                    disabled={saving || moving}
                  >
                    {saving ? "Salvando…" : "Salvar alterações"}
                  </button>
                  <button
                    type="button"
                    className="quiet"
                    disabled={saving || moving}
                    onClick={() => {
                      setDraft(toDraft(task));
                      setEditing(false);
                    }}
                  >
                    Cancelar edição
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              <h1>{task.title}</h1>
              {task.labels.length > 0 && (
                <div className="task-labels" aria-label="Etiquetas">
                  {task.labels.map((label) => (
                    <span
                      className={`task-label task-label--${label.color}`}
                      key={label.id}
                    >
                      {label.name}
                      {label.is_archived ? " (arquivada)" : ""}
                    </span>
                  ))}
                </div>
              )}
              <h2>Descrição</h2>
              {task.description ? (
                <div className="task-description">
                  <TaskReferences
                    text={task.description}
                    boardId={task.board_id}
                  />
                </div>
              ) : (
                <p className="readonly">Sem descrição.</p>
              )}
            </>
          )}
          {!canWrite && (
            <p className="readonly">
              Você tem acesso somente para leitura neste projeto.
            </p>
          )}
          <section aria-label="Comentários">
            <h2>
              Comentários <small>({ct})</small>
            </h2>
            {canWrite && (
              <form className="comment-form" onSubmit={sendComment}>
                <label className="sr-only" htmlFor="comment">
                  Novo comentário
                </label>
                <textarea
                  id="comment"
                  required
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Escreva um comentário"
                />
                <button disabled={commenting}>
                  {commenting ? "Publicando…" : "Comentar"}
                </button>
              </form>
            )}
            {comments.length === 0 && (
              <p className="readonly">Nenhum comentário ainda.</p>
            )}
            {comments.map((c) => (
              <article className="comment" key={c.id}>
                <b>{c.author.name}</b>
                <div>
                  <TaskReferences text={c.body} boardId={task.board_id} />
                </div>
                <small>{fmt(c.created_at)}</small>
              </article>
            ))}
            {comments.length < ct && (
              <button
                className="quiet"
                disabled={loadingMoreComments}
                onClick={() => void moreComments()}
              >
                Carregar mais comentários
              </button>
            )}
          </section>
          <section aria-label="Histórico">
            <h2>Linha do tempo</h2>
            {history.map((h) => (
              <p className="history" key={h.id}>
                <b>{h.actor.name}</b> {event(h.event)}
                {values(h)} · {fmt(h.created_at)}
              </p>
            ))}
            {history.length < ht && (
              <button
                className="quiet"
                disabled={loadingMoreHistory}
                onClick={() => void moreHistory()}
              >
                Carregar mais eventos
              </button>
            )}
          </section>
        </div>
      </section>
    </TaskDialog>
  );
}
