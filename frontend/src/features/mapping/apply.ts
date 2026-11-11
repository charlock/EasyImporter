/** 字段映射与长表拆行。后端不重复展开映射，只复核前端提交的行（app/rules/engine.py）。 */

import type { Mapping } from "@/lib/types";

export interface MappedRow {
  row_no: number;
  values: Record<string, unknown>;
}

function lookup(row: Record<string, unknown>, path: string[]): unknown {
  return row[path.join("\u0000")];
}

function isEmpty(value: unknown): boolean {
  return value == null || (typeof value === "string" && value.trim() === "");
}

/** 把一行 Excel 数据按映射展开成一到多行目标表记录。 */
export function applyMapping(row: Record<string, unknown>, mapping: Mapping, rowNo: number): MappedRow[] {
  const base: Record<string, unknown> = {};
  for (const column of mapping.columns) base[column.db_column] = lookup(row, column.excel_path);
  for (const constant of mapping.constants) base[constant.db_column] = constant.value;

  const unpivot = mapping.unpivot;
  if (!unpivot) return [{ row_no: rowNo, values: base }];

  const produced: MappedRow[] = [];
  for (const group of unpivot.groups) {
    const values = { ...base, [unpivot.dimension_column]: group.dimension_value };
    let anyMeasure = false;
    for (const measure of unpivot.measures) {
      const value = lookup(row, [...group.match_prefix, measure.excel_leaf]);
      values[measure.db_column] = value;
      if (!isEmpty(value)) anyMeasure = true;
    }
    if (!unpivot.skip_empty_measures || anyMeasure) produced.push({ row_no: rowNo, values });
  }
  return produced;
}

/** 连续空行达到阈值即认为数据结束，丢弃其后的内容。 */
export function trimDataRows(rows: Record<string, unknown>[], emptyRunLimit = 10): Record<string, unknown>[] {
  let emptyRun = 0;
  for (let index = 0; index < rows.length; index += 1) {
    const blank = Object.values(rows[index]).every(isEmpty);
    emptyRun = blank ? emptyRun + 1 : 0;
    if (emptyRun >= emptyRunLimit) return rows.slice(0, index - emptyRunLimit + 1);
  }
  return rows;
}

/** 模板要求但文件里找不到的表头路径，对应后端的 TEMPLATE_HEADER_MISMATCH。 */
export function missingHeaders(mapping: Mapping, leafPaths: string[][]): string[][] {
  const present = new Set(leafPaths.map((path) => path.join("\u0000")));
  const required: string[][] = mapping.columns.map((column) => column.excel_path);
  if (mapping.unpivot) {
    for (const group of mapping.unpivot.groups) {
      for (const measure of mapping.unpivot.measures) required.push([...group.match_prefix, measure.excel_leaf]);
    }
  }
  const seen = new Set<string>();
  return required.filter((path) => {
    const key = path.join("\u0000");
    if (present.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
