import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  backend,
  error,
  logout,
  restore,
  UNAUTHORIZED_EVENT,
  validate,
} from "./api";
import type { User } from "./types";
import { LoginPage } from "./pages/LoginPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import BoardPage from "./pages/BoardPage";
import { RequestFormPage, RequestReviewPage } from "./pages/RequestsPage";
import { TaskPage } from "./pages/TaskPage";
import { TaskDialog } from "./components/TaskDialog";
import NewsPage from "./pages/NewsPage";
import PortfolioPage from "./pages/PortfolioPage";
import { UsersPage } from "./pages/UsersPage";
import { AccountPage } from "./pages/AccountPage";
import { TeamPage } from "./pages/TeamPage";
import { LabelsPage } from "./pages/LabelsPage";
import {
  PublicNewsPage,
  PublicWorkPage,
  PublicRequestPage,
  PublicTrackingPage,
} from "./pages/PublicPages";
import { PublicationPage } from "./pages/PublicationPage";
import {
  appHref,
  currentPath,
  installNavigation,
  loginDestination,
  NAVIGATION_EVENT,
  navigate,
  publicHref,
  visit,
  workspaceRoute,
} from "./lib/navigation";
import "./style.css";
import "./pages/AdminPage.css";

const NO_USERS: User[] = [];

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [path, setPath] = useState(currentPath);
  const [boardRevision, setBoardRevision] = useState(0);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const pathnamePublic = path.split("?")[0].replace(/\/$/, "") || "/";
  const requiresSession =
    pathnamePublic === "/login" || /^\/app(?:\/|$)/.test(pathnamePublic);
  const route = workspaceRoute(path);

  useEffect(() => {
    const changed = () => setPath(currentPath());
    const expired = () => {
      setUser(null);
      setReady(true);
    };
    window.addEventListener(NAVIGATION_EVENT, changed);
    window.addEventListener(UNAUTHORIZED_EVENT, expired);
    const dispose = installNavigation();
    changed();
    return () => {
      dispose();
      window.removeEventListener(NAVIGATION_EVENT, changed);
      window.removeEventListener(UNAUTHORIZED_EVENT, expired);
    };
  }, []);

  useEffect(() => {
    if (!requiresSession) {
      setReady(false);
      return;
    }
    if (user) {
      setReady(true);
      return;
    }
    let mounted = true;
    setReady(false);
    restore()
      .then((value) => {
        if (mounted) setUser(value);
      })
      .catch(() => {
        if (mounted) setUser(null);
      })
      .finally(() => {
        if (mounted) setReady(true);
      });
    return () => {
      mounted = false;
    };
  }, [requiresSession]);

  useEffect(() => {
    if (!requiresSession || !user) return;
    let mounted = true;
    let validating = false;
    const revalidate = () => {
      if (document.visibilityState === "hidden") return;
      if (!mounted || validating) return;
      validating = true;
      setReady(false);
      void validate()
        .catch(() => {
          if (mounted) {
            setReady(true);
            setUser(null);
          }
        })
        .finally(() => {
          validating = false;
          if (mounted) setReady(true);
        });
    };
    window.addEventListener("focus", revalidate);
    window.addEventListener("pageshow", revalidate);
    window.addEventListener("visibilitychange", revalidate);
    return () => {
      mounted = false;
      window.removeEventListener("focus", revalidate);
      window.removeEventListener("pageshow", revalidate);
      window.removeEventListener("visibilitychange", revalidate);
    };
  }, [requiresSession, user]);

  useEffect(() => {
    if (!requiresSession || !ready) return;
    if (!user && pathnamePublic !== "/login")
      visit(`/login?next=${encodeURIComponent(path)}`, true);
    else if (user && pathnamePublic === "/login")
      visit(loginDestination(location.search), true);
  }, [path, requiresSession, ready, user, pathnamePublic]);

  async function signOut() {
    setUser(null);
    visit("/");
    setLogoutBusy(true);
    setLogoutError("");
    try {
      await logout();
    } catch (failure) {
      setLogoutError(
        `Não foi possível confirmar a saída no servidor. ${error(failure)}`,
      );
    } finally {
      setLogoutBusy(false);
    }
  }

  if (!requiresSession)
    return (
      <PublicPortal
        path={pathnamePublic}
        user={user}
        logoutError={logoutError}
        retryLogout={signOut}
      />
    );
  if (!ready)
    return (
      <main className="loading" role="status">
        Verificando seu acesso…
      </main>
    );
  if (!user)
    return (
      <LoginPage
        disabled={logoutBusy}
        logoutError={logoutError}
        retryLogout={signOut}
        onLogin={(value) => {
          setUser(value);
          setReady(true);
          setLogoutError("");
          visit(loginDestination(location.search), true);
        }}
      />
    );

  const pathname = route.split("?")[0];
  const boardId = /^board\/(\d+)$/.exec(pathname)?.[1];
  const taskId = /^tasks\/(\d+)$/.exec(pathname)?.[1];
  const taskCode = /^task\/([A-Z][A-Z0-9_]*-\d+)$/.exec(pathname)?.[1];
  const teamProjectId = /^projects\/(\d+)\/team$/.exec(pathname)?.[1];
  const labelsProjectId = /^projects\/(\d+)\/labels$/.exec(pathname)?.[1];
  const projectId = /^projects\/(\d+)$/.exec(pathname)?.[1];
  const gitProjectId = /^projects\/git\/(.+)$/.exec(pathname)?.[1];
  const query = new URLSearchParams(route.split("?")[1]);
  const taskBoard = query.get("board");
  const workspaceBoardId =
    boardId ||
    ((taskId || taskCode) && taskBoard && /^\d+$/.test(taskBoard)
      ? taskBoard
      : undefined);
  const closeTask = (loadedBoardId?: number) => {
    const board = workspaceBoardId || loadedBoardId;
    const target = board ? `board/${board}` : "projects";
    navigate(target, true);
  };
  const taskChanged = () => setBoardRevision((value) => value + 1);
  const newsRoute =
    pathname === "news" ||
    pathname.startsWith("news/") ||
    pathname === "git" ||
    pathname.startsWith("git/");
  const portfolioRoute =
    pathname === "priorities" || pathname === "prioridades";
  const requestFormRoute = pathname === "request" || pathname === "solicitar";
  const requestsRoute = pathname === "requests" || pathname === "solicitacoes";
  const prototypeRoute =
    !user.must_change_password &&
    (Boolean(workspaceBoardId) ||
      portfolioRoute ||
      requestFormRoute ||
      requestsRoute ||
      newsRoute ||
      pathname === "projects" ||
      Boolean(projectId) ||
      Boolean(gitProjectId));
  let content;
  if (user.must_change_password)
    content = <AccountPage user={user} required done={() => setUser(null)} />;
  else if (pathname === "account")
    content = <AccountPage user={user} done={() => setUser(null)} />;
  else if (pathname === "publication")
    content = <PublicationPage user={user} />;
  else if (pathname === "admin/users" && user.global_role === "admin")
    content = <UsersPage />;
  else if (teamProjectId)
    content = (
      <ProjectRoute
        key={`team-${teamProjectId}`}
        projectId={Number(teamProjectId)}
        page="team"
      />
    );
  else if (labelsProjectId)
    content = (
      <ProjectRoute
        key={`labels-${labelsProjectId}`}
        projectId={Number(labelsProjectId)}
        page="labels"
      />
    );
  else if (requestFormRoute) content = <RequestFormPage user={user} />;
  else if (requestsRoute) content = <RequestReviewPage user={user} />;
  else if (portfolioRoute) content = <PortfolioPage />;
  else if (newsRoute) content = <NewsPage />;
  else if (
    pathname === "projects" ||
    pathname === "tasks" ||
    projectId ||
    gitProjectId
  )
    content = (
      <ProjectsPage
        key={projectId || gitProjectId || pathname}
        projectId={projectId ? Number(projectId) : undefined}
        gitId={gitProjectId}
        autoOpen={pathname === "tasks"}
        canCreate={user.global_role === "admin"}
      />
    );
  else if (workspaceBoardId)
    content = (
      <BoardPage
        key={workspaceBoardId}
        id={Number(workspaceBoardId)}
        refreshKey={boardRevision}
        openCreate={query.get("newTask") === "1"}
        open={(id) => navigate(`tasks/${id}?board=${workspaceBoardId}`)}
      />
    );
  else if (taskId || taskCode)
    content = (
      <ProjectsPage autoOpen={false} canCreate={user.global_role === "admin"} />
    );
  else
    content = (
      <section className="empty-state">
        <h1>Página não encontrada</h1>
        <button onClick={() => navigate("tasks")}>Voltar ao quadro</button>
      </section>
    );

  return (
    <div
      className={
        prototypeRoute ? "app-frame app-frame--prototype" : "app-frame"
      }
    >
      <a
        className="skip-link"
        href="#conteudo"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("conteudo")?.focus();
        }}
      >
        Ir para o conteúdo
      </a>
      <header className="app-header">
        <a
          className="brand"
          href={appHref("#/news")}
          aria-label="Jornalzinho — início"
        >
          <strong className="brand-wordmark">J</strong>
          <span aria-hidden="true" />
          Jornalzinho
        </a>
        <nav aria-label="Navegação principal">
          <a
            href={appHref("#/news")}
            aria-current={newsRoute ? "page" : undefined}
          >
            Novidades
          </a>
          <a
            href={appHref("#/projects")}
            aria-current={pathname.startsWith("projects") ? "page" : undefined}
          >
            Projetos
          </a>
          <a
            href={appHref("#/priorities")}
            aria-current={portfolioRoute ? "page" : undefined}
          >
            Prioridades
          </a>
          <a
            href={appHref("#/tasks")}
            aria-current={
              pathname === "tasks" || boardId || taskId || taskCode
                ? "page"
                : undefined
            }
          >
            Tarefas
          </a>
          <a
            href={appHref("#/request")}
            aria-current={requestFormRoute ? "page" : undefined}
          >
            Solicitar
          </a>
          <a
            href={appHref("requests")}
            aria-current={requestsRoute ? "page" : undefined}
          >
            Solicitações
          </a>
          <a
            href={appHref("publication")}
            aria-current={pathname === "publication" ? "page" : undefined}
          >
            Publicação
          </a>
          <a href={publicHref("/")}>Portal público</a>
          {user.global_role === "admin" && (
            <a
              href={appHref("#/admin/users")}
              aria-current={pathname === "admin/users" ? "page" : undefined}
            >
              Usuários
            </a>
          )}
        </nav>
        <div className="account">
          <a href={appHref("#/account")}>{user.name}</a>
          <button className="quiet" onClick={() => void signOut()}>
            Sair
          </button>
        </div>
      </header>
      <main id="conteudo" tabIndex={-1} key={user.id}>
        {content}

        {!user.must_change_password && taskId && (
          <TaskPage
            key={taskId}
            taskId={Number(taskId)}
            users={NO_USERS}
            back={closeTask}
            onChanged={taskChanged}
          />
        )}
        {!user.must_change_password && taskCode && (
          <TaskCodeRoute
            key={taskCode}
            code={taskCode}
            back={closeTask}
            onChanged={taskChanged}
          />
        )}
      </main>
      <footer className="app-footer">
        Jornalzinho · demonstração local
      </footer>
    </div>
  );
}

