import { describe, expect, it } from "vitest";

import {
  initialModel,
  shouldShowEntry,
  type TemplatePageModel,
} from "./state";

const S1: TemplatePageModel = { state: "S1", returnState: null, selectedId: 7, previousId: null };
const S2: TemplatePageModel = { state: "S2", returnState: "S0", selectedId: null, previousId: null };
const S3: TemplatePageModel = { state: "S3", returnState: "S1", selectedId: 7, previousId: null };

describe("shouldShowEntry", () => {
  it("S2 无样例未跳过 → 展示入口面板", () => {
    expect(shouldShowEntry(S2, { hasSample: false, dismissed: false })).toBe(true);
  });
  it("S3 无样例未跳过 → 展示入口面板（保留数据、可换样例）", () => {
    expect(shouldShowEntry(S3, { hasSample: false, dismissed: false })).toBe(true);
  });
  it("样例上传后 → 不展示，进入正常编辑器视图", () => {
    expect(shouldShowEntry(S2, { hasSample: true, dismissed: false })).toBe(false);
    expect(shouldShowEntry(S2, { hasSample: true, dismissed: true })).toBe(false);
    expect(shouldShowEntry(S3, { hasSample: true, dismissed: false })).toBe(false);
  });
  it("用户点“进入编辑器”跳过后 → 不展示", () => {
    expect(shouldShowEntry(S2, { hasSample: false, dismissed: true })).toBe(false);
    expect(shouldShowEntry(S3, { hasSample: false, dismissed: true })).toBe(false);
  });
  it("S0/S1 不展示（S1 仍为只读旧视图）", () => {
    expect(shouldShowEntry(initialModel, { hasSample: false, dismissed: false })).toBe(false);
    expect(shouldShowEntry(S1, { hasSample: false, dismissed: false })).toBe(false);
  });
});
