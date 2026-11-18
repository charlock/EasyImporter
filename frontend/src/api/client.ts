import type { ApiErrorBody } from "@/lib/types";

/** 后端返回的业务错误。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly params: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.params = body.params ?? {};
  }
}

const API_PREFIX = "/api/v1";

let csrfToken = "";

/** 登录或刷新会话后更新 CSRF token，写请求都会带上。 */
export function setCsrfToken(token: string): void {
  csrfToken = token;
}

export function getCsrfToken(): string {
  return csrfToken;
}

/** 会话过期回调：会话过期（401 UNAUTHORIZED）时只通知一次。 */
let sessionExpiredHandler: (() => void) | null = null;
let sessionExpiredNotified = false;

/** 注册会话过期回调，由 main.ts 在应用启动后注册一次。 */
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  sessionExpiredHandler = handler;
}

/** 登录或会话刷新成功后调用，允许下一次过期再次通知。 */
export function resetSessionExpiredNotified(): void {
  sessionExpiredNotified = false;
}

function notifySessionExpired(): void {
  if (sessionExpiredNotified) return;
  sessionExpiredNotified = true;
  sessionExpiredHandler?.();
}

/**
 * 401 UNAUTHORIZED 即会话过期（无 Cookie、会话不存在或 8 小时闲置过期）。
 * 例外：/auth/login 的 401 是 LOGIN_FAILED（用户名或密码错），/auth/me 的
 * 401 由路由守卫处理（session.load 失败即视为未登录），两者都不在这里通知。
 */
function notifyIfSessionExpired(status: number, code: string, path: string): void {
  if (status === 401 && code === "UNAUTHORIZED" && path !== "/auth/login" && path !== "/auth/me") {
    notifySessionExpired();
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  query?: Record<string, string | number | boolean | undefined>;
}

async function requestOnce<T>(path: string, options: RequestOptions, retried: boolean): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const query = options.query
    ? "?" +
      Object.entries(options.query)
        .filter(([, value]) => value !== undefined && value !== "")
        .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
        .join("&")
    : "";

  const response = await fetch(`${API_PREFIX}${path}${query}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed = text ? (JSON.parse(text) as unknown) : undefined;
  if (!response.ok) {
    const error = (parsed ?? { code: "UNKNOWN", message: response.statusText }) as ApiErrorBody;
    notifyIfSessionExpired(response.status, error.code, path);
    if (!retried && response.status === 403 && error.code === "CSRF_INVALID") {
      // token 可能已漂移（例如多会话登录后 /me 曾返回别的会话的 token）：
      // 重新拉 /me 取当前会话的 token 再试一次。403 表示服务端在依赖层
      // 就拒绝了，处理函数未执行，因此重试不会重复落库。
      try {
        const refreshed = await fetch(`${API_PREFIX}/auth/me`, { credentials: "same-origin" });
        const me = refreshed.ok ? ((await refreshed.json()) as { csrf_token?: string }) : null;
        if (me?.csrf_token) {
          setCsrfToken(me.csrf_token);
          return requestOnce<T>(path, options, true);
        }
      } catch {
        // 刷新失败时落到下面的原始错误，不掩盖它。
      }
    }
    throw new ApiError(response.status, error);
  }
  return parsed as T;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return requestOnce<T>(path, options, false);
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"]) => request<T>(path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", form }),
};

/** 取回一个受会话保护的文件内容（不触发下载），供只读预览等场景使用。 */
export async function fetchBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_PREFIX}${path}`, { credentials: "same-origin" });
  if (!response.ok) {
    const text = await response.text();
    const error = text
      ? (JSON.parse(text) as ApiErrorBody)
      : { code: "UNKNOWN", message: response.statusText };
    notifyIfSessionExpired(response.status, error.code, path);
    throw new ApiError(response.status, error);
  }
  return response.blob();
}

/** 触发浏览器下载一个受会话保护的文件。 */
export async function download(path: string, filename: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}${path}`, { credentials: "same-origin" });
  if (!response.ok) {
    const text = await response.text();
    const error = text
      ? (JSON.parse(text) as ApiErrorBody)
      : { code: "UNKNOWN", message: response.statusText };
    notifyIfSessionExpired(response.status, error.code, path);
    throw new ApiError(response.status, error);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
