import { describe, expect, it } from "vitest";

import ExcelJS from "exceljs";

import { exportMappedXlsx, stripExtension } from "./exportMapped";

describe("stripExtension", () => {
  it("去扩展名，无扩展名时原样返回", () => {
    expect(stripExtension("sample.xlsx")).toBe("sample");
    expect(stripExtension("销售月度.UPSERT.xlsx")).toBe("销售月度.UPSERT");
    expect(stripExtension("sample")).toBe("sample");
  });
});

describe("exportMappedXlsx", () => {
  it("表头为目标列，行取当前映射值，错误格标红底", async () => {
    const blob = await exportMappedXlsx(
      ["serial_no", "company", "sales"],
      [
        { row_no: 3, values: { serial_no: "S001", company: "A", sales: 1000.5 } },
        { row_no: 4, values: { serial_no: "S002", company: "B", sales: 200 } },
      ],
      [{ index: 0, error: { row_no: 3, column: "sales", code: "TYPE_MISMATCH", params: {} } }],
    );
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.load(await blob.arrayBuffer());
    const sheet = workbook.getWorksheet("导入数据");
    expect(sheet).toBeDefined();
    expect(sheet!.getRow(1).values).toEqual([undefined, "serial_no", "company", "sales"]);
    expect(sheet!.getRow(2).values).toEqual([undefined, "S001", "A", 1000.5]);
    expect(sheet!.getRow(3).values).toEqual([undefined, "S002", "B", 200]);
    const errorCell = sheet!.getRow(2).getCell(3);
    expect(errorCell.fill).toMatchObject({
      type: "pattern",
      fgColor: { argb: "FFFECACA" },
    });
    // 无错误的格子不标红。
    expect(sheet!.getRow(3).getCell(3).fill).not.toMatchObject({
      fgColor: { argb: "FFFECACA" },
    });
  });
});
