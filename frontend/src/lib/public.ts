import axios from "axios";
import type { Attachment, RequestPayload } from "./requests";

const baseURL =
  typeof document === "undefined"
    ? "http://localhost/"
    : new URL("./", document.baseURI).href;
const client = axios.create({ baseURL, withCredentials: true });

export type PublicProject = {
  id: number;
  name: string;
  summary: string | null;
};
export type PublicWork = {
  code: string;
  title: string;
  summary: string | null;
  project_id: number;
  project_name: string;
  status: string;
  updated_at: string;
};
export type PublicNews = {
  id: number;
  title: string;
  summary: string | null;
  body: string | null;
  project_name: string | null;
  published_at: string | null;
};
export type PublicPage<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};
export type PublicRequestPayload = RequestPayload & { contact: string };
export type PublicRequest = {
  protocol: string;
  name: string;
  description: string;
  status: string;
  response: string | null;
  created_at: string;
  reviewed_at: string | null;
  execution_status: string | null;
  version: number;
};
export type PublicRequestDraft = RequestPayload & {
  protocol: string;
  contact: string;
  status: string;
  response: string | null;
  version: number;
  attachments: Attachment[];
};
export type PublicRequestUpdatePayload = PublicRequestPayload & {
  version: number;
  remove_attachment_ids?: number[];
};
export type PublicationProject = {
  id: number;
  name: string;
  can_publish: boolean;
};
export type PublicationDetail = {
  project: {
    id: number;
    name: string;
    summary: string | null;
    published: boolean;
    version: number;
  };
  columns: {
    id: number;
    name: string;
    is_done: boolean;
    status: string | null;
  }[];
  tasks: {
    id: number;
    code: string;
    internal_title: string;
    title: string | null;
    summary: string | null;
    published: boolean;
    version: number;
  }[];
};
export type PublicationNews = PublicNews & {
  project_id: number | null;
  published: boolean;
  version: number;
};

const path = (value: string) => `api/v1/public${value}`;
export const publicApi = {
  projects: () =>
    client
      .get<{ items: PublicProject[] }>(path("/projects"))
      .then((r) => r.data.items),
  work: (
    params: {
      project_id?: number;
      status?: string;
      q?: string;
      offset?: number;
      limit?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    client
      .get<PublicPage<PublicWork>>(path("/work"), {
        params: { ...params, limit: params.limit ?? 12 },
        signal,
      })
      .then((r) => r.data),
  workByCode: (code: string) =>
    client
      .get<PublicWork>(path(`/work/${encodeURIComponent(code)}`))
      .then((r) => r.data),
  news: (
    params: { offset?: number; limit?: number } = {},
    signal?: AbortSignal,
  ) =>
    client
      .get<PublicPage<PublicNews>>(path("/news"), {
        params: { ...params, limit: params.limit ?? 12 },
        signal,
      })
      .then((r) => r.data),
  newsById: (id: string) =>
    client
      .get<PublicNews>(path(`/news/${encodeURIComponent(id)}`))
      .then((r) => r.data),
  request: (
    data: PublicRequestPayload,
    idempotencyKey: string,
    requestKey: string,
  ) =>
    client
      .post<{ protocol: string }>(path("/requests"), data, {
        headers: {
          "Idempotency-Key": idempotencyKey,
          "X-Request-Key": requestKey,
        },
      })
      .then((r) => r.data),
  lookup: (protocol: string, key: string) =>
    client
      .post<PublicRequest>(path("/requests/lookup"), { protocol, key })
      .then((r) => r.data),
  draft: (protocol: string, key: string) =>
    client
      .get<PublicRequestDraft>(
        path(`/requests/${encodeURIComponent(protocol)}`),
        {
          headers: { "X-Request-Key": key },
        },
      )
      .then((r) => r.data),
  update: (protocol: string, key: string, data: PublicRequestUpdatePayload) =>
    client
      .put<PublicRequestDraft>(
        path(`/requests/${encodeURIComponent(protocol)}`),
        data,
        { headers: { "X-Request-Key": key } },
      )
      .then((r) => r.data),
  resubmit: (protocol: string, key: string, version: number) =>
    client
      .post<PublicRequest>(
        path(`/requests/${encodeURIComponent(protocol)}/resubmit`),
        { version },
        { headers: { "X-Request-Key": key } },
      )
      .then((r) => r.data),
};

export const newKey = () => crypto.randomUUID();
export const secureRequestKey = () => {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
};
export const attachmentPayload = (items: Attachment[]) =>
  items.map(({ filename, mime_type, content_base64 }) => ({
    filename,
    mime_type,
    content_base64,
  }));
export const publicError = (failure: unknown) => {
  if (axios.isAxiosError(failure)) {
    if (!failure.response)
      return "Não foi possível conectar. Confira sua conexão e tente novamente.";
    if (failure.response.status === 404)
      return "Não encontramos esse conteúdo.";
    if (failure.response.status === 403)
      return "Os dados informados não permitem consultar esta solicitação.";
    if (failure.response.status === 422)
      return "Confira os campos preenchidos e tente novamente.";
    if (failure.response.status >= 500)
      return "O serviço está indisponível agora. Tente novamente em alguns instantes.";
    const detail = failure.response.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return "Não foi possível concluir a ação.";
};
