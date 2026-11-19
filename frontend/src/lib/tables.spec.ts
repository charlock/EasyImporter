import { describe, expect, it } from "vitest";

import { filterTargetTables, tableKey } from "@/lib/tables";
import type { TableInfo } from "@/lib/types";

const TABLES: TableInfo[] = [
  { schema: "public", name: "sales_monthly" },
  { schema: "public", name: "customers" },
  { schema: "archive", name: "sales_2024" },
];

describe("filterTargetTables", () => {
  it("空查询返回全部", () => {
    expect(filterTargetTables(TABLES, "")).toEqual(TABLES);
    expect(filterTargetTables(TABLES, "   ")).toEqual(TABLES);
  });

  it("按表名子串匹配，不区分大小写", () => {
    expect(filterTargetTables(TABLES, "sales").map((t) => t.name)).toEqual([
      "sales_monthly",
      "sales_2024",
    ]);
    expect(filterTargetTables(TABLES, "SALES").map((t) => t.name)).toEqual([
      "sales_monthly",
      "sales_2024",
    ]);
  });

  it("按 schema.name 匹配", () => {
    expect(filterTargetTables(TABLES, "archive.sales").map((t) => t.name)).toEqual(["sales_2024"]);
  });

  it("无匹配返回空数组", () => {
    expect(filterTargetTables(TABLES, "zzz")).toEqual([]);
  });
});

describe("tableKey", () => {
  it("schema 不同则键不同", () => {
    expect(tableKey({ schema: "public", name: "t" })).not.toBe(
      tableKey({ schema: "archive", name: "t" }),
    );
    expect(tableKey({ schema: "public", name: "t" })).toBe(
      tableKey({ schema: "public", name: "t" }),
    );
  });
});
