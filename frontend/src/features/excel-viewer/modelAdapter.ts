/**
 * 模型适配器：ooxml-excel-editor 的 WorkbookModel → 领域 ParsedSheet。
 *
 * 依赖边界：只依赖 Vue 之外的通用层——库的类型（WorkbookModel / CellModel /
 * MergeRange）、通用表头树（@/features/header/tree）与 ParsedSheet 类型
 * （@/features/excel/parse，仅类型导入）。不依赖页面、UI 组件、api client、
 * 映射/校验等 EasyImporter 专属层。
 *
 * 下标约定：库模型与合并区均为 0 基；rowNumbers 是 1 基 Excel 行号；
 * leafColumns 的值是 0 基列号。
 */
import type { CellModel, MergeRange, WorkbookModel } from "ooxml-excel-editor/core";

import type { ParsedSheet } from "@/features/excel/parse";
import { buildHeaderTree, type HeaderCell } from "@/features/header/tree";

/** ParsedSheet + “叶子路径 → 0 基列号”索引，供错误定位与选区联动用。 */
export interface AdaptedSheet extends ParsedSheet {
  /** 叶子路径用 \u0000 连接 → 0 基列号。 */
  leafColumns: Map<string, number>;
}

/** 单元格显示文本（表头用）：rich 拼接、Date 转 ISO 日期、公式取 computed 结果（raw）。 */
export function cellDisplayText(cell: CellModel | undefined): string {
  if (!cell) return "";
  if (cell.rich) return cell.rich.map((run) => run.text).join("");
  if (cell.raw == null) return "";
  if (cell.raw instanceof Date) return cell.raw.toISOString().slice(0, 10);
  return String(cell.raw);
}

/** 数据行值（原始值）：number / string / boolean / null，只有 Date 在边界转 ISO 日期字符串。 */
export function cellRawValue(cell: CellModel | undefined): unknown {
  if (!cell || cell.raw == null) return null;
  if (cell.raw instanceof Date) return cell.raw.toISOString().slice(0, 10);
  return cell.raw;
}

function cellOf(sheet: WorkbookModel["sheets"][number], row: number, col: number): CellModel | undefined {
  return sheet.cells.get(`${row}:${col}`);
}

/** 叶子列是否全空（格缺失、raw 为 null/undefined/"" 都算空；0 与 false 不算空）。 */
function isLeafEmpty(sheet: WorkbookModel["sheets"][number], row: number, leafColumn: number): boolean {
  const cell = cellOf(sheet, row, leafColumn);
  return !cell || cell.raw == null || cell.raw === "";
}

export function sheetNames(model: WorkbookModel | null): string[] {
  if (!model) return [];
  return model.sheets.map((sheet) => sheet.name);
}

export function modelSheetIndex(model: WorkbookModel | null, name: string): number {
  if (!model) return -1;
  return model.sheets.findIndex((sheet) => sheet.name === name);
}

/**
 * 库模型 → ParsedSheet。
 * 表头矩阵用模型 cells（key 为 `${row}:${col}`，0 基）+ merges，调现有 buildHeaderTree；
 * 数据行从 headerStartRow + headerRowCount 起到 dimension.rows - 1，跳过叶子列全空的行；
 * hiddenRows 按 sheet.rows Map 的 hidden 统计（只计保留下来的数据行）。
 */
export function modelToParsedSheet(
  model: WorkbookModel,
  sheetIndex: number,
  headerStartRow: number,
  headerRowCount: number,
): AdaptedSheet {
  const sheet = model.sheets[sheetIndex];
  if (!sheet) throw new Error(`工作簿里没有第 ${sheetIndex + 1} 张工作表`);

  const headerCells: HeaderCell[][] = [];
  for (let row = 0; row < headerRowCount; row += 1) {
    const cellsRow: HeaderCell[] = [];
    for (let col = 0; col < sheet.dimension.cols; col += 1) {
      cellsRow.push({ value: cellDisplayText(cellOf(sheet, headerStartRow + row, col)) });
    }
    headerCells.push(cellsRow);
  }
  const merges: MergeRange[] = sheet.merges.filter(
    (merge) => merge.bottom >= headerStartRow && merge.top < headerStartRow + headerRowCount,
  );
  const header = buildHeaderTree(headerCells, merges, headerStartRow);

  const leafColumns = new Map<string, number>();
  for (const leaf of header.leaves) {
    leafColumns.set(leaf.path.join("\u0000"), leaf.column);
  }

  const rows: Record<string, unknown>[] = [];
  const rowNumbers: number[] = [];
  let hiddenRows = 0;
  const firstDataRow = headerStartRow + headerRowCount;
  for (let row = firstDataRow; row < sheet.dimension.rows; row += 1) {
    if (header.leaves.every((leaf) => isLeafEmpty(sheet, row, leaf.column))) continue;
    if (sheet.rows.get(row)?.hidden) hiddenRows += 1;
    const record: Record<string, unknown> = {};
    for (const leaf of header.leaves) {
      record[leaf.path.join("\u0000")] = cellRawValue(cellOf(sheet, row, leaf.column));
    }
    rows.push(record);
    rowNumbers.push(row + 1);
  }

  return { name: sheet.name, header, rows, rowNumbers, hiddenRows, leafColumns };
}

/** 行列定位：row 为 1 基 Excel 行号（取自 rowNumbers[rowIndex]），column 取自 leafColumns。 */
export function cellPosition(
  sheet: AdaptedSheet,
  rowIndex: number,
  pathKey: string,
): { row: number; column: number } | null {
  const row = sheet.rowNumbers[rowIndex];
  const column = sheet.leafColumns.get(pathKey);
  if (row == null || column == null) return null;
  return { row, column };
}
