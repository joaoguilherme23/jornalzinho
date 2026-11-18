import { api, backend } from "../api";
import type { Project, User } from "../types";

export type RequestStatus = "em_avaliacao" | "ajuste" | "aprovado" | "recusado";
export type Attachment = {
  id?: number;
  filename: string;
  mime_type: string;
  size?: number;
  content_base64?: string;
};
export type RequestItem = {
  id: number;
  name: string;
  area: string | null;
  project_id: number | null;
  project_name: string | null;
  project_kind: string;
  request_type: string;
  type_detail: string | null;
  description: string;
  location: string | null;
  purpose: string;
  example_url: string | null;
  urgency: "travando" | "importante" | "seria_bom";
  attachments: Attachment[];
  status: RequestStatus;
  response: string | null;
  version: number;
  created_at: string;
  reviewed_at: string | null;
  requester_id: number | null;
  origin?: "internal" | "public";
  contact?: string | null;
  reviewer_id: number | null;
  task_id: number | null;
  task_code: string | null;
  board_id: number | null;
  can_review: boolean;
  has_task?: boolean;
};
export type RequestUpdatePayload = RequestPayload & {
  version: number;
  /** Arquivos novos; os jÃ¡ enviados sÃ³ saem por remove_attachment_ids. */
  remove_attachment_ids?: number[];
};
export type RequestPage = {
  items: RequestItem[];
  total: number;
  offset: number;
  limit: number;
  counts: Record<RequestStatus, number>;
};
export type RequestPayload = {
  name: string;
  area?: string | null;
  project_id?: number | null;
  project_kind: "existing" | "novo_projeto" | "outro";
  project_name?: string | null;
  request_type:
    | "correcao"
    | "dado_novo"
    | "melhoria"
    | "funcionalidade"
    | "novo_projeto"
    | "outro";
  type_detail?: string | null;
  description: string;
  location?: string | null;
  purpose: string;
  example_url?: string | null;
  urgency: "travando" | "importante" | "seria_bom";
  attachments: Attachment[];
};
export const requestApi = {
  projects: () => backend.projects(),
  create: (data: RequestPayload, key: string) =>
    api
      .post<RequestItem>("api/v1/requests", data, {
        headers: { "Idempotency-Key": key },
      })
      .then((r) => r.data),
  update: (id: number, data: RequestUpdatePayload) =>
    api.put<RequestItem>(`api/v1/requests/${id}`, data).then((r) => r.data),
  resubmit: (id: number, version: number) =>
    api
      .post<RequestItem>(`api/v1/requests/${id}/resubmit`, { version })
      .then((r) => r.data),
  list: (status: RequestStatus, offset = 0) =>
    api
      .get<RequestPage>("api/v1/requests", {
        params: { status, offset, limit: 50 },
      })
      .then((r) => r.data),
  get: (id: number) =>
    api.get<RequestItem>(`api/v1/requests/${id}`).then((r) => r.data),
  assignees: (projectId: number) => backend.assignees(projectId),
  review: (
    id: number,
    data: {
      version: number;
      status: RequestStatus;
      response?: string | null;
      assignee_id?: number | null;
      due_date?: string | null;
      project_id?: number | null;
    },
  ) =>
    api
      .post<RequestItem>(`api/v1/requests/${id}/review`, data)
      .then((r) => r.data),
  attachment: (requestId: number, attachmentId: number) =>
    api
      .get<Blob>(`api/v1/requests/${requestId}/attachments/${attachmentId}`, {
        responseType: "blob",
      })
      .then((r) => r.data),
};
export const requestTypes = {
  correcao: "Correção de erro",
  dado_novo: "Campo ou dado novo",
  melhoria: "Melhoria no que já existe",
  funcionalidade: "Funcionalidade nova",
  novo_projeto: "Novo projeto",
  outro: "Outro",
} as const;
export const urgencyLabels = {
  travando: "Está travando meu trabalho",
  importante: "Importante, mas consigo seguir",
  seria_bom: "Seria bom ter",
} as const;
export const fileToAttachment = async (file: File): Promise<Attachment> => ({
  filename: file.name,
  mime_type: file.type,
  size: file.size,
  content_base64: await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  }),
});
export const validFiles = (files: File[]) =>
  files
    .filter(
      (file) =>
        /^(image\/(png|jpeg|webp|gif)|application\/pdf)$/.test(file.type) &&
        file.size <= 5 * 1024 * 1024,
    )
    .slice(0, 3);
export type { Project, User };
