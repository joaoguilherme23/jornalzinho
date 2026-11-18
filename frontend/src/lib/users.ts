import { api } from "../api";
import type { Membership, Page, Project, ProjectRole, User } from "../types";

const LIMIT = 50;

export type UserCreate = {
  name: string;
  email: string;
  password: string;
  global_role: User["global_role"];
  project_access?: {
    scope: "all" | "selected";
    project_ids?: number[];
    role: ProjectRole;
  };
};
export type UserUpdate = Partial<
  Pick<User, "name" | "email" | "is_active" | "global_role">
>;

async function listAll<T>(url: string): Promise<T[]> {
  const items: T[] = [];
  for (let offset = 0; ; offset += LIMIT) {
    const response = await api.get<Page<T>>(url, {
      params: { offset, limit: LIMIT },
    });
    items.push(...response.data.items);
    if (items.length >= response.data.total || !response.data.items.length)
      return items;
  }
}

export function getUsers(options: {
  q: string;
  includeInactive: boolean;
  offset: number;
}) {
  return api
    .get<Page<User>>("api/v1/users", {
      params: {
        q: options.q.trim() || undefined,
        include_inactive: options.includeInactive,
        offset: options.offset,
        limit: LIMIT,
      },
    })
    .then((response) => response.data);
}
export function getMemberships(userId: number) {
  return listAll<Membership>(`api/v1/users/${userId}/memberships`);
}
export function getProjects() {
  return listAll<Project>("api/v1/projects");
}
export function createUser(data: UserCreate) {
  return api.post<User>("api/v1/users", data).then((response) => response.data);
}
export function updateUser(id: number, data: UserUpdate) {
  return api
    .patch<User>(`api/v1/users/${id}`, data)
    .then((response) => response.data);
}
export function resetUserPassword(id: number, password: string) {
  return api.post(`api/v1/users/${id}/reset-password`, { password });
}
export function setMembership(
  projectId: number,
  email: string,
  role: ProjectRole,
) {
  return api.put(`api/v1/projects/${projectId}/members`, { email, role });
}
export function removeMembership(projectId: number, userId: number) {
  return api.delete(`api/v1/projects/${projectId}/members/${userId}`);
}

export type BulkMembershipChange = {
  action: "add" | "remove";
  scope: "all" | "selected";
  project_ids?: number[];
  role?: ProjectRole;
};

export type BulkMembershipResult = {
  added: number;
  removed: number;
  unchanged: number;
};

export function changeMembershipsBulk(
  userId: number,
  data: BulkMembershipChange,
) {
  return api
    .post<BulkMembershipResult>(`api/v1/users/${userId}/memberships/bulk`, data)
    .then((response) => response.data);
}
