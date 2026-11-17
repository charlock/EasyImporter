/**
 * 导入页导出：映射后的数据（.xlsx）。
 * 表头为目标列，行取当前映射值（含 viewer 内的改动与常量覆盖）；
 * 校验错误格标红底。exceljs 懒加载，不进首屏包。
 */
import type { MappedRow } from "@/features/mapping/apply";

import type { IndexedError } from "./viewerSync";

/** 触发浏览器下载（Blob URL，用完即回收）。 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** 文件名去扩展名（"sample.xlsx" → "sample"），无扩展名时原样返回。 */
export function stripExtension(filename: string): string {
  const index = filename.lastIndexOf(".");
  return index > 0 ? filename.slice(0, index) : filename;
}

export async function exportMappedXlsx(
  columns: string[],
  rows: MappedRow[],
  errors: IndexedError[],
): Promise<Blob> {
  const { default: ExcelJS } = await import("exceljs");
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("导入数据");
  sheet.addRow(columns);
  const headerRow = sheet.getRow(1);
  headerRow.font = { bold: true };
  for (const row of rows) {
    sheet.addRow(columns.map((column) => row.values[column] ?? null));
  }
  // 错误格：IndexedError.index 是映射行下标，导出表里第 index + 2 行（首行是表头）。
  for (const { index, error } of errors) {
    const columnIndex = columns.indexOf(error.column);
    if (index < 0 || columnIndex === -1) continue;
    const cell = sheet.getRow(index + 2).getCell(columnIndex + 1);
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFFECACA" } };
  }
  const buffer = await workbook.xlsx.writeBuffer();
  return new Blob([buffer as BlobPart], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}
