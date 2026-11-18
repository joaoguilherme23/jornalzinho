import axios, {
  AxiosAdapter,
  AxiosError,
  CanceledError,
  InternalAxiosRequestConfig,
} from "axios";
import type {
  Board,
  Column,
  Comment,
  History,
  Page,
  Project,
  Task,
  User,
  Participant,
  ProjectMember,
  Membership,
  ProjectRole,
  Label,
  LabelColor,
} from "./types";

type RequestConfig = InternalAxiosRequestConfig & {
  sessionGeneration?: number;
  retried?: boolean;
};
type AccessResponse = {
  access_token: string;
  user: User;
  expires_in: number;
  token_type: string;
  session_expires_at: string;
  server_time?: string;
};
export const UNAUTHORIZED_EVENT = "jornalzinho:unauthorized";
export const SESSION_USER_EVENT = "jornalzinho:session-user";
const LOGOUT_MARKER = "jornalzinho:logout-requested:v1";
const SESSION_CHANNEL = "jornalzinho:session:v1";
const AUTH_TIMEOUT_MS = 12_000;

type SessionMessage = { type: "ended" | "login" };

function logoutWasRequested() {
  try {
    return (
      typeof localStorage !== "undefined" &&
      localStorage.getItem(LOGOUT_MARKER) === "1"
    );
  } catch {
    return false;
  }
}

function markLogoutRequested() {
  try {
    localStorage.setItem(LOGOUT_MARKER, "1");
  } catch {
    // A geração local ainda bloqueia restauração nesta aba.
  }
}

function clearLogoutMarker() {
  try {
    localStorage.removeItem(LOGOUT_MARKER);
  } catch {
    // O login concluído ainda libera a aba atual.
  }
}

