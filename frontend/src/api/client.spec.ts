import { afterEach, describe, expect, it, vi } from "vitest";

import { api, getCsrfToken, setCsrfToken } from "./client";

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
