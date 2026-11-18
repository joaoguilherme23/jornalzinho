import { api, backend } from "../api";
import type { Participant } from "../types";
import type { ProjectRole } from "../types";

export type PortfolioPriority = "low" | "medium" | "high";
export type PortfolioStatus =
  "planned" | "in_progress" | "waiting" | "completed";
export type PortfolioLink = { label: string; url: string };
export type PortfolioTask = {
  id: number;
  code: string;
  title: string;
  due_date: string | null;
  priority: string;
};
export type PortfolioChange = {
  sha: string;
  tipo: string;
  escopo?: string | null;
  titulo: string;
  data: string;
  url?: string | null;
};
export type PortfolioChanges = {
  novidades?: PortfolioChange[];
  correcoes?: PortfolioChange[];
  melhorias?: PortfolioChange[];
  outros?: PortfolioChange[];
};
export type PortfolioGit = {
  id: string;
  nome: string;
  repositorio?: string | null;
  url_github?: string | null;
  branch?: string | null;
  versao_atual?: string | null;
  versao_data?: string | null;
  commits_desde_versao?: number;
  ultimo_commit?: {
    sha: string;
    data: string;
    assunto: string;
    url?: string | null;
  } | null;
  releases?: {
    versao: string;
    data: string;
    resumo?: string | null;
    url_comparacao?: string | null;
    total_mudancas?: number;
    mudancas?: PortfolioChanges;
  }[];
  nao_versionadas?: PortfolioChanges;
  erro?: string | null;
  areas?: string[];
};
export type PortfolioItem = {
  ref: string;
  project_id: number | null;
  legacy_app_id: string | null;
  board_id: number | null;
  version: number;
  name: string;
  description: string | null;
  priority: PortfolioPriority | null;
  status: PortfolioStatus | null;
  owner: Participant | null;
  due_date: string | null;
  objective: string | null;
  milestone_title: string | null;
  milestone_due_date: string | null;
  links: PortfolioLink[];
  pending_tasks: PortfolioTask[];
  pending_tasks_total: number;
  git: PortfolioGit | null;
  role?: ProjectRole | "admin";
};
export type PortfolioResponse = {
  git_collected_at: string;
  items: PortfolioItem[];
};
export type PortfolioHealth =
  "finalizado" | "atraso" | "critico" | "aguardando" | "a-definir" | "em-dia";
export type PortfolioUpdate = Partial<
  Pick<
    PortfolioItem,
    | "priority"
    | "status"
    | "due_date"
    | "objective"
    | "milestone_title"
    | "milestone_due_date"
    | "links"
  >
> & { version: number; owner_id?: number | null };

export const portfolioApi = {
  list: () =>
    api.get<PortfolioResponse>("api/v1/portfolio").then((r) => r.data),
  save: (item: PortfolioItem, payload: PortfolioUpdate) =>
    item.project_id !== null
      ? api
          .patch<PortfolioItem>(
            `api/v1/portfolio/projects/${item.project_id}`,
            payload,
          )
          .then((r) => r.data)
      : api
          .put<PortfolioItem>(
            `api/v1/portfolio/apps/${encodeURIComponent(item.legacy_app_id ?? item.git?.id ?? "")}`,
            payload,
          )
          .then((r) => r.data),
};

const normalizar = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
export const textoInclui = (source: string, query: string) =>
  !query || normalizar(source).includes(normalizar(query));
export function urlSegura(value: string): string | null {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
export function healthOf(item: PortfolioItem): {
  value: PortfolioHealth;
  reason: string;
} {
  if (item.status === "completed")
    return { value: "finalizado", reason: "Status finalizado" };
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
  }).format(new Date());
  if (item.due_date && item.due_date < today)
    return {
      value: "atraso",
      reason: `Prazo vencido em ${formatDate(item.due_date)}`,
    };
  if (item.milestone_due_date && item.milestone_due_date < today)
    return {
      value: "atraso",
      reason: `Marco vencido em ${formatDate(item.milestone_due_date)}`,
    };
  if (item.pending_tasks.some((task) => task.priority === "critical"))
    return { value: "critico", reason: "Há tarefa crítica em aberto" };
  if (item.status === "waiting")
    return { value: "aguardando", reason: "Status aguardando" };
  if (
    !item.priority ||
    !item.status ||
    !item.owner ||
    !item.objective ||
    !item.due_date
  )
    return {
      value: "a-definir",
      reason: "Faltam metadados ou prazo para acompanhar",
    };
  return { value: "em-dia", reason: "Metadados e prazo em dia" };
}
export type RecentGitChange = {
  key: string;
  projectRef: string;
  projectName: string;
  appId: string;
  title: string;
  date: string;
  kind: "release" | "commit";
  url: string | null;
};
function timestamp(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}
export function recentGitChanges(
  items: PortfolioItem[],
  days: 7 | 15 | 30,
  now = Date.now(),
): RecentGitChange[] {
  const cutoff = now - days * 86_400_000;
  const output: RecentGitChange[] = [];
  const seen = new Set<string>();
  const add = (entry: RecentGitChange) => {
    const time = timestamp(entry.date);
    if (
      time !== null &&
      time >= cutoff &&
      time <= now &&
      !seen.has(entry.key)
    ) {
      seen.add(entry.key);
      output.push(entry);
    }
  };
  for (const item of items) {
    const git = item.git;
    if (!git) continue;
    const releasedShas = new Set(
      (git.releases ?? []).flatMap((release) =>
        Object.values(release.mudancas ?? {})
          .flat()
          .map((change) => change.sha),
      ),
    );
    for (const release of git.releases ?? [])
      add({
        key: `release:${git.id}:${release.versao}:${release.data}`,
        projectRef: item.ref,
        projectName: item.name,
        appId: git.id,
        title: release.resumo || `Release ${release.versao}`,
        date: release.data,
        kind: "release",
        url: release.url_comparacao ? urlSegura(release.url_comparacao) : null,
      });
    for (const change of Object.values(git.nao_versionadas ?? {}).flat())
      if (change && !releasedShas.has(change.sha))
        add({
          key: `commit:${git.id}:${change.sha}`,
          projectRef: item.ref,
          projectName: item.name,
          appId: git.id,
          title: change.titulo,
          date: change.data,
          kind: "commit",
          url: change.url ? urlSegura(change.url) : null,
        });
    const commit = git.ultimo_commit;
    if (
      commit &&
      !releasedShas.has(commit.sha) &&
      (!git.releases?.length || (git.commits_desde_versao ?? 0) > 0)
    )
      add({
        key: `commit:${git.id}:${commit.sha}`,
        projectRef: item.ref,
        projectName: item.name,
        appId: git.id,
        title: commit.assunto,
        date: commit.data,
        kind: "commit",
        url: commit.url ? urlSegura(commit.url) : null,
      });
  }
  return output.sort(
    (first, second) =>
      (timestamp(second.date) ?? 0) - (timestamp(first.date) ?? 0),
  );
}
export function formatDate(value: string | null | undefined): string {
  if (!value) return "Não informado";
  const pureDate = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = new Date(pureDate ? `${value}T12:00:00Z` : value);
  if (!Number.isFinite(date.getTime())) return "Não informado";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeZone: "America/Sao_Paulo",
  }).format(date);
}
export const labelPriority: Record<PortfolioPriority | "none", string> = {
  high: "Alta",
  medium: "Média",
  low: "Baixa",
  none: "Sem prioridade",
};
export const labelStatus: Record<PortfolioStatus | "none", string> = {
  planned: "Planejado",
  in_progress: "Em andamento",
  waiting: "Aguardando",
  completed: "Finalizado",
  none: "A definir",
};