export function createSession(options: {
  baseURL: string;
  adapter?: AxiosAdapter;
  onUnauthorized?: () => void;
}) {
  const config = {
    baseURL: options.baseURL,
    withCredentials: true,
    adapter: options.adapter,
  };
  const client = axios.create(config);
  const auth = axios.create(config);
  let token: string | null = null;
  let active: User | null = null;
  let generation = 0;
  let controller = new AbortController();
  let refreshing: Promise<User> | null = null;
  let logoutPending: Promise<void> | null = null;
  let deadlineTimer: ReturnType<typeof setTimeout> | null = null;
  let locallyBlocked = logoutWasRequested();
  const channel =
    typeof window === "undefined" || typeof BroadcastChannel === "undefined"
      ? null
      : new BroadcastChannel(SESSION_CHANNEL);

  function withSessionLock<T>(operation: () => Promise<T>): Promise<T> {
    if (typeof navigator === "undefined" || !navigator.locks)
      return operation();
    return navigator.locks.request(
      "jornalzinho:session",
      { mode: "exclusive" },
      operation,
    );
  }

  function clear() {
    generation += 1;
    controller.abort();
    controller = new AbortController();
    token = null;
    active = null;
    refreshing = null;
    if (deadlineTimer !== null) clearTimeout(deadlineTimer);
    deadlineTimer = null;
    if (typeof window !== "undefined")
      window.dispatchEvent(new Event("jornalzinho:session-cleared"));
  }

  function endSession(propagate = false) {
    locallyBlocked = true;
    markLogoutRequested();
    clear();
    if (propagate) {
      channel?.postMessage({ type: "ended" } satisfies SessionMessage);
      try {
        localStorage.setItem(SESSION_CHANNEL, String(Date.now()));
      } catch {
        // BroadcastChannel cobre navegadores que o oferecem.
      }
    }
    options.onUnauthorized?.();
  }

  function rejectInvalidAccess(message: string): never {
    endSession(true);
    throw new CanceledError(message);
  }

  function applyAccess(data: AccessResponse, expected: number) {
    if (expected !== generation) throw new CanceledError("Sessão encerrada.");
    const deadline = Date.parse(data.session_expires_at);
    const serverTime = data.server_time
      ? Date.parse(data.server_time)
      : Date.now();
    if (
      typeof data.access_token !== "string" ||
      !data.access_token ||
      !data.user ||
      typeof data.session_expires_at !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(
        data.session_expires_at,
      ) ||
      !Number.isFinite(data.expires_in) ||
      data.expires_in <= 0 ||
      data.expires_in > 900 ||
      !Number.isFinite(deadline) ||
      !Number.isFinite(serverTime) ||
      deadline <= serverTime
    )
      return rejectInvalidAccess("Resposta de sessão inválida.");
    if (active && active.id !== data.user.id) {
      locallyBlocked = true;
      clear();
      options.onUnauthorized?.();
      throw new CanceledError("A conta da sessão foi alterada.");
    }
    token = data.access_token;
    active = data.user;
    if (deadlineTimer !== null) clearTimeout(deadlineTimer);
    deadlineTimer = setTimeout(
      () => {
        if (expected === generation) endSession(true);
      },
      Math.max(0, deadline - serverTime),
    );
    if (typeof window !== "undefined")
      window.dispatchEvent(
        new CustomEvent<User>(SESSION_USER_EVENT, { detail: active }),
      );
    return active;
  }

  function refresh(): Promise<User> {
    if (locallyBlocked || logoutWasRequested())
      return Promise.reject(new CanceledError("A saída foi solicitada."));
    if (refreshing) return refreshing;
    const pending = withSessionLock(async () => {
      if (locallyBlocked || logoutWasRequested())
        throw new CanceledError("A saída foi solicitada.");
      const expected = generation;
      const response = await auth.post<AccessResponse>(
        "api/v1/auth/refresh",
        {},
        { signal: controller.signal, timeout: AUTH_TIMEOUT_MS },
      );
      return applyAccess(response.data, expected);
    }).finally(() => {
      if (refreshing === pending) refreshing = null;
    });
    refreshing = pending;
    return pending;
  }

  function unauthorized() {
    endSession(true);
  }

  client.interceptors.request.use((config: RequestConfig) => {
    config.url = config.url?.replace(/^\/+/, "");
    config.sessionGeneration ??= generation;
    if (config.sessionGeneration !== generation)
      throw new CanceledError("Sessão encerrada.");
    config.signal = config.signal
      ? AbortSignal.any([config.signal as AbortSignal, controller.signal])
      : controller.signal;
    if (token) config.headers.set("Authorization", `Bearer ${token}`);
    else config.headers.delete("Authorization");
    return config;
  });

  client.interceptors.response.use(
    (response) => {
      if ((response.config as RequestConfig).sessionGeneration !== generation) {
        throw new CanceledError("Resposta de uma sessão encerrada.");
      }
      return response;
    },
    async (failure: AxiosError) => {
      const config = failure.config as RequestConfig | undefined;
      if (
        !config ||
        config.sessionGeneration !== generation ||
        axios.isCancel(failure)
      )
        throw failure;
      if (failure.response?.status !== 401) throw failure;
      if (config.retried) {
        unauthorized();
        throw failure;
      }
      config.retried = true;
      const expected = generation;
      try {
        await refresh();
      } catch (refreshError) {
        if (
          expected === generation &&
          axios.isAxiosError(refreshError) &&
          [401, 403].includes(refreshError.response?.status ?? 0)
        )
          unauthorized();
        throw refreshError;
      }
      if (expected !== generation) throw new CanceledError("Sessão encerrada.");
      return client(config);
    },
  );

  async function login(email: string, password: string) {
    // Uma resposta antiga de logout não pode limpar o cookie de um novo login.
    if (logoutPending) await logoutPending.catch(() => undefined);
    clear();
    const expected = generation;
    return withSessionLock(async () => {
      if (expected !== generation) throw new CanceledError("Sessão encerrada.");
      const response = await auth.post<AccessResponse>(
        "api/v1/auth/login",
        { email, password },
        { signal: controller.signal, timeout: AUTH_TIMEOUT_MS },
      );
      const result = applyAccess(response.data, expected);
      locallyBlocked = false;
      clearLogoutMarker();
      channel?.postMessage({ type: "login" } satisfies SessionMessage);
      try {
        localStorage.setItem(
          SESSION_CHANNEL,
          JSON.stringify({ type: "login", at: Date.now() }),
        );
      } catch {
        // A nova autenticação continua válida nesta aba.
      }
      return result;
    });
  }

  async function restore() {
    if (locallyBlocked || logoutWasRequested())
      throw new CanceledError("A saída foi solicitada.");
    if (logoutPending) await logoutPending.catch(() => undefined);
    return refresh();
  }

  async function validate() {
    if (!active || !token || locallyBlocked || logoutWasRequested())
      throw new CanceledError("A sessão não está disponível.");
    const expected = generation;
    const response = await client.get<User>("api/v1/auth/me", {
      timeout: AUTH_TIMEOUT_MS,
    });
    if (expected !== generation || response.data.id !== active.id) {
      locallyBlocked = true;
      clear();
      options.onUnauthorized?.();
      throw new CanceledError("A conta da sessão foi alterada.");
    }
    return active;
  }

  function logout(): Promise<void> {
    if (logoutPending) return logoutPending;
    const bearer = token;
    locallyBlocked = true;
    markLogoutRequested();
    clear();
    const pending = withSessionLock(() =>
      auth.post(
        "api/v1/auth/logout",
        {},
        {
          headers: bearer ? { Authorization: `Bearer ${bearer}` } : undefined,
          timeout: AUTH_TIMEOUT_MS,
        },
      ),
    )
      .then(() => undefined)
      .finally(() => {
        if (logoutPending === pending) logoutPending = null;
      });
    logoutPending = pending;
    channel?.postMessage({ type: "ended" } satisfies SessionMessage);
    try {
      localStorage.setItem(SESSION_CHANNEL, String(Date.now()));
    } catch {
      // A aba atual já foi limpa e o canal cobre o caso principal.
    }
    return pending;
  }

  function receiveEnded() {
    if (locallyBlocked && !token && !active) return;
    locallyBlocked = true;
    markLogoutRequested();
    clear();
    options.onUnauthorized?.();
  }

  channel?.addEventListener(
    "message",
    (event: MessageEvent<SessionMessage>) => {
      if (event.data?.type === "ended") receiveEnded();
      else if (event.data?.type === "login") {
        locallyBlocked = true;
        clear();
        options.onUnauthorized?.();
      }
    },
  );
  if (typeof window !== "undefined")
    window.addEventListener("storage", (event) => {
      if (event.key !== SESSION_CHANNEL || !event.newValue) return;
      try {
        const message = JSON.parse(event.newValue) as SessionMessage;
        if (message.type === "login") {
          locallyBlocked = true;
          clear();
          options.onUnauthorized?.();
        } else receiveEnded();
      } catch {
        receiveEnded();
      }
    });

  return {
    api: client,
    login,
    restore,
    validate,
    logout,
    currentUser: () => active,
  };
}

