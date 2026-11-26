export type Role = "superadmin" | "admin" | "user";
export const roleNames: Record<Role, string> = { superadmin: "超级管理员", admin: "管理员", user: "普通用户" };

export interface User {
  id: string;
  username: string;
  name: string;
  role: Role;
  enabled: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface Asset {
  id: string;
  project_id: string;
  kind: "original" | "reference" | "cover" | "result";
  filename: string;
  width: number;
  height: number;
  mime: string;
  size: number;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  version_count: number;
  cover_id: string | null;
  favorite: boolean;
  archived: boolean;
  deleted_at: string | null;
  demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectList { items: Project[]; more: boolean }

export interface Dashboard {
  projects: number;
  versions: number;
  running: number;
  recent: Project[];
}
