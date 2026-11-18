import { appHref, navigate } from "../lib/navigation";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Flipped, Flipper } from "react-flip-toolkit";
import { backend, error } from "../api";
import type {
  Board,
  Column,
  Label,
  Participant,
  Priority,
  Project,
  Task,
  TaskType,
} from "../types";
import "./BoardPage.css";

type Props = {
  id: number;
  open: (id: number) => void;
  refreshKey?: number;
  openCreate?: boolean;
};
type Filters = {
  query: string;
  priority: string;
  type: string;
  assignee: string;
  labels: string[];
};
type ColumnForm = Pick<Column, "name" | "is_done" | "position"> & {
  id: number | null;
};
const priorities: Record<Priority, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  critical: "Crítica",
};
const types: Record<TaskType, string> = {
  task: "Tarefa",
  bug: "Bug",
  improvement: "Melhoria",
};
const canWrite = (role?: string) =>
  ["member", "manager", "admin"].includes(role ?? "viewer");
const canManage = (role?: string) =>
  ["manager", "admin"].includes(role ?? "viewer");
const blankDraft = () => ({
  title: "",
  description: "",
  priority: "medium" as Priority,
  type: "task" as TaskType,
  assignee_id: "",
  due_date: "",
  label_ids: [] as number[],
});
const blankFilters = (): Filters => ({
  query: "",
  priority: "",
  type: "",
  assignee: "",
  labels: [],
});
const filtersByBoard = new Map<number, Filters>();
if (typeof window !== "undefined")
  window.addEventListener("jornalzinho:session-cleared", () =>
    filtersByBoard.clear(),
  );
const date = (value: string) =>
  new Intl.DateTimeFormat("pt-BR").format(new Date(`${value}T12:00:00`));