const session = createSession({
  baseURL:
    typeof document === "undefined"
      ? "http://localhost/"
      : new URL("./", document.baseURI).href,
  onUnauthorized: () => {
    if (typeof window !== "undefined")
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  },
});
export const { api, login, restore, validate, logout } = session;

async function page<T>(url: string, offset = 0, limit = 200): Promise<Page<T>> {
  const response = await api.get<Page<T>>(url, { params: { offset, limit } });
  return response.data;
}

async function all<T>(url: string): Promise<T[]> {
  const items: T[] = [];
  for (;;) {
    const result = await page<T>(url, items.length);
    items.push(...result.items);
    if (items.length >= result.total) return items;
    if (!result.items.length)
      throw new Error("A lista mudou durante a consulta. Atualize novamente.");
  }
}

function idempotency(key?: string) {
  return { headers: { "Idempotency-Key": key ?? crypto.randomUUID() } };
}
export type TaskCreate = {
  board_id: number;
  title: string;
  description?: string | null;
  priority: Task["priority"];
  type: Task["type"];
  assignee_id?: number | null;
  due_date?: string | null;
  label_ids?: number[];
};
export type TaskUpdate = Partial<
  Pick<Task, "title" | "description" | "priority" | "type" | "due_date">
> & { version: number; assignee_id?: number | null; label_ids?: number[] };