function PublicPortal({
  path,
  user,
  logoutError,
  retryLogout,
}: {
  path: string;
  user: User | null;
  logoutError: string;
  retryLogout: () => Promise<void>;
}) {
  let content;
  const news = /^\/noticias\/([^/]+)$/.exec(path)?.[1];
  const work = /^\/acompanhar\/([^/]+)$/.exec(path)?.[1];
  if (path === "/" || path === "/noticias") content = <PublicNewsPage />;
  else if (news) content = <PublicNewsPage key={news} id={news} />;
  else if (path === "/acompanhar" || work)
    content = <PublicWorkPage key={work ?? "list"} code={work} />;
  else if (path === "/solicitar") content = <PublicRequestPage />;
  else if (path === "/minha-solicitacao") content = <PublicTrackingPage />;
  else
    content = (
      <section className="empty-state">
        <h1>Página não encontrada</h1>
        <a href={publicHref("/")}>Voltar às notícias</a>
      </section>
    );
  return (
    <div className="app-frame public-frame">
      <a
        className="skip-link"
        href="#conteudo"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("conteudo")?.focus();
        }}
      >
        Ir para o conteúdo
      </a>
      <header className="app-header">
        <a
          className="brand"
          href={publicHref("/")}
          aria-label="Jornalzinho — início"
        >
          <strong className="brand-wordmark">J</strong>
          <span aria-hidden="true" />
          Jornalzinho
        </a>
        <nav aria-label="Navegação pública">
          <a
            href={publicHref("/")}
            aria-current={path === "/" || news ? "page" : undefined}
          >
            Notícias
          </a>
          <a
            href={publicHref("/acompanhar")}
            aria-current={path.startsWith("/acompanhar") ? "page" : undefined}
          >
            Acompanhar
          </a>
          <a
            href={publicHref("/solicitar")}
            aria-current={path === "/solicitar" ? "page" : undefined}
          >
            Solicitar
          </a>
          <a
            href={publicHref("/minha-solicitacao")}
            aria-current={path === "/minha-solicitacao" ? "page" : undefined}
          >
            Minha solicitação
          </a>
        </nav>
        <a
          className="public-login-link"
          href={publicHref(user ? "/app" : "/login")}
        >
          {user ? "Área da equipe" : "Entrar"}
        </a>
      </header>
      <main id="conteudo" tabIndex={-1}>
        {logoutError && (
          <div className="error" role="alert">
            <p>{logoutError}</p>
            <button onClick={() => void retryLogout()}>
              Tentar sair novamente
            </button>
          </div>
        )}
        {content}
      </main>
      <footer className="app-footer">
        Jornalzinho · acompanhe o trabalho da equipe
      </footer>
    </div>
  );
}

