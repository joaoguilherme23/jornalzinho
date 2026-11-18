import { FormEvent, useEffect, useRef, useState } from "react";
import axios from "axios";
import { normalizeExampleUrl } from "../lib/example-url";
import {
  fileToAttachment,
  requestTypes,
  urgencyLabels,
  type RequestPayload,
} from "../lib/requests";
import {
  attachmentPayload,
  newKey,
  publicApi,
  publicError,
  secureRequestKey,
  type PublicNews,
  type PublicRequestDraft,
  type PublicWork,
  type PublicProject,
} from "../lib/public";
import { publicHref } from "../lib/navigation";
import "./PublicPages.css";

const date = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
        new Date(value),
      )
    : "Sem data";
const link = publicHref;
const executionLabels: Record<string, string> = {
  planned: "A fazer",
  in_progress: "Em andamento",
  waiting: "Aguardando",
  completed: "Concluído",
  archived: "Arquivada",
};
const reviewLabels: Record<string, string> = {
  em_avaliacao: "Em avaliação",
  ajuste: "Precisa de ajuste",
  aprovado: "Aprovada",
  recusado: "Recusada",
};
const decoded = (value: string) => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};
function Loading() {
  return (
    <div className="public-skeleton" aria-label="Carregando" role="status">
      <i />
      <i />
      <i />
    </div>
  );
}
function Failure({ message, retry }: { message: string; retry: () => void }) {
  return (
    <section className="public-alert" role="alert">
      <p>{message}</p>
      <button onClick={() => retry()}>Tentar novamente</button>
    </section>
  );
}
function WorkCard({ item }: { item: PublicWork }) {
  return (
    <a
      className="public-card"
      href={link(`/acompanhar/${encodeURIComponent(item.code)}`)}
    >
      <small>
        {item.project_name} · {executionLabels[item.status] ?? item.status}
      </small>
      <h2>{item.title}</h2>
      <p>{item.summary || "Atualização em andamento."}</p>
      <span>Atualizado em {date(item.updated_at)}</span>
    </a>
  );
}
function Pagination({
  offset,
  total,
  load,
}: {
  offset: number;
  total: number;
  load: (offset: number) => void;
}) {
  const limit = 12;
  if (total <= limit) return null;
  return (
    <nav className="public-pagination" aria-label="Paginação">
      <button
        disabled={offset === 0}
        onClick={() => load(Math.max(0, offset - limit))}
      >
        Anterior
      </button>
      <span>
        {Math.floor(offset / limit) + 1} de {Math.ceil(total / limit)}
      </span>
      <button
        disabled={offset + limit >= total}
        onClick={() => load(offset + limit)}
      >
        Próxima
      </button>
    </nav>
  );
}

