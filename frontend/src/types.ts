export type GlobalRole = "admin" | "user";
export type ProjectRole = "manager" | "member" | "viewer";
export type User = {
  id: number; name: string; email: string; is_active: boolean;
  global_role: GlobalRole; must_change_password: boolean;
};
export type Participant = Pick<User, "id" | "name" | "email" | "is_active">;
export type ProjectMember = { user: Participant; role: ProjectRole };
export type Membership = { project_id: number; project_key: string; project_name: string; role: ProjectRole };
export type LabelColor = "teal" | "blue" | "purple" | "orange" | "red" | "gray";
export type Label = { id: number; project_id: number; name: string; color: LabelColor; is_archived: boolean };
export type Priority = "low" | "medium" | "high" | "critical";
export type TaskType = "task" | "bug" | "improvement";
export type Column = {
  id: number;
  name: string;
  position: number;
  is_done: boolean;
};
export type Project = {
  id: number;
  key: string;
  name: string;
  description: string | null;
  legacy_app_id: string | null;
  default_board_id: number | null;
  role?: ProjectRole | "admin";
};
export type Task = {
  id: number;
  code: string;
  board_id: number;
  title: string;
  description: string | null;
  column_id: number;
  column: Pick<Column, "id" | "name" | "is_done">;
  priority: Priority;
  type: TaskType;
  reporter: Participant;
  assignee: Participant | null;
  due_date: string | null;
  position: number;
  version: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  archived_at: string | null;
  labels: Label[];
  role?: ProjectRole | "admin";
};
export type Board = {
  id: number;
  name: string;
  project: Pick<Project, "id" | "key" | "name">;
  default_column_id: number | null;
  columns: Column[];
  tasks: Task[];
  tasks_total: number;
  tasks_offset: number;
  tasks_limit: number;
  role?: ProjectRole | "admin";
};
export type Page<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};
export type Comment = {
  id: number;
  task_id: number;
  author: Participant;
  body: string;
  created_at: string;
  updated_at: string;
};
export type History = {
  id: number;
  event: string;
  actor: Participant;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  created_at: string;
};
export type Mural = { gerado_em: string; apps: GitApp[] };
export type GitApp = {
  id: string;
  nome: string;
  releases?: {
    versao: string;
    data: string;
    resumo?: string | null;
    mudancas?: Record<string, unknown>;
  }[];
};