function ProjectRoute({
  projectId,
  page,
}: {
  projectId: number;
  page: "team" | "labels";
}) {
  const [project, setProject] = useState<import("./types").Project | null>(
    null,
  );
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let mounted = true;
    void backend
      .projects()
      .then((items) => {
        if (!mounted) return;
        const found = items.find((item) => item.id === projectId);
        if (found) setProject(found);
        else setNotice("O projeto não está disponível para sua conta.");
      })
      .catch((failure) => {
        if (mounted) setNotice(error(failure));
      });
    return () => {
      mounted = false;
    };
  }, [projectId]);
  if (notice)
    return (
      <section className="empty-state" role="alert">
        <h1>Projeto indisponível</h1>
        <p>{notice}</p>
      </section>
    );
  if (!project)
    return (
      <section className="loading" role="status">
        Carregando projeto…
      </section>
    );
  return page === "team" ? (
    <TeamPage project={project} role={project.role} />
  ) : (
    <LabelsPage project={project} role={project.role} />
  );
}

function TaskCodeRoute({
  code,
  back,
  onChanged,
}: {
  code: string;
  back: (boardId?: number) => void;
  onChanged: () => void;
}) {
  const [taskId, setTaskId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let mounted = true;
    void backend
      .taskByCode(code)
      .then((task) => {
        if (mounted) setTaskId(task.id);
      })
      .catch((failure) => {
        if (mounted) setNotice(error(failure));
      });
    return () => {
      mounted = false;
    };
  }, [code]);
  if (notice || taskId === null)
    return (
      <TaskDialog onClose={back} code={code}>
        <section
          className={notice ? "empty-state" : "loading"}
          role={notice ? "alert" : "status"}
        >
          {notice ? (
            <>
              <h1>Tarefa indisponível</h1>
              <p>{notice}</p>
            </>
          ) : (
            "Carregando tarefa…"
          )}
        </section>
      </TaskDialog>
    );
  return (
    <TaskPage
      key={taskId}
      taskId={taskId}
      users={NO_USERS}
      back={back}
      onChanged={onChanged}
    />
  );
}

createRoot(document.getElementById("root")!).render(<App />);
