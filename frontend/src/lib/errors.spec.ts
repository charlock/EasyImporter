import { describe, expect, it, vi } from "vitest";

/**
 * errors.ts 依赖 @/locales，而它在模块顶层读 localStorage，node 测试环境没有。
 * 这里用真实的中文文案造一个最小 i18n 替身，只覆盖 errorMessageWithDetail 用到的 te/t。
 */
vi.mock("@/locales", async () => {
  const { default: zh } = await import("@/locales/zh");
  const errors = zh.errors as Record<string, string>;
  return {
    i18n: {
      global: {
        locale: { value: "zh" },
        te: (key: string) => key.startsWith("errors.") && key.slice("errors.".length) in errors,
        t: (key: string) => errors[key.slice("errors.".length)] ?? key,
      },
    },
  };
});

import { ApiError } from "@/api/client";

import { errorMessageWithDetail } from "./errors";

describe("errorMessageWithDetail", () => {
  it("有翻译且后端给了具体原因时显示“通用文案：具体原因”", () => {
    const caught = new ApiError(422, {
      code: "TEMPLATE_INVALID",
      message: "映射到不存在的列：uscc, company_name",
    });
    expect(errorMessageWithDetail(caught)).toBe(
      "模板配置不合法：映射到不存在的列：uscc, company_name",
    );
  });

  it("没有翻译的错误码直接显示后端原文（如建表时的标识符错误）", () => {
    const message =
      "字段名 '报告期' 不合法：只允许英文字母、数字与下划线，且以字母或下划线开头，长度不超过 63 字节；中文名请改用英文字段名";
    const caught = new ApiError(400, { code: "INVALID_IDENTIFIER", message });
    expect(errorMessageWithDetail(caught)).toBe(message);
  });

  it("后端没有具体原因时只显示通用文案", () => {
    expect(errorMessageWithDetail(new ApiError(422, { code: "TEMPLATE_INVALID" }))).toBe(
      "模板配置不合法",
    );
  });

  it("没有翻译时退回后端原文", () => {
    const caught = new ApiError(422, { code: "SOME_UNKNOWN_CODE", message: "some reason" });
    expect(errorMessageWithDetail(caught)).toBe("some reason");
  });

  it("非 ApiError 时与 errorMessage 一致", () => {
    expect(errorMessageWithDetail(new Error("boom"))).toBe("boom");
  });
});
