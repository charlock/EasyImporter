import { describe, expect, it } from "vitest";

import type { Mapping } from "@/lib/types";

import { applyMapping, missingHeaders } from "./apply";

const mapping: Mapping = {
  columns: [{ excel_path: ["流水号"], db_column: "serial_no" }],
  constants: [{ db_column: "source", value: "excel" }],
  unpivot: {
    dimension_column: "month",
    groups: [
      { dimension_value: "2026-01", match_prefix: ["1月"] },
      { dimension_value: "2026-02", match_prefix: ["2月"] },
    ],
    measures: [{ excel_leaf: "销售额", db_column: "amount" }],
    skip_empty_measures: true,
  },
};

describe("applyMapping", () => {
  it("unpivots groups and skips empty measures", () => {
    const row = { "流水号": "S1", "1月\u0000销售额": "10", "2月\u0000销售额": "" };
    expect(applyMapping(row, mapping, 5)).toEqual([
      { row_no: 5, values: { serial_no: "S1", source: "excel", month: "2026-01", amount: "10" } },
    ]);
  });
});

describe("missingHeaders", () => {
  it("lists required paths absent from the file", () => {
    const missing = missingHeaders(mapping, [["流水号"], ["1月", "销售额"]]);
    expect(missing).toEqual([["2月", "销售额"]]);
  });
});

describe("applyMapping constantOverrides", () => {
  const row = { "流水号": "S1", "1月\u0000销售额": "10", "2月\u0000销售额": "" };
  it("导入时输入的常量值覆盖模板固定值", () => {
    const rows = applyMapping(row, mapping, 2, { source: "web" });
    expect(rows).toHaveLength(1);
    expect(rows[0].values.source).toBe("web");
  });
  it("没有覆盖时仍用模板固定值", () => {
    const rows = applyMapping(row, mapping, 2);
    expect(rows[0].values.source).toBe("excel");
  });
});
