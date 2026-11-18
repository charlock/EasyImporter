import { describe, expect, it } from "vitest";

import { resolveLoginRedirect } from "./auth";

describe("resolveLoginRedirect", () => {
  it("站内路径原样返回", () => {
    expect(resolveLoginRedirect("/imports")).toBe("/imports");
    expect(resolveLoginRedirect("/templates/3?x=1")).toBe("/templates/3?x=1");
  });

  it("非字符串、空值回首页", () => {
    expect(resolveLoginRedirect(undefined)).toBe("/");
    expect(resolveLoginRedirect(["/imports"])).toBe("/");
    expect(resolveLoginRedirect("")).toBe("/");
  });

  it("站外与协议相对地址回首页", () => {
    expect(resolveLoginRedirect("https://evil.example.com")).toBe("/");
    expect(resolveLoginRedirect("//evil.example.com")).toBe("/");
  });

  it("/login 本身回首页", () => {
    expect(resolveLoginRedirect("/login")).toBe("/");
  });
});