export default function BoardPage({
  id,
  open,
  refreshKey = 0,
  openCreate = false,
}: Props) {
  const [board, setBoard] = useState<Board | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [users, setUsers] = useState<Participant[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [draft, setDraft] = useState(blankDraft);
  const [filters, setFilters] = useState<Filters>(
    () => filtersByBoard.get(id) ?? blankFilters(),
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [options, setOptions] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [columnForm, setColumnForm] = useState<ColumnForm | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [groupBy, setGroupBy] = useState<"status" | "assignee">("status");
  const [statusFilter, setStatusFilter] = useState("open");
  const input = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const generation = useRef(0);
  const request = useRef({ payload: "", key: "" });
  const load = useCallback(async () => {
    const expected = ++generation.current;
    try {
      const [first, nextProjects] = await Promise.all([
        backend.board(id),
        backend.projects(),
      ]);
      const [nextUsers, nextLabels] = await Promise.all([
        backend.assignees(first.project.id),
        backend.labels(first.project.id, true),
      ]);
      const tasks = [...first.tasks];
      while (tasks.length < first.tasks_total) {
        const next = await backend.board(id, tasks.length);
        if (!next.tasks.length)
          throw new Error("O quadro mudou durante a consulta.");
        tasks.push(...next.tasks);
      }
      if (mounted.current && expected === generation.current) {
        setBoard({ ...first, tasks });
        setProjects(nextProjects);
        setUsers(nextUsers);
        setLabels(nextLabels);
      }
    } catch (failure) {
      if (mounted.current && expected === generation.current)
        setNotice(error(failure));
    }
  }, [id]);
  useEffect(() => {
    mounted.current = true;
    void load();
    const refresh = () => document.visibilityState === "visible" && void load();
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    return () => {
      mounted.current = false;
      generation.current++;
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [load, refreshKey]);
  useEffect(() => {
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (openCreate) input.current?.focus();
  }, [openCreate, board?.id]);
  const changeFilters = (next: Filters) => {
    setFilters(next);
    filtersByBoard.set(id, next);
  };
  const visible = useMemo(
    () =>
      board?.tasks.filter(
        (task) =>
          `${task.code} ${task.title}`
            .toLocaleLowerCase("pt-BR")
            .includes(filters.query.toLocaleLowerCase("pt-BR")) &&
          (!filters.priority || task.priority === filters.priority) &&
          (!filters.type || task.type === filters.type) &&
          (!filters.assignee ||
            (filters.assignee === "none"
              ? !task.assignee
              : task.assignee?.id === Number(filters.assignee))) &&
          filters.labels.every((labelId) =>
            task.labels.some((label) => label.id === Number(labelId)),
          ) &&
          (statusFilter === "all" ||
            (statusFilter === "completed" && task.column.is_done) ||
            (statusFilter === "open" && !task.column.is_done) ||
            (statusFilter === "overdue" &&
              !task.column.is_done &&
              !!task.due_date &&
              new Date(`${task.due_date}T23:59:59`) < new Date())),
      ) ?? [],
    [board, filters, statusFilter],
  );
  async function create(event: FormEvent) {
    event.preventDefault();
    if (!board || busy) return;
    if (!draft.title.trim()) {
      setNotice("Informe o título da tarefa.");
      input.current?.focus();
      return;
    }
    const data = {
      board_id: board.id,
      title: draft.title.trim(),
      description: draft.description || null,
      priority: draft.priority,
      type: draft.type,
      assignee_id: draft.assignee_id ? Number(draft.assignee_id) : null,
      due_date: draft.due_date || null,
      label_ids: draft.label_ids,
    };
    const payload = JSON.stringify(data);
    if (request.current.payload !== payload)
      request.current = { payload, key: crypto.randomUUID() };
    setBusy(true);
    setNotice("");
    try {
      await backend.createTask(data, request.current.key);
      request.current = { payload: "", key: "" };
      setDraft(blankDraft());
      setOptions(false);
      setNotice("Tarefa adicionada ao quadro.");
      await load();
      input.current?.focus();
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  }
  async function move(task: Task, columnId: number, position: number) {
    if (busy) return;
    setBusy(true);
    try {
      await backend.move(task.id, columnId, position, task.version);
      await load();
    } catch (failure) {
      setNotice(
        `${error(failure)} O quadro foi atualizado; confira a tarefa antes de tentar novamente.`,
      );
      await load();
    } finally {
      setBusy(false);
    }
  }
  async function assign(task: Task, assigneeId: number | null) {
    if (busy) return;
    setBusy(true);
    try {
      await backend.patchTask(task.id, {
        version: task.version,
        assignee_id: assigneeId,
      });
      await load();
    } catch (failure) {
      setNotice(
        `${error(failure)} O quadro foi atualizado; confira a tarefa antes de tentar novamente.`,
      );
      await load();
    } finally {
      setBusy(false);
    }
  }
  async function columnAction(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      setColumnForm(null);
      setConfirmDelete(false);
      await load();
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  }
  function saveColumn(event: FormEvent) {
    event.preventDefault();
    if (!board || !columnForm) return;
    const form = columnForm;
    void columnAction(() =>
      form.id
        ? backend.patchColumn(form.id, {
            name: form.name,
            is_done: form.is_done,
            position: form.position,
          })
        : backend.addColumn(board.id, form.name, form.is_done),
    );
  }
  async function copy(value: string, success: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(success);
    } catch {
      setNotice("Não foi possível copiar neste navegador.");
    }
  }
  if (!board)
    return (
      <section className="empty-state" role={notice ? "alert" : "status"}>
        {notice ? (
          <>
            <h1>Não foi possível carregar o quadro</h1>
            <p>{notice}</p>
            <button onClick={() => void load()}>Tentar novamente</button>
          </>
        ) : (
          <div className="board-skeleton">
            <span />
            <span />
            <span />
          </div>
        )}
      </section>
    );
  const writable = canWrite(board.role);
  const manager = canManage(board.role);
  const labelsActive = labels.filter((label) => !label.is_archived);
  const tasksIn = (columnId: number) =>
    visible
      .filter((task) => task.column_id === columnId)
      .sort((a, b) => a.position - b.position);
  const findDragged = (event: React.DragEvent) =>
    board.tasks.find(
      (task) => task.id === Number(event.dataTransfer.getData("task")),
    );
  const end = (columnId: number, task: Task) =>
    board.tasks.filter(
      (item) => item.column_id === columnId && item.id !== task.id,
    ).length;
  const historicalAssignees = Array.from(
    new Map(
      visible
        .flatMap((task) => (task.assignee ? [task.assignee] : []))
        .map((assignee) => [assignee.id, assignee]),
    ).values(),
  ).filter((assignee) => !users.some((user) => user.id === assignee.id));
  const groups =
    groupBy === "status"
      ? board.columns.map((column) => ({
          key: String(column.id),
          title: column.name,
          tasks: tasksIn(column.id),
          columnId: column.id,
          assigneeId: undefined as number | null | undefined,
          eligible: true,
        }))
      : [
          {
            key: "none",
            title: "Sem responsável",
            tasks: visible.filter((task) => !task.assignee),
            assigneeId: null,
            columnId: undefined,
            eligible: true,
          },
          ...users.map((user) => ({
            key: String(user.id),
            title: user.name,
            tasks: visible.filter((task) => task.assignee?.id === user.id),
            assigneeId: user.id,
            columnId: undefined,
            eligible: true,
          })),
          ...historicalAssignees.map((user) => ({
            key: `historic-${user.id}`,
            title: `${user.name} (histórico)`,
            tasks: visible.filter((task) => task.assignee?.id === user.id),
            assigneeId: user.id,
            columnId: undefined,
            eligible: false,
          })),
        ];
  return (
    <section className="boardpage" aria-label="Área de tarefas">
      <div className="board-controls">
        <header className="board-intro">
          <div>
            <p className="eyebrow">Execução</p>
            <h1>Tarefas da equipe.</h1>
            <p>
              O que está na mão de cada um, em cada projeto, com prazo e
              situação.
            </p>
          </div>
          <p className="board-context">
            <b>{board.project.key}</b> · {board.project.name}
            <span className="board-tools">
              <a href={appHref(`#/projects/${board.project.id}/team`)}>
                Equipe
              </a>
              {manager && (
                <a href={appHref(`#/projects/${board.project.id}/labels`)}>
                  Etiquetas
                </a>
              )}
            </span>
          </p>
        </header>
        {notice && (
          <div className="boarderror" role="status">
            <p>{notice}</p>
            <button className="quiet" onClick={() => setNotice("")}>
              Fechar aviso
            </button>
          </div>
        )}
        <section className="board-filters" aria-label="Filtros das tarefas">
          <label className="board-filter-assignee">
            Responsável
            <select
              value={filters.assignee}
              onChange={(event) =>
                changeFilters({ ...filters, assignee: event.target.value })
              }
            >
              <option value="">Toda a equipe</option>
              <option value="none">Sem responsável</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name}
                </option>
              ))}
            </select>
          </label>
          <label className="board-filter-project">
            Projeto
            <select
              value={board.id}
              onChange={(event) => {
                navigate(`#/board/${event.target.value}`);
              }}
            >
              {projects
                .filter((project) => project.default_board_id)
                .map((project) => (
                  <option key={project.id} value={project.default_board_id!}>
                    {project.name}
                  </option>
                ))}
            </select>
          </label>
          <div
            className="group-toggle"
            role="group"
            aria-label="Situação das tarefas"
          >
            <span>Situação</span>
            {[
              ["open", "Abertas"],
              ["overdue", "Vencidas"],
              ["completed", "Concluídas"],
              ["all", "Todas"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className="quiet"
                aria-pressed={statusFilter === value}
                onClick={() => setStatusFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="group-toggle board-filter-group"
            role="group"
            aria-label="Agrupar tarefas"
          >
            <span>Agrupar por</span>
            <button
              type="button"
              className="quiet"
              aria-pressed={groupBy === "status"}
              onClick={() => setGroupBy("status")}
            >
              Situação
            </button>
            <button
              type="button"
              className="quiet"
              aria-pressed={groupBy === "assignee"}
              onClick={() => setGroupBy("assignee")}
            >
              Responsável
            </button>
          </div>
          <details className="board-more-options">
            <summary>Mais opções do quadro</summary>
            <div>
              <label>
                Busca
                <input
                  aria-label="Buscar tarefas"
                  placeholder="Buscar tarefa ou código"
                  value={filters.query}
                  onChange={(event) =>
                    changeFilters({ ...filters, query: event.target.value })
                  }
                />
              </label>
              <label>
                Prioridade
                <select
                  value={filters.priority}
                  onChange={(event) =>
                    changeFilters({ ...filters, priority: event.target.value })
                  }
                >
                  <option value="">Todas as prioridades</option>
                  {Object.entries(priorities).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Tipo
                <select
                  value={filters.type}
                  onChange={(event) =>
                    changeFilters({ ...filters, type: event.target.value })
                  }
                >
                  <option value="">Todos os tipos</option>
                  {Object.entries(types).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {labelsActive.length > 0 && (
                <fieldset>
                  <legend>Etiquetas</legend>
                  {labelsActive.map((label) => (
                    <label key={label.id} className="check-field">
                      <input
                        type="checkbox"
                        checked={filters.labels.includes(String(label.id))}
                        onChange={(event) =>
                          changeFilters({
                            ...filters,
                            labels: event.target.checked
                              ? [...filters.labels, String(label.id)]
                              : filters.labels.filter(
                                  (labelId) => labelId !== String(label.id),
                                ),
                          })
                        }
                      />
                      <span className={`task-label task-label--${label.color}`}>
                        {label.name}
                      </span>
                    </label>
                  ))}
                </fieldset>
              )}
              <button
                className="quiet"
                type="button"
                onClick={() => changeFilters(blankFilters())}
              >
                Limpar filtros
              </button>
              {manager && (
                <button
                  type="button"
                  className="quiet"
                  onClick={() => {
                    setColumnForm({
                      id: null,
                      name: "",
                      is_done: false,
                      position: board.columns.length,
                    });
                    setConfirmDelete(false);
                  }}
                >
                  Gerenciar quadro
                </button>
              )}
            </div>
          </details>
        </section>
        <div className="board-heading">
          <h2>Quadro de tarefas</h2>
          <p className="board-count" aria-live="polite">
            {visible.length} de {board.tasks.length} tarefas
            {busy ? " · salvando…" : ""}
          </p>
        </div>
        {writable && (
          <form className="task-create" onSubmit={create}>
            <label>
              <span>Projeto</span>
              <select
                value={board.id}
                onChange={(event) => {
                  const hasDraft = Boolean(
                    draft.title.trim() ||
                    draft.description.trim() ||
                    draft.assignee_id ||
                    draft.due_date ||
                    draft.label_ids.length,
                  );
                  if (
                    hasDraft &&
                    !window.confirm(
                      "Trocar de projeto descarta o rascunho desta tarefa. Continuar?",
                    )
                  )
                    return;
                  navigate(`#/board/${event.target.value}?newTask=1`);
                }}
              >
                {projects
                  .filter((project) => project.default_board_id)
                  .map((project) => (
                    <option key={project.id} value={project.default_board_id!}>
                      {project.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              <span>Tarefa</span>
              <input
                ref={input}
                required
                maxLength={300}
                placeholder="O que precisa ser feito"
                value={draft.title}
                onChange={(event) =>
                  setDraft({ ...draft, title: event.target.value })
                }
              />
            </label>
            <label>
              <span>Responsável</span>
              <select
                value={draft.assignee_id}
                onChange={(event) =>
                  setDraft({ ...draft, assignee_id: event.target.value })
                }
              >
                <option value="">Quem faz</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Prazo</span>
              <input
                type="date"
                value={draft.due_date}
                onChange={(event) =>
                  setDraft({ ...draft, due_date: event.target.value })
                }
              />
            </label>
            <button disabled={busy}>
              {busy ? "Salvando…" : "Adicionar tarefa"}
            </button>
            <details
              className="task-options"
              open={options}
              onToggle={(event) => setOptions(event.currentTarget.open)}
            >
              <summary>Mais opções</summary>
              <div>
                <label>
                  Prioridade
                  <select
                    value={draft.priority}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        priority: event.target.value as Priority,
                      })
                    }
                  >
                    {Object.entries(priorities).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Tipo
                  <select
                    value={draft.type}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        type: event.target.value as TaskType,
                      })
                    }
                  >
                    {Object.entries(types).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="task-description">
                  Descrição
                  <textarea
                    value={draft.description}
                    onChange={(event) =>
                      setDraft({ ...draft, description: event.target.value })
                    }
                  />
                </label>
                {labelsActive.length > 0 && (
                  <fieldset>
                    <legend>Etiquetas</legend>
                    {labelsActive.map((label) => (
                      <label key={label.id} className="check-field">
                        <input
                          type="checkbox"
                          checked={draft.label_ids.includes(label.id)}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              label_ids: event.target.checked
                                ? [...draft.label_ids, label.id]
                                : draft.label_ids.filter(
                                    (labelId) => labelId !== label.id,
                                  ),
                            })
                          }
                        />
                        <span
                          className={`task-label task-label--${label.color}`}
                        >
                          {label.name}
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}
              </div>
            </details>
          </form>
        )}
        {columnForm && (
          <section className="column-editor card" aria-label="Gerenciar quadro">
            <h2>{columnForm.id ? "Editar coluna" : "Nova coluna"}</h2>
            <form
              onSubmit={saveColumn}
              onKeyDown={(event) =>
                event.key === "Escape" && setColumnForm(null)
              }
            >
              <label>
                Nome da coluna
                <input
                  autoFocus
                  required
                  maxLength={120}
                  value={columnForm.name}
                  onChange={(event) =>
                    setColumnForm({ ...columnForm, name: event.target.value })
                  }
                />
              </label>
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={columnForm.is_done}
                  onChange={(event) =>
                    setColumnForm({
                      ...columnForm,
                      is_done: event.target.checked,
                    })
                  }
                />
                As tarefas nesta coluna estão concluídas
              </label>
              {columnForm.id && (
                <label>
                  Posição da coluna
                  <select
                    value={columnForm.position}
                    onChange={(event) =>
                      setColumnForm({
                        ...columnForm,
                        position: Number(event.target.value),
                      })
                    }
                  >
                    {board.columns.map((column, index) => (
                      <option key={column.id} value={index}>
                        {index + 1} — {column.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="column-actions">
                <button disabled={busy}>Salvar coluna</button>
                <button
                  type="button"
                  className="quiet"
                  onClick={() => setColumnForm(null)}
                >
                  Cancelar
                </button>
                {columnForm.id && (
                  <>
                    <button
                      type="button"
                      disabled={
                        busy || board.default_column_id === columnForm.id
                      }
                      onClick={() =>
                        void columnAction(() =>
                          backend.patchBoard(id, {
                            default_column_id: columnForm.id!,
                          }),
                        )
                      }
                    >
                      Usar como coluna inicial
                    </button>
                    <button
                      type="button"
                      className="quiet"
                      disabled={
                        busy || board.default_column_id === columnForm.id
                      }
                      onClick={() => {
                        if (
                          board.tasks.some(
                            (task) => task.column_id === columnForm.id,
                          )
                        ) {
                          setNotice(
                            "Esvazie ou mova as tarefas da coluna antes de excluí-la.",
                          );
                          return;
                        }
                        setConfirmDelete(true);
                      }}
                    >
                      Excluir coluna
                    </button>
                  </>
                )}
              </div>
            </form>
            {confirmDelete && (
              <div className="boarderror" role="alert">
                <p>
                  Excluir “{columnForm.name}”? A coluna deve estar vazia e não
                  pode ser a coluna inicial.
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    void columnAction(() =>
                      backend.deleteColumn(columnForm.id!),
                    )
                  }
                >
                  Confirmar exclusão
                </button>
                <button
                  className="quiet"
                  onClick={() => setConfirmDelete(false)}
                >
                  Manter coluna
                </button>
              </div>
            )}
          </section>
        )}
      </div>
      <div
        className="board-lanes"
        role="region"
        aria-label="Quadro de tarefas"
        tabIndex={0}
      >
        <Flipper
          flipKey={board.tasks
            .map(
              (task) =>
                `${groupBy}:${task.id}:${task.column_id}:${task.assignee?.id ?? "none"}:${task.position}`,
            )
            .join("|")}
          spring={{ stiffness: 280, damping: 26 }}
        >
          <div
            className={`boardkanban${groupBy === "assignee" ? " boardkanban--people" : ""}`}
          >
            {groups.map((column) => (
              <section
                className="column"
                key={column.key}
                aria-label={`Coluna ${column.title}`}
                onDragOver={(event) => writable && event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  const task = findDragged(event);
                  if (task && writable) {
                    if (groupBy === "status" && column.columnId)
                      void move(
                        task,
                        column.columnId,
                        end(column.columnId, task),
                      );
                    if (groupBy === "assignee" && column.eligible)
                      void assign(task, column.assigneeId ?? null);
                  }
                }}
              >
                <header className="columnhead">
                  <h2>{column.title}</h2>
                  <span>{column.tasks.length}</span>
                  {manager && groupBy === "status" && column.columnId && (
                    <button
                      className="quiet column-edit"
                      onClick={() => {
                        const found = board.columns.find(
                          (item) => item.id === column.columnId,
                        );
                        if (found) {
                          setColumnForm(found);
                          setConfirmDelete(false);
                        }
                      }}
                    >
                      Editar
                    </button>
                  )}
                </header>
                <div className="column-cards">
                  {column.tasks.map((task) => (
                    <Flipped
                      key={task.id}
                      flipId={`task-${task.id}`}
                      shouldFlip={() => !reducedMotion}
                    >
                      <article
                        className={`task boardtask${task.column.is_done ? " boardtask--done" : task.due_date && new Date(`${task.due_date}T23:59:59`) < new Date() ? " boardtask--overdue" : ""}`}
                        draggable={writable && !busy}
                        onDragStartCapture={(event) =>
                          event.dataTransfer.setData("task", String(task.id))
                        }
                        onDragOver={(event) =>
                          writable && event.preventDefault()
                        }
                        onDrop={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          const dragged = findDragged(event);
                          if (dragged && dragged.id !== task.id && writable) {
                            if (groupBy === "status" && column.columnId)
                              void move(
                                dragged,
                                column.columnId,
                                task.position -
                                  (dragged.column_id === column.columnId &&
                                  dragged.position < task.position
                                    ? 1
                                    : 0),
                              );
                            if (groupBy === "assignee" && column.eligible)
                              void assign(dragged, column.assigneeId ?? null);
                          }
                        }}
                      >
                        <button
                          className="taskmain"
                          onClick={() => open(task.id)}
                        >
                          <p className="task-title">{task.title}</p>
                          <p className="task-meta">
                            {board.project.name} ·{" "}
                            {task.assignee?.name ?? "Sem responsável"}
                            {task.due_date
                              ? ` · até ${date(task.due_date)}`
                              : ""}
                          </p>
                          <p className="task-meta">
                            <b>{task.code}</b> · {priorities[task.priority]} ·{" "}
                            {types[task.type]}
                          </p>
                          {task.labels.length > 0 && (
                            <span
                              className="task-labels"
                              aria-label="Etiquetas"
                            >
                              {task.labels.map((label) => (
                                <span
                                  className={`task-label task-label--${label.color}`}
                                  key={label.id}
                                >
                                  {label.name}
                                </span>
                              ))}
                            </span>
                          )}
                        </button>
                        <div className="task-actions-row">
                          <div className="task-primary-actions">
                            {writable &&
                              board.columns.some(
                                (target) =>
                                  target.is_done !== task.column.is_done,
                              ) && (
                                <button
                                  className="quiet"
                                  type="button"
                                  disabled={busy}
                                  onClick={() => {
                                    const target = task.column.is_done
                                      ? board.columns.find(
                                          (item) => !item.is_done,
                                        )
                                      : board.columns.find(
                                          (item) => item.is_done,
                                        );
                                    if (target)
                                      void move(
                                        task,
                                        target.id,
                                        end(target.id, task),
                                      );
                                  }}
                                >
                                  {task.column.is_done ? "Reabrir" : "Concluir"}
                                </button>
                              )}
                          </div>
                          <details className="task-card-more">
                            <summary>Mais ações</summary>
                            <div className="task-card-actions">
                              <button
                                className="quiet"
                                type="button"
                                onClick={() =>
                                  void copy(task.code, "Código copiado.")
                                }
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
                                        `#/task/${encodeURIComponent(task.code)}`,
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
                            {writable && (
                              <label className="task-move">
                                Mover para
                                <select
                                  value={task.column_id}
                                  disabled={busy}
                                  onChange={(event) =>
                                    void move(
                                      task,
                                      Number(event.target.value),
                                      end(Number(event.target.value), task),
                                    )
                                  }
                                >
                                  {board.columns.map((target) => (
                                    <option key={target.id} value={target.id}>
                                      {target.name}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            )}
                          </details>
                        </div>
                      </article>
                    </Flipped>
                  ))}
                </div>
                {!column.tasks.length && (
                  <p className="column-empty">Nenhuma tarefa</p>
                )}
              </section>
            ))}
          </div>
        </Flipper>
      </div>
    </section>
  );
}
