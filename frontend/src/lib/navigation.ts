/** Rotas do portal e do espaço da equipe, incluindo links antigos do Kanban. */
export const NAVIGATION_EVENT = "jornalzinho:navigation";

const segments: Record<string, string> = {
  projects: "projetos",
  priorities: "prioridades",
  prioridades: "prioridades",
  board: "kanban",
  tasks: "tarefas",
  task: "tarefa",
  news: "noticias",
  request: "solicitar",
  solicitar: "solicitar",
  requests: "solicitacoes",
  solicitacoes: "solicitacoes",
  account: "conta",
  publication: "publicacao",
};
const internal: Record<string, string> = {
  projetos: "projects",
  prioridades: "priorities",
  kanban: "board",
  tarefas: "tasks",
  tarefa: "task",
  noticias: "news",
  solicitar: "request",
  solicitacoes: "requests",
  conta: "account",
  publicacao: "publication",
};

export function legacyPath(route: string): string {
  const clean = route.replace(/^#?\/?/, "");
  const [path, ...query] = clean.split("?");
  let target: string;
  if (!path || path === "tasks") target = "/app";
  else if (path === "admin/users") target = "/app/admin/usuarios";
  else {
    const [first, ...rest] = path.split("/");
    target = `/app/${[segments[first] ?? first, ...rest].join("/")}`;
  }
  return target + (query.length ? `?${query.join("?")}` : "");
}

export function workspaceRoute(path: string): string {
  const [pathname, ...query] = path.split("?");
  const clean = pathname.replace(/^\/app\/?/, "");
  const [first, ...rest] = clean.split("/");
  const route = !clean
    ? "tasks"
    : clean === "admin/usuarios"
      ? "admin/users"
      : [internal[first] ?? first, ...rest].join("/");
  return route + (query.length ? `?${query.join("?")}` : "");
}

export function basePath(): string {
  return typeof document === "undefined"
    ? "/"
    : new URL(document.baseURI).pathname;
}

export function publicHref(path: string): string {
  return `${basePath().replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

export const appHref = (route: string) => publicHref(legacyPath(route));

export function currentPath(): string {
  if (location.hash.startsWith("#/")) return legacyPath(location.hash);
  const prefix = basePath().replace(/\/$/, "");
  const path = location.pathname;
  return (
    (prefix && (path === prefix || path.startsWith(`${prefix}/`))
      ? path.slice(prefix.length) || "/"
      : path) + location.search
  );
}

export const currentWorkspaceRoute = () => workspaceRoute(currentPath());

export function visit(path: string, replace = false): void {
  const target = publicHref(path);
  if (replace) history.replaceState(history.state, "", target);
  else history.pushState(null, "", target);
  window.dispatchEvent(new Event(NAVIGATION_EVENT));
}

export const navigate = (route: string, replace = false) =>
  visit(legacyPath(route), replace);

/** Aceita apenas destinos da área interna; nunca redireciona para outro domínio. */
export function loginDestination(search: string): string {
  const candidate = new URLSearchParams(search).get("next");
  if (
    !candidate ||
    !/^\/app(?:\/|\?|$)/.test(candidate) ||
    /[\\#\r\n]/.test(candidate)
  )
    return "/app";
  const parsed = new URL(candidate, "https://jornalzinho.invalid");
  return parsed.origin === "https://jornalzinho.invalid" &&
    /^\/app(?:\/|$)/.test(parsed.pathname)
    ? parsed.pathname + parsed.search
    : "/app";
}

export function installNavigation(): () => void {
  const legacy = () => {
    if (location.hash.startsWith("#/")) navigate(location.hash, true);
  };
  const changed = () => {
    legacy();
    window.dispatchEvent(new Event(NAVIGATION_EVENT));
  };
  const clicked = (event: MouseEvent) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    const anchor = (event.target as Element | null)?.closest<HTMLAnchorElement>(
      "a[href]",
    );
    if (
      !anchor ||
      anchor.hasAttribute("download") ||
      (anchor.target && anchor.target !== "_self")
    )
      return;
    const raw = anchor.getAttribute("href") ?? "";
    if (raw.startsWith("#/")) {
      event.preventDefault();
      navigate(raw);
      return;
    }
    const url = new URL(anchor.href);
    if (
      url.origin !== location.origin ||
      url.hash ||
      !url.pathname.startsWith(basePath())
    )
      return;
    const path = `/${url.pathname.slice(basePath().length)}`;
    if (
      !/^\/(?:$|login\/?$|noticias(?:\/|$)|acompanhar(?:\/|$)|solicitar\/?$|minha-solicitacao\/?$|app(?:\/|$))/.test(
        path,
      )
    )
      return;
    event.preventDefault();
    visit(path + url.search);
  };
  legacy();
  addEventListener("popstate", changed);
  addEventListener("hashchange", changed);
  document.addEventListener("click", clicked);
  return () => {
    removeEventListener("popstate", changed);
    removeEventListener("hashchange", changed);
    document.removeEventListener("click", clicked);
  };
}
