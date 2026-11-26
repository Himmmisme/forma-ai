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

export type Task = "optimize" | "inspect" | "generate" | "edit" | "materials" | "manufacturing" | "cost_advice";
export const taskNames: Record<Task, string> = {
  optimize: "提示词优化", inspect: "产品原图分析", generate: "图片生成", edit: "图片修改",
  materials: "材料选型", manufacturing: "制造工艺分析", cost_advice: "成本辅助评估",
};
export const capabilityNames = { text: "文本", vision: "图片理解", image_generate: "图片生成", image_edit: "图片编辑", multi_image: "多图输入" };
export type Capability = keyof typeof capabilityNames;
export type Protocol = "mock" | "openai" | "gemini" | "compatible";

export interface Template {
  id: string; slug: string; kind: "level" | "direction"; name: string; summary: string;
  body: string; sort: number; enabled: boolean; revision: number;
}
export interface SizeOption { ratio: string; value: string; label: string }
export interface Model {
  id: string; name: string; model_code: string; protocol: Protocol; provider_id: string; provider_name: string;
  provider_enabled: boolean; enabled: boolean; capabilities: Capability[]; sizes: SizeOption[];
  max_count: number; max_inputs: number; pricing: string; tasks?: Task[];
}
export interface Provider {
  id: string; name: string; protocol: Protocol; base_url: string; timeout: number; concurrency: number;
  enabled: boolean; has_key: boolean;
}
export interface Catalog {
  templates: Template[]; models: Model[]; defaults: Record<Task, string | null>;
}
export type Status = "queued" | "running" | "succeeded" | "failed";
export const statusNames: Record<Status, string> = { queued: "排队中", running: "处理中", succeeded: "成功", failed: "失败" };
export interface Call {
  id: string; generation: number; operation: string; status: string; request_id: string | null;
  http_status: number | null; elapsed_ms: number | null; usage: Record<string, unknown> | null; created_at: string;
}
export interface Job {
  id: string; project_id: string | null; model_id: string | null; model_code: string | null; provider_id: string;
  kind: Task | "probe_connection" | "probe_model"; mock: boolean; status: Status; error: string | null; generation: number;
  result: {
    version_ids?: string[]; assets?: Asset[]; optimized?: string; conflicts?: string[];
    summary?: string; uncertainties?: string[]; message?: string; models?: string[];
    width?: number; height?: number;
  } | null;
  calls?: Call[];
  created_at: string; updated_at: string;
}

export interface Version {
  id: string; project_id: string; user_id: string; parent_id: string | null; job_id: string;
  number: number; favorite: boolean; created_at: string; status: Status; mock: boolean; asset: Asset | null;
  direction: string; level: string; model_name: string; project_name?: string;
}
export interface VersionList { items: Version[]; more: boolean }
export interface VersionDetail extends Version {
  project_name: string; author: string; parent_number: number | null; originals: Asset[]; references: Asset[];
  iteration: Asset | null; job: Job;
  configuration: {
    raw: string; optimized: string; final: string; constraints: string; prompt: string; warnings: string[];
    provider: { id: string; name: string; protocol: Protocol; base_url: string };
    model: { id: string; name: string; model_code: string; pricing: string };
    templates: { base_revision: string; main: Template; auxiliary: Template[]; level: Template };
    output: { count: number; ratio: string; size: string; background: string; view: string };
  };
}
