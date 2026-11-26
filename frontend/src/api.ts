import { useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function api<T>(path: string, method = "GET", body?: object, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-Forma-Action"] = "1";
  if (body && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api${path}`, {
    ...options, method, headers, credentials: "same-origin",
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(typeof payload.detail === "string" ? payload.detail : "请求失败，请稍后重试", response.status);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export function message(error: unknown) {
  return error instanceof ApiError ? error.message : "暂时无法连接服务，请稍后重试";
}

export function useResource<T>(path: string | null, pollMs = 0) {
  const [request, setRequest] = useState(0);
  const [state, setState] = useState<{ path: string; data?: T; error?: string }>({ path: "" });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let pending = false;
    async function load() {
      if (pending || controller.signal.aborted) return;
      pending = true;
      try {
        const data = await api<T>(path!, "GET", undefined, { signal: controller.signal });
        if (!controller.signal.aborted) setState({ path: path!, data });
      } catch (error) {
        if (!controller.signal.aborted) {
          setState((current) => ({ path: path!, data: current.path === path ? current.data : undefined, error: message(error) }));
        }
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = pollMs ? window.setInterval(load, pollMs) : undefined;
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [path, request, pollMs]);
  const current = state.path === path ? state : undefined;
  return { data: current?.data, error: current?.error, loading: !!path && !current, refresh: () => setRequest((v) => v + 1) };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(action: () => Promise<unknown>) {
    setError("");
    setBusy(true);
    try { await action(); }
    catch (exception) { setError(message(exception)); }
    finally { setBusy(false); }
  }
  return { run, busy, error, setError };
}

export function assetUrl(id: string, download = false) {
  return `/api/assets/${encodeURIComponent(id)}/content${download ? "?download=true" : ""}`;
}

export function dateTime(value?: string | null) {
  return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

export function requestKey() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) => v.toString(16).padStart(2, "0")).join("");
}