export const backend = {
  projects: () => all<Project>("api/v1/projects"),
  users: (q = "", includeInactive = false, offset = 0) =>
    api.get<Page<User>>("api/v1/users", { params: { q: q.trim() || undefined, include_inactive: includeInactive, offset, limit: 50 } }).then((result) => result.data),
  members: (projectId: number, offset = 0) => page<ProjectMember>(`api/v1/projects/${projectId}/members`, offset),
  allMembers: (projectId: number) => all<ProjectMember>(`api/v1/projects/${projectId}/members`),
  memberships: (userId: number) => all<Membership>(`api/v1/users/${userId}/memberships`),
  assignees: (projectId: number) => all<Participant>(`api/v1/projects/${projectId}/assignees`),
  addMember: (projectId: number, email: string, role: ProjectRole) =>
    api.put<ProjectMember>(`api/v1/projects/${projectId}/members`, { email, role }).then((r) => r.data),
  removeMember: (projectId: number, userId: number) => api.delete(`api/v1/projects/${projectId}/members/${userId}`),
  labels: (projectId: number, includeArchived = false) =>
    all<Label>(`api/v1/projects/${projectId}/labels?include_archived=${includeArchived}`),
  createLabel: (projectId: number, data: { name: string; color: LabelColor }) =>
    api.post<Label>(`api/v1/projects/${projectId}/labels`, data).then((r) => r.data),
  patchLabel: (id: number, data: Partial<Pick<Label, "name" | "color" | "is_archived">>) =>
    api.patch<Label>(`api/v1/labels/${id}`, data).then((r) => r.data),
  createUser: (data: { name: string; email: string; password: string; global_role?: "admin" | "user" }) =>
    api.post<User>("api/v1/users", data).then((r) => r.data),
  patchUser: (id: number, data: Partial<Pick<User, "name" | "email" | "is_active" | "global_role">>) =>
    api.patch<User>(`api/v1/users/${id}`, data).then((r) => r.data),
  resetPassword: (id: number, password: string) => api.post(`api/v1/users/${id}/reset-password`, { password }),
  changePassword: (current_password: string, new_password: string) => api.post("api/v1/auth/change-password", { current_password, new_password }),
  taskByCode: (code: string) => api.get<Task>(`api/v1/tasks/by-code/${encodeURIComponent(code)}`).then((r) => r.data),
  board: (id: number, offset = 0) =>
    api
      .get<Board>(`api/v1/boards/${id}`, {
        params: { tasks_offset: offset, tasks_limit: 200 },
      })
      .then((response) => response.data),
  task: (id: number) =>
    api.get<Task>(`api/v1/tasks/${id}`).then((response) => response.data),
  createProject: (
    data: Pick<Project, "key" | "name" | "description" | "legacy_app_id">,
    key?: string,
  ) =>
    api
      .post<Project>("api/v1/projects", data, idempotency(key))
      .then((response) => response.data),
  createTask: (data: TaskCreate, key?: string) =>
    api
      .post<Task>("api/v1/tasks", data, idempotency(key))
      .then((response) => response.data),
  patchTask: (id: number, data: TaskUpdate) =>
    api
      .patch<Task>(`api/v1/tasks/${id}`, data)
      .then((response) => response.data),
  move: (id: number, column_id: number, position: number, version: number) =>
    api
      .patch<Task>(`api/v1/tasks/${id}/move`, { column_id, position, version })
      .then((response) => response.data),
  comments: (id: number, offset = 0, limit = 50) =>
    page<Comment>(`api/v1/tasks/${id}/comments`, offset, limit),
  addComment: (id: number, body: string, key?: string) =>
    api
      .post<Comment>(`api/v1/tasks/${id}/comments`, { body }, idempotency(key))
      .then((response) => response.data),
  history: (id: number, offset = 0, limit = 50) =>
    page<History>(`api/v1/tasks/${id}/history`, offset, limit),
  addColumn: (board: number, name: string, is_done: boolean) =>
    api.post<Column>(`api/v1/boards/${board}/columns`, { name, is_done }),
  patchColumn: (id: number, data: Partial<Column>) =>
    api.patch<Column>(`api/v1/columns/${id}`, data),
  deleteColumn: (id: number) => api.delete(`api/v1/columns/${id}`),
  patchBoard: (
    id: number,
    data: { name?: string; default_column_id?: number },
  ) =>
    api
      .patch<Board>(`api/v1/boards/${id}`, data)
      .then((response) => response.data),
};

export function error(failure: unknown): string {
  if (axios.isAxiosError(failure)) {
    const detail = failure.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") return detail.message;
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" ");
    if (!failure.response)
      return "Não foi possível conectar. Confira sua conexão e tente novamente.";
  }
  return "Não foi possível concluir a ação.";
}
