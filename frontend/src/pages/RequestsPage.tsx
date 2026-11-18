import { appHref } from "../lib/navigation";
import { normalizeExampleUrl } from "../lib/example-url";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { User } from "../types";
import { error } from "../api";
import {
  fileToAttachment,
  requestApi,
  requestTypes,
  urgencyLabels,
  type Attachment,
  type RequestItem,
  type RequestPayload,
  type RequestStatus,
} from "../lib/requests";
import "./RequestsPage.css";

const statuses: [RequestStatus, string][] = [
  ["em_avaliacao", "Em avaliação"],
  ["ajuste", "Precisa de ajuste"],
  ["aprovado", "Aprovados"],
  ["recusado", "Recusados"],
];
const actions: [RequestStatus, string][] = [
  ["aprovado", "Aprovar"],
  ["ajuste", "Pedir ajuste"],
  ["recusado", "Recusar"],
  ["em_avaliacao", "Voltar para avaliação"],
];
type Draft = Omit<RequestPayload, "urgency" | "request_type"> & {
  urgency: RequestPayload["urgency"] | "";
  request_type: RequestPayload["request_type"] | "";
};
const blank = (name: string): Draft => ({
  name,
  area: null,
  project_id: null,
  project_kind: "existing",
  project_name: null,
  request_type: "",
  type_detail: null,
  description: "",
  location: null,
  purpose: "",
  example_url: null,
  urgency: "",
  attachments: [],
});
const draftFromRequest = (item: RequestItem): Draft => ({
  name: item.name,
  area: item.area,
  project_id: item.project_id,
  project_kind: item.project_kind as Draft["project_kind"],
  project_name: item.project_name,
  request_type: item.request_type as Draft["request_type"],
  type_detail: item.type_detail,
  description: item.description,
  location: item.location,
  purpose: item.purpose,
  example_url: item.example_url,
  urgency: item.urgency,
  // Anexos existentes continuam no servidor. Este campo recebe só novos arquivos.
  attachments: [],
});
const date = (value: string) =>
  new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
    new Date(value),
  );
const size = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
const safeUrl = normalizeExampleUrl;

