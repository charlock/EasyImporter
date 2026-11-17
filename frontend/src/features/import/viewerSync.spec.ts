import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { parseWorkbook } from "ooxml-excel-editor/core";

import { modelToParsedSheet, type AdaptedSheet } from "@/features/excel-viewer/modelAdapter";
import { applyMapping } from "@/features/mapping/apply";
import { validateRow } from "@/features/rules/execute";
import type { ColumnRule, Mapping } from "@/lib/types";
import {
  applyCellEditToRawRows,
  collectErrorPositions,
  editableTargets,
  expandMappedRows,
  normalizeCellValue,
  pathKey,
  resyncRowsFromModel,
  resolveCellEdit,
  resolveErrorCell,
  resolveErrorCellByRow,
} from "./viewerSync";

/** 与 modelAdapter.spec.ts 同一份样例：表“销售”，表头 0 基第 0 行起、共 2 行，数据 3 行。 */
const SAMPLE_PATH = join(
  process.env.HOME ?? "",
  "workspace/easyimporter-local-verify/verify/sample.xlsx",
);

function sampleBuffer(): ArrayBuffer {
  const buf = readFileSync(SAMPLE_PATH);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

async function sampleSheet(): Promise<AdaptedSheet> {
  const model = await parseWorkbook(sampleBuffer());
  return modelToParsedSheet(model, 0, 0, 2);
}

const PLAIN_MAPPING: Mapping = {
  columns: [
    { excel_path: ["水单号"], db_column: "serial_no" },
    { excel_path: ["公司"], db_column: "company" },
    { excel_path: ["1月份", "销售额"], db_column: "sales_jan" },
    { excel_path: ["1月份", "利润"], db_column: "profit_jan" },
    { excel_path: ["2月份", "销售额"], db_column: "sales_feb" },
    { excel_path: ["2月份", "利润"], db_column: "profit_feb" },
  ],
  unpivot: null,
  constants: [],
};

function unpivotMapping(skipEmpty: boolean): Mapping {
  return {
    columns: [
      { excel_path: ["水单号"], db_column: "serial_no" },
      { excel_path: ["公司"], db_column: "company" },
    ],
    unpivot: {
      dimension_column: "month",
      groups: [
        { dimension_value: "1月份", match_prefix: ["1月份"] },
        { dimension_value: "2月份", match_prefix: ["2月份"] },
      ],
      measures: [
        { excel_leaf: "销售额", db_column: "sales" },
        { excel_leaf: "利润", db_column: "profit" },
      ],
      skip_empty_measures: skipEmpty,
    },
    constants: [{ db_column: "period", value: "2026-01" }],
  };
}

/** 带尾部总计行的样例：与 sample.xlsx 同结构，第 6 行为总计行（水单号/公司为空、1 月销售额写“总计”）。 */
const TOTAL_PATH = join(
  process.env.HOME ?? "",
  "workspace/easyimporter-local-verify/verify/sample-total.xlsx",
);

function totalBuffer(): ArrayBuffer {
  const buf = readFileSync(TOTAL_PATH);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

async function totalSheet(): Promise<AdaptedSheet> {
  const model = await parseWorkbook(totalBuffer());
  return modelToParsedSheet(model, 0, 0, 2);
}

/** 删总计行错误消失：重取后行数/行号跟上最新结构，必填错误随之消失。 */
const REQUIRED_RULES: ColumnRule[] = [
  { db_column: "serial_no", type: "string", precision: null, scale: null, required: true, default: null, max_length: null, enum: null, pattern: null },
  { db_column: "company", type: "string", precision: null, scale: null, required: true, default: null, max_length: null, enum: null, pattern: null },
  { db_column: "sales_jan", type: "decimal", precision: null, scale: null, required: false, default: null, max_length: null, enum: null, pattern: null },
  { db_column: "profit_jan", type: "decimal", precision: null, scale: null, required: false, default: null, max_length: null, enum: null, pattern: null },
  { db_column: "sales_feb", type: "decimal", precision: null, scale: null, required: false, default: null, max_length: null, enum: null, pattern: null },
  { db_column: "profit_feb", type: "decimal", precision: null, scale: null, required: false, default: null, max_length: null, enum: null, pattern: null },
];

function validateAll(
  rows: Record<string, unknown>[],
  rowNumbers: number[],
  mapping: Mapping,
  rules: ColumnRule[],
) {
  const errors: { row_no: number; column: string; code: string }[] = [];
  for (let i = 0; i < rows.length; i += 1) {
    const expanded = expandMappedRows(rows[i]!, mapping, rowNumbers[i]!);
    for (const row of expanded.rows) {
      for (const err of validateRow(rules, row.values, row.row_no).errors) errors.push(err);
    }
  }
  return errors;
}

describe("resyncRowsFromModel（删行后重取重校验）", () => {
  it("总计行在：重取得到 4 行，行号 3-6", async () => {
    const model = await parseWorkbook(totalBuffer());
    const next = resyncRowsFromModel(model, 0, 0, 2);
    expect(next.rawRows).toHaveLength(4);
    expect(next.rowNumbers).toEqual([3, 4, 5, 6]);
    expect(next.rawRows[3]![pathKey(["1月份", "销售额"])]).toBe("总计");
  });

  it("删总计行：重取后只剩 3 行，行号 3-5，提交数据与最新行一致", async () => {
    const model = await parseWorkbook(totalBuffer());
    const sheet = model.sheets[0]!;
    // 模拟 viewer 删行后的模型：第 6 行（0 基第 5 行）的格子没了，dimension 收缩。
    for (let col = 0; col < sheet.dimension.cols; col += 1) sheet.cells.delete(`5:${col}`);
    sheet.dimension.rows = 6;
    const next = resyncRowsFromModel(model, 0, 0, 2);
    expect(next.rawRows).toHaveLength(3);
    expect(next.rowNumbers).toEqual([3, 4, 5]);
    expect(next.rawRows.map((row) => row[pathKey(["水单号"])])).toEqual(["S001", "S002", "S003"]);
    expect(next.rawRows.some((row) => row[pathKey(["1月份", "销售额"])] === "总计")).toBe(false);
  });

  it("删总计行错误消失：删前 #6 两条必填错误，删后 0 错误", async () => {
    const model = await parseWorkbook(totalBuffer());
    const before = resyncRowsFromModel(model, 0, 0, 2);
    const errorsBefore = validateAll(before.rawRows, before.rowNumbers, PLAIN_MAPPING, REQUIRED_RULES);
    // 总计行：serial_no/company 为空（REQUIRED），1 月销售额写了“总计”文本（TYPE_MISMATCH）。
    expect(errorsBefore).toEqual([
      { row_no: 6, column: "serial_no", code: "REQUIRED", params: {} },
      { row_no: 6, column: "company", code: "REQUIRED", params: {} },
      { row_no: 6, column: "sales_jan", code: "TYPE_MISMATCH", params: {} },
    ]);
    const sheet = model.sheets[0]!;
    for (let col = 0; col < sheet.dimension.cols; col += 1) sheet.cells.delete(`5:${col}`);
    sheet.dimension.rows = 6;
    const after = resyncRowsFromModel(model, 0, 0, 2);
    expect(validateAll(after.rawRows, after.rowNumbers, PLAIN_MAPPING, REQUIRED_RULES)).toEqual([]);
  });

  it("改格后重校验：改成非法值出 TYPE_MISMATCH，改回合法值错误消失", async () => {
    const adapted = await sampleSheet();
    const illegal = applyCellEditToRawRows(
      adapted.rows,
      adapted.rowNumbers,
      3,
      pathKey(["1月份", "销售额"]),
      "abc",
    )!;
    expect(
      validateAll(illegal, adapted.rowNumbers, PLAIN_MAPPING, REQUIRED_RULES).map((e) => e.code),
    ).toEqual(["TYPE_MISMATCH"]);
    const fixed = applyCellEditToRawRows(
      illegal,
      adapted.rowNumbers,
      3,
      pathKey(["1月份", "销售额"]),
      1000.5,
    )!;
    expect(validateAll(fixed, adapted.rowNumbers, PLAIN_MAPPING, REQUIRED_RULES)).toEqual([]);
  });

  it("改格后重校验：必填列清空出 REQUIRED，填回后错误消失", async () => {
    const adapted = await sampleSheet();
    const cleared = applyCellEditToRawRows(
      adapted.rows,
      adapted.rowNumbers,
      3,
      pathKey(["水单号"]),
      "",
    )!;
    expect(
      validateAll(cleared, adapted.rowNumbers, PLAIN_MAPPING, REQUIRED_RULES),
    ).toEqual([{ row_no: 3, column: "serial_no", code: "REQUIRED", params: {} }]);
    const restored = applyCellEditToRawRows(
      cleared,
      adapted.rowNumbers,
      3,
      pathKey(["水单号"]),
      "S001",
    )!;
    expect(validateAll(restored, adapted.rowNumbers, PLAIN_MAPPING, REQUIRED_RULES)).toEqual([]);
  });
});

describe("expandMappedRows", () => {
  it("非拆行：与 applyMapping 一致，来源全为 null", async () => {
    const adapted = await sampleSheet();
    const row = adapted.rows[0]!;
    const expanded = expandMappedRows(row, PLAIN_MAPPING, 3);
    expect(expanded.rows).toEqual(applyMapping(row, PLAIN_MAPPING, 3));
    expect(expanded.rows).toHaveLength(1);
    expect(expanded.sources).toEqual([{ rowNo: 3, groupIndex: null }]);
    expect(expanded.rows[0]!.values["sales_jan"]).toBe(1000.5);
  });

  it("拆行：每行产出 2 条，来源分组按顺序一一对应，与整行 applyMapping 一致", async () => {
    const adapted = await sampleSheet();
    const mapping = unpivotMapping(false);
    for (const [i, row] of adapted.rows.entries()) {
      const expanded = expandMappedRows(row, mapping, adapted.rowNumbers[i]!);
      expect(expanded.rows).toEqual(applyMapping(row, mapping, adapted.rowNumbers[i]!));
      expect(expanded.rows).toHaveLength(2);
      expect(expanded.sources.map((source) => source.groupIndex)).toEqual([0, 1]);
      expect(expanded.rows[0]!.values).toMatchObject({ month: "1月份" });
      expect(expanded.rows[0]!.values["sales"]).toBe(row[pathKey(["1月份", "销售额"])]);
      expect(expanded.rows[1]!.values).toMatchObject({ month: "2月份" });
      expect(expanded.rows[1]!.values["sales"]).toBe(row[pathKey(["2月份", "销售额"])]);
      expect(expanded.rows[0]!.values["period"]).toBe("2026-01");
    }
  });

  it("拆行 skip_empty：某分组度量全空时只产出另一组", async () => {
    const adapted = await sampleSheet();
    const mapping = unpivotMapping(true);
    const row = {
      ...adapted.rows[0]!,
      [pathKey(["2月份", "销售额"])]: null,
      [pathKey(["2月份", "利润"])]: "",
    };
    const expanded = expandMappedRows(row, mapping, 3);
    expect(expanded.rows).toHaveLength(1);
    expect(expanded.rows[0]!.values["month"]).toBe("1月份");
    expect(expanded.sources).toEqual([{ rowNo: 3, groupIndex: 0 }]);
  });

  it("常量覆盖：导入时输入的常量值写进产出行", async () => {
    const adapted = await sampleSheet();
    const expanded = expandMappedRows(adapted.rows[0]!, unpivotMapping(false), 3, {
      period: "2026-02",
    });
    expect(expanded.rows[0]!.values["period"]).toBe("2026-02");
  });
});

describe("resolveCellEdit / applyCellEditToRawRows", () => {
  it("普通列：列号命中叶子路径与目标列", async () => {
    const adapted = await sampleSheet();
    expect(resolveCellEdit(adapted, PLAIN_MAPPING, 2)).toEqual({
      pathKey: pathKey(["1月份", "销售额"]),
      dbColumns: ["sales_jan"],
    });
    expect(resolveCellEdit(adapted, PLAIN_MAPPING, 0)?.dbColumns).toEqual(["serial_no"]);
  });

  it("拆行度量列：同一叶子命中度量目标列", async () => {
    const adapted = await sampleSheet();
    expect(resolveCellEdit(adapted, unpivotMapping(false), 4)).toEqual({
      pathKey: pathKey(["2月份", "销售额"]),
      dbColumns: ["sales"],
    });
  });

  it("不在表头树里的列返回 null", async () => {
    const adapted = await sampleSheet();
    expect(resolveCellEdit(adapted, PLAIN_MAPPING, 6)).toBeNull();
  });

  it("写回原始行：只改目标行与目标键，不改原数组", async () => {
    const adapted = await sampleSheet();
    const next = applyCellEditToRawRows(
      adapted.rows,
      adapted.rowNumbers,
      4,
      pathKey(["公司"]),
      "新公司",
    );
    expect(next).not.toBeNull();
    expect(next![1]![pathKey(["公司"])]).toBe("新公司");
    expect(adapted.rows[1]![pathKey(["公司"])]).not.toBe("新公司");
    expect(next![0]).toBe(adapted.rows[0]);
    expect(applyCellEditToRawRows(adapted.rows, adapted.rowNumbers, 99, "公司", "x")).toBeNull();
  });

  it("normalizeCellValue：Date 转 ISO 日期，其余原样", () => {
    expect(normalizeCellValue(new Date("2026-01-15T00:00:00Z"))).toBe("2026-01-15");
    expect(normalizeCellValue(1000.5)).toBe(1000.5);
    expect(normalizeCellValue(null)).toBeNull();
  });
});

describe("错误定位", () => {
  it("普通列：row_no 换算为 0 基行，叶子列号直接取", async () => {
    const adapted = await sampleSheet();
    expect(
      resolveErrorCell(adapted, PLAIN_MAPPING, { rowNo: 4, groupIndex: null }, "sales_jan"),
    ).toEqual({ row: 3, column: 2 });
  });

  it("拆行度量列：按来源分组定位到该分组的格子", async () => {
    const adapted = await sampleSheet();
    const mapping = unpivotMapping(false);
    expect(resolveErrorCell(adapted, mapping, { rowNo: 4, groupIndex: 1 }, "sales")).toEqual({
      row: 3,
      column: 4,
    });
    expect(resolveErrorCell(adapted, mapping, { rowNo: 4, groupIndex: 0 }, "sales")).toEqual({
      row: 3,
      column: 2,
    });
  });

  it("维度列与常量列没有对应的格子", async () => {
    const adapted = await sampleSheet();
    const mapping = unpivotMapping(false);
    expect(
      resolveErrorCell(adapted, mapping, { rowNo: 4, groupIndex: 0 }, "month"),
    ).toBeNull();
    expect(
      resolveErrorCell(adapted, mapping, { rowNo: 4, groupIndex: 0 }, "period"),
    ).toBeNull();
  });

  it("resolveErrorCellByRow：按行号回退，取第一个能定位的来源", async () => {
    const adapted = await sampleSheet();
    const mapping = unpivotMapping(false);
    const sources = [
      { rowNo: 3, groupIndex: 0 },
      { rowNo: 3, groupIndex: 1 },
      { rowNo: 4, groupIndex: 0 },
    ];
    expect(resolveErrorCellByRow(adapted, mapping, sources, 3, "sales")).toEqual({
      row: 2,
      column: 2,
    });
    expect(resolveErrorCellByRow(adapted, mapping, sources, 3, "month")).toBeNull();
  });

  it("collectErrorPositions：错误格集合用 0 基 key，清单保留行号与错误码", async () => {
    const adapted = await sampleSheet();
    const sources = [
      { rowNo: 3, groupIndex: null },
      { rowNo: 4, groupIndex: null },
      { rowNo: 5, groupIndex: null },
    ];
    const { cells, items } = collectErrorPositions(adapted, PLAIN_MAPPING, sources, [
      { index: 0, error: { row_no: 3, column: "sales_jan", code: "TYPE_MISMATCH", params: {} } },
      { index: 1, error: { row_no: 4, column: "period", code: "REQUIRED", params: {} } },
      { index: -1, error: { row_no: 5, column: "serial_no", code: "DUPLICATE_KEY_IN_FILE", params: {} } },
    ]);
    expect([...cells].sort()).toEqual(["2:2", "4:0"]);
    expect(items).toHaveLength(3);
    expect(items[0]).toEqual({ rowNo: 3, column: "sales_jan", code: "TYPE_MISMATCH", row: 2, col: 2 });
    expect(items[1]!.col).toBeNull();
    expect(items[2]).toEqual({
      rowNo: 5,
      column: "serial_no",
      code: "DUPLICATE_KEY_IN_FILE",
      row: 4,
      col: 0,
    });
  });
});

describe("editableTargets", () => {
  it("已映射列在数据行范围内的矩形区域，表头行不在内", async () => {
    const adapted = await sampleSheet();
    const targets = editableTargets(PLAIN_MAPPING, adapted, 2, 13);
    expect(targets).toHaveLength(6);
    expect(targets[0]).toEqual({ top: 2, left: 0, bottom: 12, right: 0 });
    expect(targets[2]).toEqual({ top: 2, left: 2, bottom: 12, right: 2 });
    expect(targets[5]).toEqual({ top: 2, left: 5, bottom: 12, right: 5 });
  });

  it("拆行：只含度量列，不含维度列与常量列", async () => {
    const adapted = await sampleSheet();
    const targets = editableTargets(unpivotMapping(false), adapted, 2, 13);
    expect(targets.map((target) => target.left).sort()).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("无数据行或无映射列时返回空数组", async () => {
    const adapted = await sampleSheet();
    expect(editableTargets(PLAIN_MAPPING, adapted, 2, 2)).toEqual([]);
    expect(
      editableTargets({ columns: [], unpivot: null, constants: [] }, adapted, 2, 13),
    ).toEqual([]);
  });
});
