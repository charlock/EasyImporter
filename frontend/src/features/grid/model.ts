/** 预览网格的数据模型：把映射结果和校验错误定位到单元格。 */

import type { CellError, DefaultApplied } from "@/features/rules/execute";
import type { ColumnRule } from "@/lib/types";

export interface GridColumn {
  key: string;
  label: string;
  rule: ColumnRule | null;
}

export interface GridCell {
  value: string;
  error: CellError | null;
  defaultApplied: DefaultApplied | null;
}

export interface GridRow {
  rowNo: number;
  cells: Record<string, GridCell>;
}

function display(value: unknown): string {
  if (value == null) return "";
  return String(value);
}

/** 由映射后的行和校验错误构造可渲染的网格。 */
export function buildGrid(
  rows: { row_no: number; values: Record<string, unknown> }[],
  columns: GridColumn[],
  errors: CellError[],
  defaults: DefaultApplied[],
): GridRow[] {
  const errorAt = new Map(errors.map((error) => [`${error.row_no}\u0000${error.column}`, error]));
  const defaultAt = new Map(defaults.map((item) => [`${item.row}\u0000${item.column}`, item]));
  return rows.map((row) => ({
    rowNo: row.row_no,
    cells: Object.fromEntries(
      columns.map((column) => {
        const key = `${row.row_no}\u0000${column.key}`;
        return [
          column.key,
          {
            value: display(row.values[column.key]),
            error: errorAt.get(key) ?? null,
            defaultApplied: defaultAt.get(key) ?? null,
          } satisfies GridCell,
        ];
      }),
    ),
  }));
}

/** 把用户编辑写回映射后的行，返回新数组，不改原对象。 */
export function applyEdit(
  rows: { row_no: number; values: Record<string, unknown> }[],
  rowNo: number,
  column: string,
  value: string,
): { row_no: number; values: Record<string, unknown> }[] {
  return rows.map((row) =>
    row.row_no === rowNo ? { ...row, values: { ...row.values, [column]: value } } : row,
  );
}

/** 统计仍未修复的错误数，用于提交按钮的启用判断。 */
export function errorCount(rows: GridRow[]): number {
  return rows.reduce(
    (total, row) => total + Object.values(row.cells).filter((cell) => cell.error).length,
    0,
  );
}
