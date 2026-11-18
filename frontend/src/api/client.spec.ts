import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  api,
  download,
  getCsrfToken,
  resetSessionExpiredNotified,
  setCsrfToken,
  setSessionExpiredHandler,
} from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("CSRF token 漂移自愈", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setCsrfToken("");
  });

  it("写请求报 CSRF_INVALID 时刷新 /me 并重试一次，第二次成功则返回结果", async () => {
    setCsrfToken("stale-token");
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      if (url === "/api/v1/auth/me") return jsonResponse(200, { csrf_token: "fresh-token" });
      if (url === "/api/v1/workspaces/1/datasources/2/tables/infer") {
        const token = (init?.headers as Record<string, string> | undefined)?.["X-CSRF-Token"];
        if (token === "stale-token") {
          return jsonResponse(403, { code: "CSRF_INVALID", message: "expired", params: {} });
        }
        return jsonResponse(200, { columns: [], ddl: "CREATE TABLE t (a TEXT);" });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await api.post<{ ddl: string }>("/workspaces/1/datasources/2/tables/infer", {
      table_name: "t",
      columns: [],
    });
    expect(res.ddl).toContain("CREATE TABLE");
    expect(getCsrfToken()).toBe("fresh-token");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("重试后仍报 CSRF_INVALID 时只试一次并抛出原错误", async () => {
    setCsrfToken("stale-token");
    const fetchMock = vi.fn(async (input: string | URL | Request): Promise<Response> => {
      const url = String(input);
      if (url === "/api/v1/auth/me") return jsonResponse(200, { csrf_token: "still-stale" });
      return jsonResponse(403, { code: "CSRF_INVALID", message: "expired", params: {} });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.post("/workspaces/1/datasources/2/tables/infer", {})).rejects.toMatchObject({
      code: "CSRF_INVALID",
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("非 CSRF 错误不重试", async () => {
    setCsrfToken("good-token");
    const fetchMock = vi.fn(async (): Promise<Response> =>
      jsonResponse(422, { code: "VALIDATION_FAILED", message: "bad", params: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.post("/workspaces/1/templates", {})).rejects.toMatchObject({
      code: "VALIDATION_FAILED",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("会话过期通知", () => {
  const handler = vi.fn();

  beforeEach(() => {
    handler.mockClear();
    setSessionExpiredHandler(handler);
    resetSessionExpiredNotified();
  });

  afterEach(() => {
    setSessionExpiredHandler(null);
    resetSessionExpiredNotified();
    vi.unstubAllGlobals();
  });

  function unauthorized(): Response {
    return jsonResponse(401, { code: "UNAUTHORIZED", message: "未登录或会话已过期" });
  }

  it("401 UNAUTHORIZED 时通知一次，错误仍照常抛出", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
    await expect(api.get("/workspaces")).rejects.toMatchObject({
      code: "UNAUTHORIZED",
      status: 401,
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("多次 401 只通知一次（轮询等场景不会重复跳转）", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
    await expect(api.get("/workspaces")).rejects.toThrow();
    await expect(api.get("/templates")).rejects.toThrow();
    await expect(api.get("/imports")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("重置后下一次 401 会再次通知", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
    await expect(api.get("/workspaces")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
    resetSessionExpiredNotified();
    await expect(api.get("/workspaces")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it("登录接口的 401 LOGIN_FAILED 不通知", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(401, { code: "LOGIN_FAILED", message: "用户名或密码错误" })),
    );
    await expect(api.post("/auth/login", { username: "a", password: "b" })).rejects.toMatchObject({
      code: "LOGIN_FAILED",
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("/auth/me 的 401 不通知（由路由守卫处理）", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
    await expect(api.get("/auth/me")).rejects.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });

  it("403 / 500 不通知", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(403, { code: "FORBIDDEN", message: "没有权限执行该操作" })),
    );
    await expect(api.get("/workspaces")).rejects.toThrow();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(500, { code: "UNKNOWN", message: "oops" })));
    await expect(api.get("/workspaces")).rejects.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });

  it("download 的 401 UNAUTHORIZED 也通知", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
    await expect(download("/imports/1/file", "x.xlsx")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
