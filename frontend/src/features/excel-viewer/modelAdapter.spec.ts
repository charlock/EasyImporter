import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { parseWorkbook } from "ooxml-excel-editor/core";

import { parseBuffer } from "@/features/excel/parse";
import {
  cellPosition,
  modelSheetIndex,
  modelToParsedSheet,
  sheetNames,
} from "./modelAdapter";
import { inferSelectionKind } from "./useExcelViewer";

/** 样例文件：销售月度样例，1 张表“销售”；表头 0 基第 0 行起、共 2 行；数据 3 行。 */
const SAMPLE_PATH = join(
  process.env.HOME ?? "",
  "workspace/easyimporter-local-verify/verify/sample.xlsx",
);

function sampleBuffer(): ArrayBuffer {
  const buf = readFileSync(SAMPLE_PATH);
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

const HEADER_START_ROW = 0;
const HEADER_ROW_COUNT = 2;

describe("modelToParsedSheet 与现有 parseBuffer 在同一文件上一致", () => {
  it("叶子路径、行号、隐藏行数与逐格值一致", async () => {
    const buffer = sampleBuffer();
    const model = await parseWorkbook(buffer.slice(0));
    const adapted = modelToParsedSheet(model, 0, HEADER_START_ROW, HEADER_ROW_COUNT);
    const parsed = await parseBuffer(buffer.slice(0), {
      sheet: "销售",
      headerStartRow: HEADER_START_ROW,
      headerRowCount: HEADER_ROW_COUNT,
    });

    expect(adapted.name).toBe(parsed.name);
    expect(adapted.header.leaves.map((leaf) => `${leaf.column}:${leaf.path.join("/")}`)).toEqual(
      parsed.header.leaves.map((leaf) => `${leaf.column}:${leaf.path.join("/")}`),
    );
    expect(adapted.header.leaves.map((leaf) => `${leaf.column}:${leaf.path.join("/")}`)).toEqual([
      "0:水单号",
      "1:公司",
      "2:1月份/销售额",
      "3:1月份/利润",
      "4:2月份/销售额",
      "5:2月份/利润",
    ]);
    expect(adapted.rowNumbers).toEqual(parsed.rowNumbers);
    expect(adapted.rowNumbers).toEqual([3, 4, 5]);
    expect(adapted.hiddenRows).toBe(parsed.hiddenRows);
    expect(adapted.rows).toHaveLength(parsed.rows.length);
    // 行值：适配器取原始值（number），parseBuffer 取 cellText 字符串；
    // 逐格按 String(原始值) 对齐比较（null/空按 ""）。
    for (let i = 0; i < parsed.rows.length; i += 1) {
      for (const key of Object.keys(parsed.rows[i]!)) {
        const raw = adapted.rows[i]![key];
        expect(raw == null ? "" : String(raw)).toBe(parsed.rows[i]![key]);
      }
    }
    // 原始值本身是 number，不是字符串。
    expect(adapted.rows[0]!["1月份\u0000销售额"]).toBe(1000.5);
    expect(adapted.rows[1]!["水单号"]).toBe("S002");
  });

  it("leafColumns 与 cellPosition", async () => {
    const model = await parseWorkbook(sampleBuffer());
    const adapted = modelToParsedSheet(model, 0, HEADER_START_ROW, HEADER_ROW_COUNT);
    expect(adapted.leafColumns.get("水单号")).toBe(0);
    expect(adapted.leafColumns.get("1月份\u0000销售额")).toBe(2);
    expect(adapted.leafColumns.get("2月份\u0000利润")).toBe(5);
    expect(adapted.leafColumns.size).toBe(6);
    expect(cellPosition(adapted, 0, "1月份\u0000销售额")).toEqual({ row: 3, column: 2 });
    expect(cellPosition(adapted, 2, "水单号")).toEqual({ row: 5, column: 0 });
    expect(cellPosition(adapted, 3, "水单号")).toBeNull();
    expect(cellPosition(adapted, 0, "不存在\u0000列")).toBeNull();
  });

  it("sheetNames / modelSheetIndex", async () => {
    const model = await parseWorkbook(sampleBuffer());
    expect(sheetNames(model)).toEqual(["销售"]);
    expect(sheetNames(null)).toEqual([]);
    expect(modelSheetIndex(model, "销售")).toBe(0);
    expect(modelSheetIndex(model, "不存在")).toBe(-1);
    expect(modelSheetIndex(null, "销售")).toBe(-1);
  });

  it("不存在的表抛错", async () => {
    const model = await parseWorkbook(sampleBuffer());
    expect(() => modelToParsedSheet(model, 5, 0, 2)).toThrow();
  });
});

describe("inferSelectionKind", () => {
  const dimension = { rows: 13, cols: 6 };
  it("整行：left=0 且 right=cols-1 且 top=bottom", () => {
    expect(inferSelectionKind({ top: 3, left: 0, bottom: 3, right: 5 }, dimension)).toBe("row");
  });
  it("整列：top=0 且 bottom=rows-1 且 left=right", () => {
    expect(inferSelectionKind({ top: 0, left: 1, bottom: 12, right: 1 }, dimension)).toBe(
      "column",
    );
  });
  it("单格：1x1", () => {
    expect(inferSelectionKind({ top: 3, left: 1, bottom: 3, right: 1 }, dimension)).toBe("cell");
  });
  it("其余为 range", () => {
    expect(inferSelectionKind({ top: 2, left: 1, bottom: 4, right: 3 }, dimension)).toBe("range");
    expect(inferSelectionKind({ top: 0, left: 0, bottom: 2, right: 2 }, dimension)).toBe("range");
  });
});
