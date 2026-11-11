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

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  query?: Record<string, string | number | undefined>;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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
    throw new ApiError(response.status, error);
  }
  return parsed as T;
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"]) => request<T>(path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", form }),
};

/** 触发浏览器下载一个受会话保护的文件。 */
export async function download(path: string, filename: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}${path}`, { credentials: "same-origin" });
  if (!response.ok) {
    const text = await response.text();
    const error = text
      ? (JSON.parse(text) as ApiErrorBody)
      : { code: "UNKNOWN", message: response.statusText };
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
