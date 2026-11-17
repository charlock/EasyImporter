/** 导入记录页的纯逻辑：可删状态判断、错误 → Viewer 单元格定位。
 * 不依赖 Vue / API / Viewer 实例，可直接单测。 */

import type { AdaptedSheet } from "@/features/excel-viewer/modelAdapter";
import type { ImportError, ImportStatus, Mapping } from "@/lib/types";

/** 前端能发起删除的状态；已被 worker 认领的 QUEUED 后端会再以 409 拒绝。 */
const DELETABLE_STATUSES: ImportStatus[] = ["SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"];

export function canDeleteImport(status: ImportStatus): boolean {
  return status === "QUEUED" || DELETABLE_STATUSES.includes(status);
}

/** 错误定位到的 Viewer 单元格（0 基行列，与 ooxml-excel-editor 模型一致）。 */
export interface ErrorCellTarget {
  row: number;
  column: number;
}

/**
 * 错误 → 单元格：error.column 是目标字段名，先经该版本模板的映射找到 Excel
 * 叶子路径，再经 AdaptedSheet.leafColumns 取 0 基列号；error.row_no 是 1 基
 * Excel 行号（提交时写入的 _row），先在 rowNumbers 里找对应数据行，找不到
 * 时退回 row_no - 1。映射或表头里找不到该列时返回 null（不跳格）。
 * 拆行度量列不在 mapping.columns 里：按 viewerSync.resolveErrorCell 的逻辑，
 * 经 unpivot 分组溯源到具体格子（分组用该行原始值区分，见 measureCellPosition）。
 */
export function errorCellPosition(
  error: ImportError,
  mapping: Mapping,
  sheet: AdaptedSheet | null,
): ErrorCellTarget | null {
  if (!sheet) return null;
  const column = mapping.columns.find((item) => item.db_column === error.column);
  if (column) {
    const col = sheet.leafColumns.get(column.excel_path.join("\u0000"));
    if (col == null) return null;
    const rowIndex = sheet.rowNumbers.indexOf(error.row_no);
    const row = rowIndex >= 0 ? sheet.rowNumbers[rowIndex] - 1 : error.row_no - 1;
    return { row, column: col };
  }
  return measureCellPosition(error, mapping, sheet);
}

/**
 * 度量列 → 具体分组的格：error 只有 row_no + 列名、没有分组信息，分组只能从
 * 该行原始值溯源——错误来自某条拆行产出行，该分组的度量格必有值；类型不符时
 * 值通常是文本（数字/布尔/日期在转换里都能通过），先找文本格，再找任意非空
 * 格；全空时（例如必填缺失）仍落到首个分组的格子，保证能跳格；行号不在
 * rowNumbers 里时没有原始值可比，同样落到首个分组。找不到度量列或任一分组
 * 的叶子都不在表头里时返回 null（不跳格）。
 */
function measureCellPosition(
  error: ImportError,
  mapping: Mapping,
  sheet: AdaptedSheet,
): ErrorCellTarget | null {
  const unpivot = mapping.unpivot;
  if (!unpivot) return null;
  const measure = unpivot.measures.find((item) => item.db_column === error.column);
  if (!measure) return null;
  const rowIndex = sheet.rowNumbers.indexOf(error.row_no);
  const row = rowIndex >= 0 ? sheet.rowNumbers[rowIndex] - 1 : error.row_no - 1;
  const record = rowIndex >= 0 ? sheet.rows[rowIndex] : undefined;
  const candidates: { column: number; value: unknown }[] = [];
  for (const group of unpivot.groups) {
    const key = [...group.match_prefix, measure.excel_leaf].join("\u0000");
    const column = sheet.leafColumns.get(key);
    if (column == null) continue;
    candidates.push({ column, value: record?.[key] });
  }
  if (candidates.length === 0) return null;
  const isBlank = (value: unknown): boolean =>
    value == null || (typeof value === "string" && value.trim() === "");
  const text = candidates.find((item) => typeof item.value === "string" && !isBlank(item.value));
  if (text) return { row, column: text.column };
  const valued = candidates.find((item) => !isBlank(item.value));
  if (valued) return { row, column: valued.column };
  return { row, column: candidates[0].column };
}

/** 全部错误的标红格集合（key 为 `${row}:${col}`，与 quickImportPlugin 约定一致）。 */
export function buildErrorCells(
  errors: ImportError[],
  mapping: Mapping,
  sheet: AdaptedSheet | null,
): ReadonlySet<string> {
  const cells = new Set<string>();
  for (const error of errors) {
    const target = errorCellPosition(error, mapping, sheet);
    if (target) cells.add(`${target.row}:${target.column}`);
  }
  return cells;
}
