import { describe, expect, it } from "vitest";

import {
  applyTextFilter,
  cellMatchesKind,
  importStatusTone,
  pageNumbers,
} from "./listTypes";

describe("pageNumbers", () => {
  it("总页数 ≤ 7 时全部展开", () => {
    expect(pageNumbers(1, 1)).toEqual([1]);
    expect(pageNumbers(3, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageNumbers(7, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("首页：首两页 + 尾两页，中间折叠", () => {
    expect(pageNumbers(1, 10)).toEqual([1, 2, "…", 9, 10]);
  });

  it("中间页：当前页前后各一页，两头折叠", () => {
    expect(pageNumbers(5, 10)).toEqual([1, 2, "…", 4, 5, 6, "…", 9, 10]);
  });

  it("尾页：与首页对称", () => {
    expect(pageNumbers(10, 10)).toEqual([1, 2, "…", 9, 10]);
  });

  it("总页数为 0 时为空", () => {
    expect(pageNumbers(1, 0)).toEqual([]);
  });
});

describe("cellMatchesKind", () => {
  it("五种表达各与自己的 kind 一致", () => {
    expect(cellMatchesKind("link", { type: "link", to: "/x", label: "x" })).toBe(true);
    expect(cellMatchesKind("badge", { type: "badge", label: "x", tone: "muted" })).toBe(true);
    expect(cellMatchesKind("text", { type: "text", text: "x" })).toBe(true);
    expect(cellMatchesKind("meta", { type: "meta", primary: "x" })).toBe(true);
    expect(cellMatchesKind("count", { type: "count", primary: "x" })).toBe(true);
  });

  it("表达与 kind 不符时拒绝，actions 列没有单元格值", () => {
    expect(cellMatchesKind("text", { type: "badge", label: "x", tone: "muted" })).toBe(false);
    expect(cellMatchesKind("link", { type: "text", text: "x" })).toBe(false);
    expect(cellMatchesKind("actions", { type: "text", text: "x" })).toBe(false);
  });
});

describe("importStatusTone", () => {
  it("终态与进行态各有固定底色", () => {
    expect(importStatusTone("SUCCEEDED")).toBe("success");
    expect(importStatusTone("FAILED")).toBe("danger");
    expect(importStatusTone("UNKNOWN")).toBe("warning");
    expect(importStatusTone("RUNNING")).toBe("info");
    expect(importStatusTone("COMMITTING")).toBe("info");
    expect(importStatusTone("QUEUED")).toBe("muted");
    expect(importStatusTone("CANCELLED")).toBe("muted");
  });
});

describe("applyTextFilter", () => {
  const rows = [
    { name: "零售数据（月报）", table: "sales_monthly" },
    { name: "Weekly Report", table: "weekly" },
    { name: "库存", table: "stock" },
  ];

  it("空查询返回原数组", () => {
    expect(applyTextFilter(rows, "  ", (r) => [r.name])).toEqual(rows);
  });

  it("按任一字段子串命中，不区分大小写", () => {
    expect(applyTextFilter(rows, "月报", (r) => [r.name, r.table])).toHaveLength(1);
    expect(applyTextFilter(rows, "WEEKLY", (r) => [r.name, r.table])).toHaveLength(1);
    expect(applyTextFilter(rows, "sales", (r) => [r.name, r.table])).toHaveLength(1);
  });

  it("无命中返回空数组", () => {
    expect(applyTextFilter(rows, "不存在", (r) => [r.name])).toEqual([]);
  });
});