export function PublicNewsPage({ id }: { id?: string }) {
  const [item, setItem] = useState<PublicNews | null>(null);
  const [page, setPage] = useState<{
    items: PublicNews[];
    total: number;
    offset: number;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const revision = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const load = (offset = 0) => {
    const current = ++revision.current;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setNotice("");
    if (!id) setPage(null);
    (id
      ? publicApi.newsById(decoded(id)).then((value) => {
          if (current === revision.current) setItem(value);
        })
      : publicApi.news({ offset }, controller.signal).then((value) => {
          if (current === revision.current) setPage(value);
        })
    ).catch((e) => {
      if (!axios.isCancel(e) && current === revision.current)
        setNotice(publicError(e));
    });
    return () => {
      pending.current?.abort();
      revision.current += 1;
    };
  };
  useEffect(() => load(), [id]);
  if (notice)
    return (
      <section className="public-page">
        <Failure message={notice} retry={load} />
      </section>
    );
  if (id)
    return (
      <section className="public-page">
        {!item ? (
          <Loading />
        ) : (
          <article className="public-article">
            <a href={link("/")}>← Notícias</a>
            <p>
              {item.project_name || "Atualização"} · {date(item.published_at)}
            </p>
            <h1>{item.title}</h1>
            <strong>{item.summary}</strong>
            <div className="public-body">
              {item.body?.split("\n").map((line, index) => (
                <p key={index}>{line}</p>
              ))}
            </div>
          </article>
        )}
      </section>
    );
  return (
    <section className="public-page">
      <header className="public-hero">
        <p>Atualizações</p>
        <h1>O que estamos construindo.</h1>
        <span>Acompanhe novidades e melhorias publicadas pela equipe.</span>
      </header>
      {!page ? (
        <Loading />
      ) : !page.items.length ? (
        <p className="public-empty">Ainda não há notícias publicadas.</p>
      ) : (
        <>
          <section className="public-grid">
            {page.items.map((news) => (
              <a
                className="public-card"
                key={news.id}
                href={link(`/noticias/${news.id}`)}
              >
                <small>
                  {news.project_name || "Atualização"} ·{" "}
                  {date(news.published_at)}
                </small>
                <h2>{news.title}</h2>
                <p>{news.summary}</p>
                <b>Ler atualização →</b>
              </a>
            ))}
          </section>
          <Pagination offset={page.offset} total={page.total} load={load} />
        </>
      )}
    </section>
  );
}

export function PublicWorkPage({ code }: { code?: string }) {
  const [work, setWork] = useState<PublicWork | null>(null);
  const [page, setPage] = useState<{
    items: PublicWork[];
    total: number;
    offset: number;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [q, setQ] = useState("");
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [projects, setProjects] = useState<PublicProject[]>([]);
  const filters = useRef<{ q?: string; project_id?: number; status?: string }>(
    {},
  );
  const request = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const load = (offset = 0) => {
    const revision = ++request.current;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setNotice("");
    if (!code) setPage(null);
    (code
      ? publicApi.workByCode(decoded(code))
      : publicApi.work({ ...filters.current, offset }, controller.signal)
    )
      .then((data) => {
        if (revision !== request.current) return;
        if (code) setWork(data as PublicWork);
        else
          setPage(
            data as { items: PublicWork[]; total: number; offset: number },
          );
      })
      .catch((e) => {
        if (!axios.isCancel(e) && revision === request.current)
          setNotice(publicError(e));
      });
    return () => {
      pending.current?.abort();
      request.current += 1;
    };
  };
  useEffect(() => load(), [code]);
  useEffect(() => {
    if (code) return;
    let mounted = true;
    publicApi
      .projects()
      .then((items) => {
        if (mounted) setProjects(items);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [code]);
  if (notice)
    return (
      <section className="public-page">
        <Failure message={notice} retry={load} />
      </section>
    );
  if (code)
    return (
      <section className="public-page">
        {!work ? (
          <Loading />
        ) : (
          <article className="public-article">
            <a href={link("/acompanhar")}>← Acompanhar trabalho</a>
            <p>
              {work.project_name} ·{" "}
              {executionLabels[work.status] ?? work.status}
            </p>
            <h1>{work.title}</h1>
            <strong>
              {work.summary ||
                "Esta entrega está sendo acompanhada pela equipe."}
            </strong>
            <p>Última atualização: {date(work.updated_at)}</p>
          </article>
        )}
      </section>
    );
  return (
    <section className="public-page">
      <header className="public-hero">
        <p>Acompanhamento</p>
        <h1>Veja o andamento das entregas.</h1>
        <span>
          Consulte o que já está em execução e as atualizações publicadas.
        </span>
      </header>
      <form
        className="public-search"
        onSubmit={(e) => {
          e.preventDefault();
          filters.current = {
            q: q.trim() || undefined,
            project_id: projectId ? Number(projectId) : undefined,
            status: status || undefined,
          };
          load();
        }}
      >
        <label>
          Buscar trabalho
          <input
            value={q}
            maxLength={300}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Digite uma palavra-chave"
          />
        </label>
        <label>
          Projeto
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">Todos os projetos</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Situação
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Todas as situações</option>
            {Object.entries(executionLabels)
              .filter(([value]) => value !== "archived")
              .map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
          </select>
        </label>
        <button>Buscar</button>
      </form>
      {!page ? (
        <Loading />
      ) : !page.items.length ? (
        <p className="public-empty">Nenhuma entrega encontrada.</p>
      ) : (
        <>
          <section className="public-grid">
            {page.items.map((entry) => (
              <WorkCard key={entry.code} item={entry} />
            ))}
          </section>
          <Pagination offset={page.offset} total={page.total} load={load} />
        </>
      )}
    </section>
  );
}

type Draft = Omit<RequestPayload, "request_type" | "urgency"> & {
  request_type: RequestPayload["request_type"] | "";
  urgency: RequestPayload["urgency"] | "";
  contact: string;
};
const blank: Draft = {
  name: "",
  contact: "",
  area: null,
  project_id: null,
  project_kind: "outro",
  project_name: null,
  request_type: "",
  type_detail: null,
  description: "",
  location: null,
  purpose: "",
  example_url: null,
  urgency: "",
  attachments: [],
};
export function PublicRequestPage() {
  const [draft, setDraft] = useState<Draft>(blank);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const readingFiles = useRef(false);
  const submitting = useRef(false);
  const [sent, setSent] = useState<{ protocol: string; key: string } | null>(
    null,
  );
  const request = useRef({ body: "", idempotency: "", key: "" });
  const update = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  async function files(list: File[]) {
    if (submitting.current || readingFiles.current) return;
    readingFiles.current = true;
    setReading(true);
    const accepted: File[] = [],
      rejected: string[] = [];
    for (const file of list) {
      if (
        !/^(image\/(png|jpeg|webp|gif)|application\/pdf)$/.test(file.type) ||
        !file.size ||
        file.size > 5 * 1024 * 1024
      )
        rejected.push(`${file.name}: use imagem ou PDF não vazio de até 5 MB`);
      else if (accepted.length + draft.attachments.length >= 3)
        rejected.push(`${file.name}: o limite é de 3 arquivos`);
      else accepted.push(file);
    }
    try {
      const attachments = await Promise.all(accepted.map(fileToAttachment));
      setDraft((current) => ({
        ...current,
        attachments: [...current.attachments, ...attachments].slice(0, 3),
      }));
      setError(rejected.length ? `Não anexado: ${rejected.join("; ")}.` : "");
    } catch {
      setError("Não foi possível ler o arquivo. Escolha-o novamente.");
    } finally {
      readingFiles.current = false;
      setReading(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || readingFiles.current) return;
    if (
      draft.name.trim().length < 2 ||
      draft.contact.trim().length < 3 ||
      draft.description.trim().length < 5 ||
      draft.purpose.trim().length < 5 ||
      !draft.request_type ||
      !draft.urgency ||
      !draft.project_name?.trim() ||
      (draft.request_type === "outro" && !draft.type_detail?.trim())
    ) {
      setError("Preencha os campos obrigatórios para enviar a solicitação.");
      return;
    }
    const exampleUrl = normalizeExampleUrl(draft.example_url);
    if (draft.example_url?.trim() && !exampleUrl) {
      setError("Informe um link HTTP ou HTTPS válido, sem credenciais.");
      return;
    }
    const payload = {
      ...draft,
      name: draft.name.trim(),
      contact: draft.contact.trim(),
      description: draft.description.trim(),
      purpose: draft.purpose.trim(),
      example_url: exampleUrl,
      project_id: null,
      project_kind: "outro" as const,
      project_name: draft.project_name.trim(),
      request_type: draft.request_type as RequestPayload["request_type"],
      urgency: draft.urgency as RequestPayload["urgency"],
      attachments: attachmentPayload(draft.attachments),
    };
    const body = JSON.stringify(payload);
    if (request.current.body !== body)
      request.current = {
        body,
        idempotency: newKey(),
        key: secureRequestKey(),
      };
    submitting.current = true;
    const ticket = request.current;
    setBusy(true);
    setError("");
    try {
      const result = await publicApi.request(
        payload,
        ticket.idempotency,
        ticket.key,
      );
      setSent({ protocol: result.protocol, key: ticket.key });
    } catch (e) {
      setError(publicError(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  if (sent)
    return (
      <section className="public-page">
        <section className="public-success">
          <p>Solicitação enviada</p>
          <h1>Guarde seu comprovante.</h1>
          <dl>
            <dt>Protocolo</dt>
            <dd>{sent.protocol}</dd>
            <dt>Chave de consulta</dt>
            <dd className="public-key">{sent.key}</dd>
          </dl>
          {error && <p role="status">{error}</p>}
          <div className="public-actions">
            <button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(
                    `Protocolo: ${sent.protocol}\nChave: ${sent.key}`,
                  );
                  setError("Comprovante copiado.");
                } catch {
                  setError(
                    "Não foi possível copiar. Use Baixar comprovante para guardá-lo.",
                  );
                }
              }}
            >
              Copiar comprovante
            </button>
            <button
              className="secondary"
              onClick={() => {
                const blob = new Blob(
                  [`Protocolo: ${sent.protocol}\nChave: ${sent.key}`],
                  { type: "text/plain" },
                );
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `solicitacao-${sent.protocol}.txt`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Baixar comprovante
            </button>
            <a href={link("/minha-solicitacao")}>Acompanhar solicitação</a>
          </div>
        </section>
      </section>
    );
  return (
    <section className="public-page">
      <header className="public-hero">
        <p>Solicitação</p>
        <h1>Conte o que você precisa.</h1>
        <span>
          Você receberá um protocolo e uma chave para acompanhar apenas esta
          solicitação.
        </span>
      </header>
      <form className="public-form" onSubmit={(e) => void submit(e)}>
        {error && (
          <p className="public-alert" role="alert">
            {error}
          </p>
        )}
        <fieldset className="public-fields" disabled={busy}>
          <div className="public-two">
            <label>
              Seu nome *
              <input
                value={draft.name}
                minLength={2}
                maxLength={120}
                onChange={(e) => update("name", e.target.value)}
                required
              />
            </label>
            <label>
              Como falamos com você? *
              <input
                value={draft.contact}
                minLength={3}
                maxLength={320}
                onChange={(e) => update("contact", e.target.value)}
                placeholder="E-mail ou telefone"
                required
              />
            </label>
          </div>
          {draft.request_type === "outro" && (
            <label>
              Qual tipo de pedido? *
              <input
                value={draft.type_detail || ""}
                onChange={(e) => update("type_detail", e.target.value)}
                maxLength={200}
                required
              />
            </label>
          )}
          <div className="public-two">
            <label>
              Área
              <input
                value={draft.area || ""}
                onChange={(e) => update("area", e.target.value)}
                maxLength={120}
              />
            </label>
            <label>
              Onde acontece?
              <input
                value={draft.location || ""}
                onChange={(e) => update("location", e.target.value)}
                maxLength={500}
              />
            </label>
          </div>
          <label>
            Link de exemplo
            <input
              type="text"
              inputMode="url"
              autoComplete="url"
              placeholder="exemplo.com"
              value={draft.example_url || ""}
              onChange={(e) => update("example_url", e.target.value)}
              maxLength={1000}
            />
          </label>
          <label>
            Projeto *
            <input
              value={draft.project_name || ""}
              maxLength={160}
              onChange={(e) => update("project_name", e.target.value)}
              required
            />
          </label>
          <div className="public-two">
            <label>
              Tipo de pedido *
              <select
                value={draft.request_type}
                onChange={(e) =>
                  update(
                    "request_type",
                    e.target.value as Draft["request_type"],
                  )
                }
                required
              >
                <option value="">Selecione</option>
                {Object.entries(requestTypes).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Urgência *
              <select
                value={draft.urgency}
                onChange={(e) =>
                  update("urgency", e.target.value as Draft["urgency"])
                }
                required
              >
                <option value="">Selecione</option>
                {Object.entries(urgencyLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            O que precisa acontecer? *
            <textarea
              value={draft.description}
              minLength={5}
              maxLength={4000}
              onChange={(e) => update("description", e.target.value)}
              required
            />
          </label>
          <label>
            Para que isso serve? *
            <textarea
              value={draft.purpose}
              minLength={5}
              maxLength={2000}
              onChange={(e) => update("purpose", e.target.value)}
              required
            />
          </label>
          <label>
            Arquivos (imagem ou PDF, até 3)
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
              multiple
              disabled={busy || reading}
              onChange={(e) => void files(Array.from(e.target.files || []))}
            />
          </label>
          {draft.attachments.length > 0 && (
            <ul className="public-files">
              {draft.attachments.map((file, i) => (
                <li key={`${file.filename}-${i}`}>
                  {file.filename}
                  <button
                    type="button"
                    onClick={() =>
                      update(
                        "attachments",
                        draft.attachments.filter((_, index) => index !== i),
                      )
                    }
                  >
                    Remover
                  </button>
                </li>
              ))}
            </ul>
          )}
          {reading && <p role="status">Lendo arquivos…</p>}
          <button disabled={busy || reading}>
            {busy ? "Enviando…" : "Enviar solicitação"}
          </button>
        </fieldset>
      </form>
    </section>
  );
}

export function PublicTrackingPage() {
  const [protocol, setProtocol] = useState("");
  const [key, setKey] = useState("");
  const [item, setItem] = useState<Awaited<
    ReturnType<typeof publicApi.lookup>
  > | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<PublicRequestDraft | null>(null);
  const [credentials, setCredentials] = useState<{
    protocol: string;
    key: string;
  } | null>(null);
  async function lookup(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setNotice("");
    setItem(null);
    try {
      const checkedProtocol = protocol.trim();
      const checkedKey = key.trim();
      setItem(await publicApi.lookup(checkedProtocol, checkedKey));
      setCredentials({ protocol: checkedProtocol, key: checkedKey });
    } catch (error) {
      setItem(null);
      setNotice(publicError(error));
    } finally {
      setBusy(false);
    }
  }
  const openEditor = async () => {
    if (!item || !credentials || busy) return;
    setBusy(true);
    setNotice("");
    try {
      setEditing(await publicApi.draft(credentials.protocol, credentials.key));
    } catch (failure) {
      setNotice(publicError(failure));
    } finally {
      setBusy(false);
    }
  };
  const resubmit = async () => {
    const version = editing?.version ?? item?.version;
    if (!version || !credentials || busy) return;
    setBusy(true);
    setNotice("");
    try {
      const updated = await publicApi.resubmit(
        credentials.protocol,
        credentials.key,
        version,
      );
      setEditing(null);
      setItem((previous) =>
        previous ? { ...previous, ...updated } : previous,
      );
      setNotice("Solicitação reenviada para avaliação.");
    } catch (failure) {
      setNotice(publicError(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="public-page">
      <header className="public-hero">
        <p>Minha solicitação</p>
        <h1>Acompanhe seu pedido.</h1>
        <span>Digite o protocolo e a chave recebidos no comprovante.</span>
      </header>
      <form
        className="public-form public-track"
        onSubmit={(e) => void lookup(e)}
      >
        {notice && (
          <p className="public-alert" role="alert">
            {notice}
          </p>
        )}
        <label>
          Protocolo
          <input
            value={protocol}
            minLength={12}
            maxLength={64}
            autoComplete="off"
            onChange={(e) => setProtocol(e.target.value)}
            required
          />
        </label>
        <label>
          Chave de consulta
          <input
            type="password"
            value={key}
            minLength={64}
            pattern="[0-9a-fA-F]{64}"
            maxLength={64}
            autoComplete="off"
            onChange={(e) => setKey(e.target.value)}
            required
          />
        </label>
        <button disabled={busy}>{busy ? "Consultando…" : "Consultar"}</button>
      </form>
      {item && (
        <section className="public-result">
          <p>
            Avaliação: <b>{reviewLabels[item.status] ?? item.status}</b>
          </p>
          <p>
            Execução:{" "}
            <b>
              {item.execution_status
                ? (executionLabels[item.execution_status] ??
                  item.execution_status)
                : "Ainda não iniciada"}
            </b>
          </p>
          <h2>{item.name}</h2>
          <p>{item.description}</p>
          <p>Enviado em {date(item.created_at)}</p>
          {item.response && (
            <>
              <h3>Resposta da equipe</h3>
              <p>{item.response}</p>
            </>
          )}
          {!item.execution_status &&
            (item.status === "ajuste" || item.status === "recusado") && (
              <div className="public-actions">
                <button
                  type="button"
                  onClick={() => void openEditor()}
                  disabled={busy}
                >
                  Editar solicitação
                </button>
                {!editing && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void resubmit()}
                    disabled={busy}
                  >
                    Reenviar para avaliação
                  </button>
                )}
              </div>
            )}
        </section>
      )}
      {editing && (
        <PublicRequestEditor
          protocol={credentials!.protocol}
          requestKey={credentials!.key}
          item={editing}
          onCancel={() => setEditing(null)}
          onSaved={(updated) => {
            setEditing(null);
            setItem((previous) =>
              previous ? { ...previous, ...updated } : previous,
            );
            setNotice("Alterações salvas. Reenvie quando estiver pronto.");
          }}
        />
      )}
    </section>
  );
}

function PublicRequestEditor({
  protocol,
  requestKey,
  item,
  onCancel,
  onSaved,
}: {
  protocol: string;
  requestKey: string;
  item: PublicRequestDraft;
  onCancel: () => void;
  onSaved: (item: PublicRequestDraft) => void;
}) {
  const [draft, setDraft] = useState(item);
  const [removed, setRemoved] = useState<number[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [readingFiles, setReadingFiles] = useState(false);
  const [conflict, setConflict] = useState(false);
  const filesReading = useRef(false);
  const update = <K extends keyof PublicRequestDraft>(
    key: K,
    value: PublicRequestDraft[K],
  ) => setDraft((current) => ({ ...current, [key]: value }));
  const addFiles = async (files: File[]) => {
    if (busy || filesReading.current) return;
    filesReading.current = true;
    setReadingFiles(true);
    const retained = draft.attachments.filter(
      (file) => !file.id || !removed.includes(file.id),
    ).length;
    const valid = files.filter(
      (file) =>
        /^(image\/(png|jpeg|webp|gif)|application\/pdf)$/.test(file.type) &&
        file.size > 0 &&
        file.size <= 5 * 1024 * 1024,
    );
    if (valid.length !== files.length)
      setNotice("Use imagens ou PDF não vazios de até 5 MB.");
    if (retained + valid.length > 3) {
      setNotice("A solicitação pode ter no máximo 3 arquivos.");
      filesReading.current = false;
      setReadingFiles(false);
      return;
    }
    try {
      update("attachments", [
        ...draft.attachments,
        ...(await Promise.all(valid.map(fileToAttachment))),
      ]);
    } catch {
      setNotice("Não foi possível ler o arquivo. Escolha-o novamente.");
    } finally {
      filesReading.current = false;
      setReadingFiles(false);
    }
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || filesReading.current) return;
    if (
      draft.name.trim().length < 2 ||
      draft.contact.trim().length < 3 ||
      draft.description.trim().length < 5 ||
      draft.purpose.trim().length < 5 ||
      !draft.request_type ||
      !draft.urgency ||
      (draft.project_kind === "existing" && !draft.project_id) ||
      (draft.project_kind !== "existing" && !draft.project_name?.trim()) ||
      (draft.request_type === "outro" && !draft.type_detail?.trim())
    ) {
      setNotice("Preencha os campos obrigatórios antes de salvar.");
      return;
    }
    const exampleUrl = normalizeExampleUrl(draft.example_url);
    if (draft.example_url?.trim() && !exampleUrl) {
      setNotice("Informe um link HTTP ou HTTPS válido, sem credenciais.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const updated = await publicApi.update(protocol, requestKey, {
        version: draft.version,
        name: draft.name.trim(),
        contact: draft.contact.trim(),
        area: draft.area?.trim() || null,
        project_name:
          draft.project_kind === "existing"
            ? null
            : draft.project_name?.trim() || null,
        type_detail:
          draft.request_type === "outro"
            ? draft.type_detail?.trim() || null
            : null,
        description: draft.description.trim(),
        location: draft.location?.trim() || null,
        purpose: draft.purpose.trim(),
        example_url: exampleUrl,
        project_id: draft.project_id,
        project_kind: draft.project_kind,
        request_type: draft.request_type,
        urgency: draft.urgency,
        attachments: attachmentPayload(
          draft.attachments.filter((file) => !file.id),
        ),
        remove_attachment_ids: removed,
      });
      setDraft(updated);
      setRemoved([]);
      setConflict(false);
      onSaved(updated);
    } catch (failure) {
      if (axios.isAxiosError(failure) && failure.response?.status === 409) {
        setConflict(true);
        setNotice(
          "A solicitação mudou enquanto você editava. Recarregue a versão antes de salvar; seu texto foi mantido.",
        );
      } else {
        setNotice(`${publicError(failure)} O que você escreveu continua aqui.`);
      }
    } finally {
      setBusy(false);
    }
  };
  const reloadVersion = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const latest = await publicApi.draft(protocol, requestKey);
      setDraft((current) => ({
        ...latest,
        ...current,
        version: latest.version,
        attachments: latest.attachments,
      }));
      setRemoved([]);
      setConflict(false);
      setNotice("Versão atualizada. Revise os anexos e salve novamente.");
    } catch (failure) {
      setNotice(publicError(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="public-form public-edit"
      onSubmit={(event) => void save(event)}
    >
      <h2>Revise seu pedido</h2>
      <p className="field-help">
        Salve as alterações antes de reenviar para a equipe.
      </p>
      {notice && (
        <p className="public-alert" role="alert">
          {notice}
        </p>
      )}
      <fieldset className="public-fields" disabled={busy || readingFiles}>
        <div className="public-two">
          <label>
            Seu nome *
            <input
              required
              minLength={2}
              maxLength={120}
              value={draft.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </label>
          <label>
            Como falamos com você? *
            <input
              required
              minLength={3}
              maxLength={320}
              value={draft.contact}
              onChange={(e) => update("contact", e.target.value)}
            />
          </label>
        </div>
        <label>
          Projeto{draft.project_kind !== "existing" ? " *" : ""}
          <input
            value={draft.project_name || ""}
            maxLength={160}
            required={draft.project_kind !== "existing"}
            readOnly={draft.project_kind === "existing"}
            placeholder={
              draft.project_kind === "existing" ? "Projeto selecionado" : undefined
            }
            onChange={(e) => update("project_name", e.target.value)}
          />
        </label>
        <div className="public-two">
          <label>
            Tipo de pedido *
            <select
              required
              value={draft.request_type}
              onChange={(e) =>
                update(
                  "request_type",
                  e.target.value as PublicRequestDraft["request_type"],
                )
              }
            >
              {Object.entries(requestTypes).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Urgência *
            <select
              required
              value={draft.urgency}
              onChange={(e) =>
                update(
                  "urgency",
                  e.target.value as PublicRequestDraft["urgency"],
                )
              }
            >
              {Object.entries(urgencyLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {draft.request_type === "outro" && (
          <label>
            Qual tipo de pedido? *
            <input
              required
              maxLength={200}
              value={draft.type_detail || ""}
              onChange={(e) => update("type_detail", e.target.value)}
            />
          </label>
        )}
        <label>
          O que precisa acontecer? *
          <textarea
            required
            minLength={5}
            maxLength={4000}
            value={draft.description}
            onChange={(e) => update("description", e.target.value)}
          />
        </label>
        <label>
          Para que isso serve? *
          <textarea
            required
            minLength={5}
            maxLength={2000}
            value={draft.purpose}
            onChange={(e) => update("purpose", e.target.value)}
          />
        </label>
        <label>
          Onde acontece?
          <input
            maxLength={500}
            value={draft.location || ""}
            onChange={(e) => update("location", e.target.value)}
          />
        </label>
        <label>
          Link de exemplo
          <input
            type="text"
            inputMode="url"
            autoComplete="url"
            placeholder="exemplo.com"
            maxLength={1000}
            value={draft.example_url || ""}
            onChange={(e) => update("example_url", e.target.value)}
          />
        </label>
        {!!draft.attachments.length && (
          <ul className="public-files">
            {draft.attachments.map((file) => {
              const removedFile = !!file.id && removed.includes(file.id);
              return (
                <li
                  key={file.id || file.filename}
                  className={removedFile ? "public-file--removed" : ""}
                >
                  <span>{file.filename}</span>
                  <button
                    type="button"
                    onClick={() =>
                      file.id
                        ? setRemoved((ids) =>
                            removedFile
                              ? ids.filter((id) => id !== file.id)
                              : [...ids, file.id!],
                          )
                        : update(
                            "attachments",
                            draft.attachments.filter((entry) => entry !== file),
                          )
                    }
                  >
                    {removedFile ? "Manter" : "Remover"}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <label>
          Adicionar arquivos (imagem ou PDF, até 3 no total)
          <input
            type="file"
            multiple
            disabled={readingFiles}
            accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
            onChange={(e) => {
              void addFiles(Array.from(e.currentTarget.files || []));
              e.currentTarget.value = "";
            }}
          />
        </label>
        {readingFiles && <p role="status">Lendo arquivos…</p>}
        {conflict && (
          <button
            type="button"
            className="secondary"
            onClick={() => void reloadVersion()}
          >
            Recarregar versão e manter rascunho
          </button>
        )}
        <div className="public-actions">
          <button type="submit">
            {busy ? "Salvando…" : "Salvar alterações"}
          </button>
          <button type="button" className="secondary" onClick={onCancel}>
            Cancelar
          </button>
        </div>
      </fieldset>
    </form>
  );
}