export function RequestFormPage({ user }: { user: User }) {
  const [draft, setDraft] = useState<Draft>(() => blank(user.name));
  const [area, setArea] = useState("");
  const [projects, setProjects] = useState<
    Awaited<ReturnType<typeof requestApi.projects>>
  >([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(true);
  const request = useRef({ payload: "", key: "" });
  const readingFiles = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const update = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  useEffect(() => {
    let active = true;
    void requestApi
      .projects()
      .then((items) => {
        if (!active) return;
        setProjects(items);
        const id = Number(new URLSearchParams(location.search).get("projeto"));
        if (items.some((project) => project.id === id))
          setDraft((current) => ({ ...current, project_id: id }));
      })
      .catch((failure) => active && setNotice(error(failure)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);
  const addFiles = async (files: File[]) => {
    if (busy || readingFiles.current) return;
    readingFiles.current = true;
    setReading(true);
    const accepted: File[] = [],
      rejected: string[] = [];
    for (const file of files) {
      if (!/^(image\/(png|jpeg|webp|gif)|application\/pdf)$/.test(file.type))
        rejected.push(`${file.name}: use imagem ou PDF`);
      else if (!file.size || file.size > 5 * 1024 * 1024)
        rejected.push(`${file.name}: use um arquivo de até 5 MB`);
      else if (draft.attachments.length + accepted.length >= 3)
        rejected.push(`${file.name}: o limite é de 3 arquivos`);
      else accepted.push(file);
    }
    try {
      const attachments = await Promise.all(accepted.map(fileToAttachment));
      setDraft((current) => ({
        ...current,
        attachments: [...current.attachments, ...attachments].slice(0, 3),
      }));
      setNotice(rejected.length ? `Não anexado: ${rejected.join("; ")}.` : "");
    } catch {
      setNotice("Não foi possível ler o arquivo. Escolha-o novamente.");
    } finally {
      readingFiles.current = false;
      setReading(false);
    }
  };
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || readingFiles.current) return;
    const required: [string, string, boolean][] = [
      ["name", "seu nome", draft.name.trim().length >= 2],
      [
        "area_other",
        "qual área",
        area !== "outro" || Boolean(draft.area?.trim()),
      ],
      [
        "project",
        "o projeto",
        draft.project_kind !== "existing" || Boolean(draft.project_id),
      ],
      [
        "project_name",
        "o nome do projeto",
        draft.project_kind === "existing" ||
          Boolean(draft.project_name?.trim()),
      ],
      ["request_type", "o tipo de pedido", Boolean(draft.request_type)],
      [
        "type_detail",
        "qual tipo de pedido",
        draft.request_type !== "outro" || Boolean(draft.type_detail?.trim()),
      ],
      [
        "description",
        "o que precisa (ao menos 5 caracteres)",
        draft.description.trim().length >= 5,
      ],
      [
        "purpose",
        "para que serve (ao menos 5 caracteres)",
        draft.purpose.trim().length >= 5,
      ],
      ["urgency", "a urgência", Boolean(draft.urgency)],
    ];
    const missing = required.filter(([, , valid]) => !valid);
    if (missing.length) {
      setNotice(
        `Falta preencher: ${missing.map(([, label]) => label).join(", ")}.`,
      );
      form.current
        ?.querySelector<HTMLElement>(`[name="${missing[0][0]}"]`)
        ?.focus();
      return;
    }
    if (draft.example_url?.trim() && !safeUrl(draft.example_url.trim())) {
      setNotice(
        "O link de exemplo precisa ser um endereço HTTP ou HTTPS válido.",
      );
      form.current?.querySelector<HTMLElement>('[name="example_url"]')?.focus();
      return;
    }
    const data: RequestPayload = {
      ...draft,
      name: draft.name.trim(),
      description: draft.description.trim(),
      purpose: draft.purpose.trim(),
      location:
        draft.project_kind === "novo_projeto"
          ? null
          : draft.location?.trim() || null,
      area: draft.area?.trim() || null,
      project_name:
        draft.project_kind === "existing" ? null : draft.project_name?.trim(),
      type_detail:
        draft.request_type === "outro" ? draft.type_detail?.trim() : null,
      example_url: safeUrl(draft.example_url) || null,
      request_type: draft.request_type as RequestPayload["request_type"],
      urgency: draft.urgency as RequestPayload["urgency"],
      attachments: draft.attachments.map(
        ({ filename, mime_type, content_base64 }) => ({
          filename,
          mime_type,
          content_base64,
        }),
      ),
    };
    const payload = JSON.stringify(data);
    if (request.current.payload !== payload)
      request.current = { payload, key: crypto.randomUUID() };
    setBusy(true);
    setNotice("");
    try {
      await requestApi.create(data, request.current.key);
      request.current = { payload: "", key: "" };
      setSent(true);
      setDraft(blank(user.name));
    } catch (failure) {
      setNotice(
        `Não foi possível enviar agora. ${error(failure)} O que você escreveu continua aqui.`,
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="requests-page">
      <header className="requests-hero">
        <p>Para a equipe interna</p>
        <h1>Solicitar uma alteração.</h1>
        <p>
          Conte o que precisa mudar em um projeto. O pedido entra em avaliação
          e, se fizer sentido, vira tarefa na lista do projeto.
        </p>
      </header>
      {sent ? (
        <section className="request-sent" role="status">
          <h2>Pedido enviado.</h2>
          <p>
            Ele está em avaliação. Se precisar de algum detalhe, a direção entra
            em contato com você.
          </p>
          <div className="request-actions">
            <button
              onClick={() => {
                setSent(false);
                setArea("");
                setNotice("");
              }}
            >
              Enviar outro pedido
            </button>
            <a href={appHref("#/requests")}>Ver solicitações</a>
          </div>
        </section>
      ) : (
        <form
          className="request-form"
          noValidate
          onSubmit={submit}
          ref={form}
          onPaste={(event) => {
            if (event.clipboardData.files.length) {
              event.preventDefault();
              void addFiles([...event.clipboardData.files]);
            }
          }}
        >
          <fieldset disabled={busy || reading}>
            <div className="request-grid">
              <label>
                <span>
                  Seu nome{" "}
                  <b className="required-marker" aria-hidden="true">
                    *
                  </b>
                </span>
                <input
                  name="name"
                  required
                  minLength={2}
                  maxLength={120}
                  autoComplete="name"
                  value={draft.name}
                  onChange={(event) => update("name", event.target.value)}
                />
              </label>
              <label>
                Área
                <select
                  value={area}
                  onChange={(event) => {
                    setArea(event.target.value);
                    update(
                      "area",
                      event.target.value === "outro"
                        ? ""
                        : event.target.value || null,
                    );
                  }}
                >
                  <option value="">Escolha a área</option>
                  {["Núcleo", "Marketing", "Financeiro", "Jurídico"].map(
                    (value) => (
                      <option key={value}>{value}</option>
                    ),
                  )}
                  <option value="outro">Outro</option>
                </select>
              </label>
              {area === "outro" && (
                <label>
                  <span>
                    Qual área?{" "}
                    <b className="required-marker" aria-hidden="true">
                      *
                    </b>
                  </span>
                  <input
                    name="area_other"
                    required
                    maxLength={120}
                    value={draft.area || ""}
                    onChange={(event) => update("area", event.target.value)}
                  />
                </label>
              )}
              <label>
                <span>
                  Projeto{" "}
                  <b className="required-marker" aria-hidden="true">
                    *
                  </b>
                </span>
                <select
                  name="project"
                  required
                  disabled={loading}
                  value={
                    draft.project_kind === "existing"
                      ? (draft.project_id ?? "")
                      : draft.project_kind
                  }
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((current) => ({
                      ...current,
                      project_id: /^\d+$/.test(value) ? Number(value) : null,
                      project_kind:
                        value === "novo_projeto" || value === "outro"
                          ? value
                          : "existing",
                      project_name: null,
                      request_type:
                        value === "novo_projeto" && !current.request_type
                          ? "novo_projeto"
                          : current.request_type,
                    }));
                  }}
                >
                  <option value="">
                    {loading ? "Carregando projetos…" : "Escolha o projeto"}
                  </option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                  <option value="novo_projeto">Novo projeto</option>
                  <option value="outro">Outro</option>
                </select>
              </label>
              {draft.project_kind !== "existing" && (
                <label>
                  <span>
                    {draft.project_kind === "novo_projeto"
                      ? "Nome ou ideia do novo projeto"
                      : "Qual projeto?"}{" "}
                    <b className="required-marker" aria-hidden="true">
                      *
                    </b>
                  </span>
                  <input
                    name="project_name"
                    required
                    maxLength={160}
                    value={draft.project_name || ""}
                    onChange={(event) =>
                      update("project_name", event.target.value)
                    }
                  />
                </label>
              )}
              <label>
                <span>
                  Tipo de pedido{" "}
                  <b className="required-marker" aria-hidden="true">
                    *
                  </b>
                </span>
                <select
                  name="request_type"
                  required
                  value={draft.request_type}
                  onChange={(event) =>
                    update(
                      "request_type",
                      event.target.value as Draft["request_type"],
                    )
                  }
                >
                  <option value="">Escolha o tipo</option>
                  {Object.entries(requestTypes).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {draft.request_type === "outro" && (
                <label>
                  <span>
                    Qual tipo de pedido?{" "}
                    <b className="required-marker" aria-hidden="true">
                      *
                    </b>
                  </span>
                  <input
                    name="type_detail"
                    required
                    maxLength={200}
                    value={draft.type_detail || ""}
                    onChange={(event) =>
                      update("type_detail", event.target.value)
                    }
                  />
                </label>
              )}
            </div>
            <label>
              <span>
                O que precisa{" "}
                <b className="required-marker" aria-hidden="true">
                  *
                </b>
              </span>
              <textarea
                name="description"
                required
                minLength={5}
                maxLength={4000}
                rows={4}
                placeholder="Ex.: incluir o campo X no relatório ABC"
                value={draft.description}
                onChange={(event) => update("description", event.target.value)}
              />
            </label>
            {draft.project_kind !== "novo_projeto" && (
              <label>
                Em qual tela ou relatório
                <input
                  name="location"
                  maxLength={500}
                  placeholder="Ex.: aba Tarefas, relatório de vendas do mês"
                  value={draft.location || ""}
                  onChange={(event) => update("location", event.target.value)}
                />
                <span className="field-help">
                  Opcional. Em que parte do projeto a mudança deve aparecer.
                </span>
              </label>
            )}
            <label>
              <span>
                Para que serve{" "}
                <b className="required-marker" aria-hidden="true">
                  *
                </b>
              </span>
              <textarea
                name="purpose"
                required
                minLength={5}
                maxLength={2000}
                rows={4}
                placeholder="Que problema isso resolve no seu dia a dia?"
                value={draft.purpose}
                onChange={(event) => update("purpose", event.target.value)}
              />
              <span className="field-help">
                É o que mais ajuda a avaliar o pedido.
              </span>
            </label>
            <div className="request-attachments">
              <label>
                Print ou arquivo
                <input
                  type="file"
                  multiple
                  accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
                  onChange={(event) => {
                    void addFiles([...(event.currentTarget.files || [])]);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              {!!draft.attachments.length && (
                <ul className="request-files">
                  {draft.attachments.map((file, index) => (
                    <li key={index}>
                      {file.mime_type.startsWith("image/") ? (
                        <img
                          alt=""
                          src={`data:${file.mime_type};base64,${file.content_base64}`}
                        />
                      ) : (
                        <span className="request-file-pdf">PDF</span>
                      )}
                      <span>
                        {file.filename} · {size(file.size || 0)}
                      </span>
                      <button
                        type="button"
                        className="request-text-button"
                        aria-label={`Remover ${file.filename}`}
                        onClick={() =>
                          update(
                            "attachments",
                            draft.attachments.filter((_, i) => i !== index),
                          )
                        }
                      >
                        Remover
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <span className="field-help">
                Opcional. Até 3 arquivos (imagem ou PDF, até 5 MB cada). Também
                dá para colar um print com Ctrl+V em qualquer campo.
              </span>
              {reading && <span role="status">Lendo arquivos…</span>}
            </div>
            <label>
              Link de exemplo
              <input
                name="example_url"
                type="text"
                inputMode="url"
                autoComplete="url"
                maxLength={1000}
                placeholder="Link de uma planilha, tela ou documento"
                value={draft.example_url || ""}
                onChange={(event) => update("example_url", event.target.value)}
              />
              <span className="field-help">Opcional.</span>
            </label>
            <label>
              <span>
                Urgência{" "}
                <b className="required-marker" aria-hidden="true">
                  *
                </b>
              </span>
              <select
                name="urgency"
                required
                value={draft.urgency}
                onChange={(event) =>
                  update("urgency", event.target.value as Draft["urgency"])
                }
              >
                <option value="">Escolha a urgência</option>
                {Object.entries(urgencyLabels).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {notice && (
              <p className="request-error" role="alert">
                {notice}
              </p>
            )}
            <div className="request-actions">
              <button type="submit" disabled={busy || reading || loading}>
                {busy ? "Enviando…" : "Enviar pedido"}
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {!sent && (
        <p className="request-own-link">
          <a href={appHref("#/requests")}>Ver solicitações →</a>
        </p>
      )}
    </section>
  );
}

export function RequestReviewPage({
  user: _user,
  embedded = false,
}: {
  user: User;
  embedded?: boolean;
}) {
  const [status, setStatus] = useState<RequestStatus>("em_avaliacao");
  const [offset, setOffset] = useState(0),
    [total, setTotal] = useState(0);
  const [items, setItems] = useState<RequestItem[]>([]);
  const [counts, setCounts] = useState<Record<RequestStatus, number>>({
    em_avaliacao: 0,
    ajuste: 0,
    aprovado: 0,
    recusado: 0,
  });
  const [notice, setNotice] = useState(""),
    [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    setNotice("");
    try {
      const page = await requestApi.list(status, offset);
      if (current === generation.current) {
        setItems(page.items);
        setCounts(page.counts);
        setTotal(page.total);
      }
    } catch (failure) {
      if (current === generation.current) setNotice(error(failure));
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [status, offset]);
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  const download = async (item: RequestItem, file: Attachment) => {
    if (!file.id) return;
    try {
      const url = URL.createObjectURL(
        await requestApi.attachment(item.id, file.id),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = file.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      setNotice(error(failure));
    }
  };
  return (
    <section
      className={`requests-page requests-review${embedded ? " requests-review--embedded" : ""}`}
    >
      <header className="request-review-heading">
        <p>Para avaliar</p>
        <div>
          <h1>Solicitações da equipe</h1>
          <span>
            {Object.values(counts).reduce((sum, value) => sum + value, 0)}{" "}
            pedidos recebidos ·{" "}
            <a href={appHref("#/request")}>Solicitar uma alteração</a>
          </span>
        </div>
      </header>
      <div
        className="request-chips"
        role="group"
        aria-label="Situação dos pedidos"
      >
        {statuses.map(([value, label]) => (
          <button
            key={value}
            aria-pressed={status === value}
            onClick={() => {
              setStatus(value);
              setOffset(0);
            }}
          >
            {label} · {counts[value]}
          </button>
        ))}
      </div>
      {notice && (
        <div className="request-error" role="alert">
          {notice}{" "}
          <button className="request-text-button" onClick={() => void loadRef.current()}>
            Tentar novamente
          </button>
        </div>
      )}
      {loading ? (
        <p role="status">Carregando solicitações…</p>
      ) : items.length ? (
        <div className="request-list">
          {items.map((item) => (
            <RequestCard
              key={item.id}
              item={item}
              user={_user}
              reload={() => void loadRef.current()}
              download={download}
            />
          ))}
        </div>
      ) : (
        !notice && (
          <p className="request-empty">
            {status === "em_avaliacao"
              ? "Nenhum pedido esperando avaliação."
              : "Nenhum pedido nesta situação."}
          </p>
        )
      )}
      {total > 50 && (
        <nav
          className="request-pagination"
          aria-label="Paginação de solicitações"
        >
          <button
            disabled={offset === 0 || loading}
            onClick={() => setOffset((value) => Math.max(0, value - 50))}
          >
            Anterior
          </button>
          <span>
            {offset + 1}–{Math.min(offset + 50, total)} de {total}
          </span>
          <button
            disabled={offset + 50 >= total || loading}
            onClick={() => setOffset((value) => value + 50)}
          >
            Próxima
          </button>
        </nav>
      )}
    </section>
  );
}

function RequestCard({
  item,
  user,
  reload,
  download,
}: {
  item: RequestItem;
  user: User;
  reload: () => void;
  download: (item: RequestItem, file: Attachment) => Promise<void>;
}) {
  const [current, setCurrent] = useState(item),
    [response, setResponse] = useState(item.response || "");
  const [projectId, setProjectId] = useState<number | null>(item.project_id),
    [assigneeId, setAssigneeId] = useState(""),
    [dueDate, setDueDate] = useState("");
  const [projects, setProjects] = useState<
      Awaited<ReturnType<typeof requestApi.projects>>
    >([]),
    [assignees, setAssignees] = useState<
      Awaited<ReturnType<typeof requestApi.assignees>>
    >([]);
  const [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loadingPeople, setLoadingPeople] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState<Draft>(() =>
    draftFromRequest(item),
  );
  const [removedAttachments, setRemovedAttachments] = useState<number[]>([]);
  const [readingEditFiles, setReadingEditFiles] = useState(false);
  const [editConflict, setEditConflict] = useState(false);
  const editFilesReading = useRef(false);
  const projectInput = useRef<HTMLSelectElement>(null),
    assigneeInput = useRef<HTMLSelectElement>(null),
    dateInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setCurrent(item);
    if (!editing) setEditDraft(draftFromRequest(item));
  }, [item]);
  useEffect(() => {
    let active = true;
    if (current.can_review && current.project_kind !== "existing")
      void requestApi
        .projects()
        .then(
          (values) =>
            active &&
            setProjects(
              values.filter(
                (project) =>
                  project.role === "admin" || project.role === "manager",
              ),
            ),
        )
        .catch((failure) => active && setNotice(error(failure)));
    return () => {
      active = false;
    };
  }, [current.can_review, current.project_kind]);
  useEffect(() => {
    let active = true;
    setAssignees([]);
    if (current.can_review && projectId) {
      setLoadingPeople(true);
      void requestApi
        .assignees(projectId)
        .then((values) => active && setAssignees(values))
        .catch((failure) => active && setNotice(error(failure)))
        .finally(() => active && setLoadingPeople(false));
    }
    return () => {
      active = false;
    };
  }, [projectId, current.can_review]);
  const review = async (status: RequestStatus) => {
    if (busy) return;
    if (
      status === "aprovado" &&
      !current.has_task &&
      (!projectId || !assigneeId || !dueDate)
    ) {
      setNotice(
        "Antes de aprovar, defina o projeto, o responsável e o prazo da tarefa.",
      );
      if (!projectId) projectInput.current?.focus();
      else if (!assigneeId) assigneeInput.current?.focus();
      else dateInput.current?.focus();
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      await requestApi.review(current.id, {
        version: current.version,
        status,
        response: response.trim() || null,
        ...(status === "aprovado" && !current.has_task
          ? {
              project_id: projectId!,
              assignee_id: Number(assigneeId),
              due_date: dueDate,
            }
          : {}),
      });
      reload();
    } catch (failure) {
      if (
        typeof failure === "object" &&
        failure &&
        "response" in failure &&
        (failure as { response?: { status?: number } }).response?.status === 409
      ) {
        try {
          setCurrent(await requestApi.get(current.id));
          setNotice(
            "A solicitação foi atualizada. Confira os dados antes de reenviar; seu rascunho foi mantido.",
          );
        } catch {
          setNotice(error(failure));
        }
      } else setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  };
  const canRevise =
    current.requester_id === user.id &&
    !current.has_task &&
    (current.status === "ajuste" || current.status === "recusado");
  const changeEdit = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setEditDraft((draft) => ({ ...draft, [key]: value }));
  const addEditFiles = async (files: File[]) => {
    if (busy || editFilesReading.current) return;
    editFilesReading.current = true;
    setReadingEditFiles(true);
    const kept = current.attachments.filter(
      (file) => !file.id || !removedAttachments.includes(file.id),
    ).length;
    const valid = files.filter(
      (file) =>
        /^(image\/(png|jpeg|webp|gif)|application\/pdf)$/.test(file.type) &&
        file.size > 0 &&
        file.size <= 5 * 1024 * 1024,
    );
    if (valid.length !== files.length)
      setNotice("Use imagens ou PDF não vazios de até 5 MB.");
    if (kept + editDraft.attachments.length + valid.length > 3) {
      setNotice("O pedido pode ter no máximo 3 arquivos.");
      editFilesReading.current = false;
      setReadingEditFiles(false);
      return;
    }
    try {
      const attachments = await Promise.all(valid.map(fileToAttachment));
      changeEdit("attachments", [...editDraft.attachments, ...attachments]);
    } catch {
      setNotice("Não foi possível ler o arquivo. Escolha-o novamente.");
    } finally {
      editFilesReading.current = false;
      setReadingEditFiles(false);
    }
  };
  const saveEdit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || editFilesReading.current) return;
    if (
      editDraft.name.trim().length < 2 ||
      editDraft.description.trim().length < 5 ||
      editDraft.purpose.trim().length < 5 ||
      !editDraft.request_type ||
      !editDraft.urgency ||
      (editDraft.project_kind === "existing" && !editDraft.project_id) ||
      (editDraft.project_kind !== "existing" &&
        !editDraft.project_name?.trim()) ||
      (editDraft.request_type === "outro" && !editDraft.type_detail?.trim())
    ) {
      setNotice("Preencha os campos obrigatórios antes de salvar a revisão.");
      return;
    }
    if (
      editDraft.example_url?.trim() &&
      !safeUrl(editDraft.example_url.trim())
    ) {
      setNotice("O link de exemplo precisa ser HTTP ou HTTPS válido.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const updated = await requestApi.update(current.id, {
        ...editDraft,
        version: current.version,
        name: editDraft.name.trim(),
        area: editDraft.area?.trim() || null,
        project_name:
          editDraft.project_kind === "existing"
            ? null
            : editDraft.project_name?.trim() || null,
        type_detail:
          editDraft.request_type === "outro"
            ? editDraft.type_detail?.trim() || null
            : null,
        description: editDraft.description.trim(),
        location: editDraft.location?.trim() || null,
        purpose: editDraft.purpose.trim(),
        example_url: safeUrl(editDraft.example_url) || null,
        request_type: editDraft.request_type as RequestPayload["request_type"],
        urgency: editDraft.urgency as RequestPayload["urgency"],
        attachments: editDraft.attachments.map(
          ({ filename, mime_type, content_base64 }) => ({
            filename,
            mime_type,
            content_base64,
          }),
        ),
        remove_attachment_ids: removedAttachments,
      });
      setCurrent(updated);
      setEditDraft(draftFromRequest(updated));
      setRemovedAttachments([]);
      setEditConflict(false);
      setEditing(false);
      setNotice("Alterações salvas. Reenvie o pedido para nova avaliação.");
    } catch (failure) {
      if (
        typeof failure === "object" &&
        failure &&
        "response" in failure &&
        (failure as { response?: { status?: number } }).response?.status === 409
      ) {
        setEditConflict(true);
        setNotice(
          "A solicitação mudou enquanto você editava. Recarregue a versão antes de salvar; seu texto foi mantido.",
        );
      } else {
        setNotice(`${error(failure)} O que você escreveu continua aqui.`);
      }
    } finally {
      setBusy(false);
    }
  };
  const reloadEditVersion = async () => {
    if (busy) return;
    setBusy(true);
    try {
      setCurrent(await requestApi.get(current.id));
      setEditConflict(false);
      setNotice("Versão atualizada. Revise os anexos e salve novamente.");
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  };
  const resubmit = async () => {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      setCurrent(await requestApi.resubmit(current.id, current.version));
      setNotice("Pedido reenviado para avaliação.");
      reload();
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  };
  const example = safeUrl(current.example_url);
  return (
    <article
      className={`request-card request-card--${current.urgency}`}
      data-request-id={current.id}
    >
      <div className="request-card__top">
        <span>
          {requestTypes[current.request_type as keyof typeof requestTypes] ||
            current.request_type}
          {current.type_detail ? `: ${current.type_detail}` : ""} ·{" "}
          {current.project_name || "Projeto a definir"}
        </span>
        <strong>{urgencyLabels[current.urgency]}</strong>
      </div>
      <h2>{current.description}</h2>
      <p className="request-meta">
        {current.name}
        {current.area ? ` · ${current.area}` : ""} · {date(current.created_at)}
      </p>
      <dl className="request-data">
        {current.origin === "public" && (
          <div>
            <dt>Enviado pelo portal público</dt>
            <dd>{current.contact || "Contato não informado"}</dd>
          </div>
        )}
        <div>
          <dt>Para que serve</dt>
          <dd>{current.purpose}</dd>
        </div>
        {current.location && (
          <div>
            <dt>Tela ou relatório</dt>
            <dd>{current.location}</dd>
          </div>
        )}
        {example && (
          <div>
            <dt>Link de exemplo</dt>
            <dd>
              <a href={example} target="_blank" rel="noopener noreferrer">
                {example.replace(/^https?:\/\//, "")} ↗
              </a>
            </dd>
          </div>
        )}
        {!!current.attachments.length && (
          <div>
            <dt>Anexos</dt>
            <dd>
              {current.attachments.map((file) => (
                <button
                  className="request-text-button"
                  key={file.id}
                  onClick={() => void download(current, file)}
                >
                  Baixar {file.filename}
                </button>
              ))}
            </dd>
          </div>
        )}
        {current.reviewed_at && (
          <div>
            <dt>Avaliado em</dt>
            <dd>{date(current.reviewed_at)}</dd>
          </div>
        )}
      </dl>
      {canRevise && !editing && (
        <div className="request-actions request-requester-actions">
          <button type="button" onClick={() => setEditing(true)}>
            Editar solicitação
          </button>
          <button
            type="button"
            className="request-button-secondary"
            disabled={busy}
            onClick={() => void resubmit()}
          >
            {busy ? "Reenviando…" : "Reenviar para avaliação"}
          </button>
        </div>
      )}
      {canRevise && editing && (
        <form
          className="request-edit-form"
          onSubmit={(event) => void saveEdit(event)}
        >
          <h3>Revise seu pedido</h3>
          <p className="field-help">
            A resposta da equipe permanece visível. Salve as alterações e
            reenvie quando estiver pronto.
          </p>
          <fieldset disabled={busy || readingEditFiles}>
            <div className="request-grid">
              <label>
                Seu nome
                <input
                  required
                  minLength={2}
                  maxLength={120}
                  value={editDraft.name}
                  onChange={(event) => changeEdit("name", event.target.value)}
                />
              </label>
              <label>
                Projeto
                <input
                  value={editDraft.project_name || current.project_name || ""}
                  readOnly
                  aria-describedby="request-project-edit-help"
                />
                <span id="request-project-edit-help" className="field-help">
                  O projeto é mantido nesta revisão.
                </span>
              </label>
            </div>
            <label>
              O que precisa
              <textarea
                required
                minLength={5}
                maxLength={4000}
                value={editDraft.description}
                onChange={(event) =>
                  changeEdit("description", event.target.value)
                }
              />
            </label>
            <label>
              Para que serve
              <textarea
                required
                minLength={5}
                maxLength={2000}
                value={editDraft.purpose}
                onChange={(event) => changeEdit("purpose", event.target.value)}
              />
            </label>
            <label>
              Em qual tela ou relatório
              <input
                maxLength={500}
                value={editDraft.location || ""}
                onChange={(event) => changeEdit("location", event.target.value)}
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
                value={editDraft.example_url || ""}
                onChange={(event) =>
                  changeEdit("example_url", event.target.value)
                }
              />
            </label>
            <div className="request-grid">
              <label>
                Tipo de pedido
                <select
                  required
                  value={editDraft.request_type}
                  onChange={(event) =>
                    changeEdit(
                      "request_type",
                      event.target.value as Draft["request_type"],
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
                Urgência
                <select
                  required
                  value={editDraft.urgency}
                  onChange={(event) =>
                    changeEdit(
                      "urgency",
                      event.target.value as Draft["urgency"],
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
            {editDraft.request_type === "outro" && (
              <label>
                Qual tipo de pedido?
                <input
                  required
                  maxLength={200}
                  value={editDraft.type_detail || ""}
                  onChange={(event) =>
                    changeEdit("type_detail", event.target.value)
                  }
                />
              </label>
            )}
            {!!current.attachments.length && (
              <div className="request-attachments">
                <span className="field-help">Arquivos enviados</span>
                <ul className="request-files">
                  {current.attachments.map((file) => {
                    const removed =
                      !!file.id && removedAttachments.includes(file.id);
                    return (
                      <li
                        key={file.id}
                        className={removed ? "request-file--removed" : ""}
                      >
                        <span className="request-file-pdf">
                          {file.mime_type === "application/pdf" ? "PDF" : "IMG"}
                        </span>
                        <span>
                          {file.filename} · {size(file.size || 0)}
                        </span>
                        {file.id && (
                          <button
                            type="button"
                            className="request-text-button"
                            onClick={() =>
                              setRemovedAttachments((ids) =>
                                removed
                                  ? ids.filter((id) => id !== file.id)
                                  : [...ids, file.id!],
                              )
                            }
                          >
                            {removed ? "Manter" : "Remover"}
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            <label>
              Adicionar arquivos (imagem ou PDF, até 3 no total)
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
                multiple
                disabled={readingEditFiles}
                onChange={(event) => {
                  void addEditFiles(
                    Array.from(event.currentTarget.files || []),
                  );
                  event.currentTarget.value = "";
                }}
              />
            </label>
            {!!editDraft.attachments.length && (
              <ul className="request-files">
                {editDraft.attachments.map((file, index) => (
                  <li key={`${file.filename}-${index}`}>
                    <span className="request-file-pdf">NOVO</span>
                    <span>
                      {file.filename} · {size(file.size || 0)}
                    </span>
                    <button
                      type="button"
                      className="request-text-button"
                      onClick={() =>
                        changeEdit(
                          "attachments",
                          editDraft.attachments.filter(
                            (_, itemIndex) => itemIndex !== index,
                          ),
                        )
                      }
                    >
                      Remover
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {readingEditFiles && <p role="status">Lendo arquivos…</p>}
            {notice && (
              <p role="alert" className="request-error">
                {notice}
              </p>
            )}
            {editConflict && (
              <button
                type="button"
                className="request-button-secondary"
                onClick={() => void reloadEditVersion()}
              >
                Recarregar versão e manter rascunho
              </button>
            )}
            <div className="request-actions">
              <button type="submit">
                {busy ? "Salvando…" : "Salvar alterações"}
              </button>
              <button
                type="button"
                className="request-button-secondary"
                onClick={() => {
                  setEditing(false);
                  setEditDraft(draftFromRequest(current));
                  setRemovedAttachments([]);
                  setEditConflict(false);
                  setNotice("");
                }}
              >
                Cancelar
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {current.can_review ? (
        <fieldset disabled={busy} className="request-review-fields">
          <label>
            Resposta
            <textarea
              rows={2}
              maxLength={2000}
              placeholder="Resposta ou observação para quem pediu (opcional)"
              value={response}
              onChange={(event) => setResponse(event.target.value)}
            />
          </label>
          {!current.has_task && (
            <div className="request-assignment">
              {current.project_kind !== "existing" && !current.has_task && (
                <label>
                  Projeto para aprovação
                  <select
                    ref={projectInput}
                    value={projectId || ""}
                    onChange={(event) => {
                      setProjectId(Number(event.target.value) || null);
                      setAssigneeId("");
                    }}
                  >
                    <option value="">Escolha o projeto</option>
                    {projects.map((project) => (
                      <option value={project.id} key={project.id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                  <span className="field-help">
                    Se necessário,{" "}
                    <a
                      href={appHref("#/projects")}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      cadastre o projeto
                    </a>{" "}
                    e atualize esta tela.
                  </span>
                </label>
              )}
              <label>
                Responsável
                <select
                  ref={assigneeInput}
                  disabled={loadingPeople || !projectId}
                  value={assigneeId}
                  onChange={(event) => setAssigneeId(event.target.value)}
                >
                  <option value="">
                    {loadingPeople
                      ? "Carregando equipe…"
                      : "Escolha o responsável"}
                  </option>
                  {assignees.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Prazo
                <input
                  ref={dateInput}
                  type="date"
                  value={dueDate}
                  onChange={(event) => setDueDate(event.target.value)}
                />
              </label>
              <span className="field-help">
                Obrigatórios para aprovar. Ao aprovar, o pedido vira tarefa com
                esse dono e prazo.
              </span>
            </div>
          )}
          {notice && (
            <p role="alert" className="request-error">
              {notice}
            </p>
          )}
          <div className="request-actions">
            {actions
              .filter(([status]) => status !== current.status)
              .map(([status, label]) => (
                <button
                  key={status}
                  className={
                    status === "aprovado" ? "" : "request-button-secondary"
                  }
                  disabled={busy || (status === "aprovado" && loadingPeople)}
                  onClick={() => void review(status)}
                >
                  {busy ? "Salvando…" : label}
                </button>
              ))}
          </div>
        </fieldset>
      ) : (
        current.response && (
          <p className="request-response">
            <strong>Resposta</strong>
            <br />
            {current.response}
          </p>
        )
      )}
      {current.has_task && (
        <p className="request-warning">
          Esta solicitação já gerou uma tarefa. Reavaliar não cancela nem altera
          essa tarefa; uma nova aprovação preserva o responsável e o prazo
          atuais.
        </p>
      )}
      {current.task_id && (
        <a
          href={appHref(`#/tasks/${current.task_id}?board=${current.board_id}`)}
        >
          Abrir tarefa {current.task_code}
        </a>
      )}
    </article>
  );
}
