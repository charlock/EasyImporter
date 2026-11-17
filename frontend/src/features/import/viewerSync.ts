/**
 * 导入页 viewer 同步逻辑（纯函数，不依赖 Vue / DOM / viewer api）。
 *
 * 职责：把 viewer 里的原始文件坐标（0 基行列）与“映射后的行”互相翻译。
 * - expandMappedRows：按行展开映射，同时记录每条产出行的来源分组（拆行时
 *   校验错误要定位到具体分组的格子，只靠 row_no + db_column 区分不开）。
 * - resolveCellEdit / applyCellEditToRawRows：viewer 的 cell-change 写回
 *   “按表头路径索引的原始行记录”，再由页面整行重展开 + 重校验。
 * - collectErrorPositions：校验错误 → viewer 错误格集合（cellStyle 标红用，
 *   key 为 `${row}:${col}`，0 基）与抽屉错误清单（含定位坐标）。
 * - editableTargets：已映射列在数据行范围内的可编辑白名单（矩形区域）。
 *
 * 下标约定：viewer / 库模型一律 0 基；rowNo（Excel 行号）一律 1 基；
 * 叶子路径用 "\u0000" 连接，与 features/mapping/apply.ts 一致。
 */
import type { MergeRange } from "ooxml-excel-editor/core";

import type { AdaptedSheet } from "@/features/excel-viewer/modelAdapter";
import { applyMapping, type MappedRow } from "@/features/mapping/apply";
import type { CellError } from "@/features/rules/execute";
import type { Mapping } from "@/lib/types";

export const PATH_SEP = "\u0000";

export function pathKey(path: string[]): string {
  return path.join(PATH_SEP);
}

/** 一条映射产出行的来源：拆行时为产出它的分组下标；非拆行行恒为 null。 */
export interface RowSource {
  rowNo: number;
  groupIndex: number | null;
}

/**
 * 按行展开映射，同时给出每条产出行的来源分组。
 * 拆行时按分组逐个调 applyMapping（单分组映射一次只产出 0 或 1 行），
 * 拼接结果与整行调一次 applyMapping 完全一致（顺序与 skip_empty 语义相同），
 * 但能准确知道每行来自哪个分组；非拆行时与直接调用等价。
 */
export function expandMappedRows(
  row: Record<string, unknown>,
  mapping: Mapping,
  rowNo: number,
  constantOverrides: Record<string, string> = {},
): { rows: MappedRow[]; sources: RowSource[] } {
  const unpivot = mapping.unpivot;
  if (!unpivot) {
    const rows = applyMapping(row, mapping, rowNo, constantOverrides);
    return { rows, sources: rows.map(() => ({ rowNo, groupIndex: null })) };
  }
  const rows: MappedRow[] = [];
  const sources: RowSource[] = [];
  unpivot.groups.forEach((group, groupIndex) => {
    const produced = applyMapping(
      row,
      { ...mapping, unpivot: { ...unpivot, groups: [group] } },
      rowNo,
      constantOverrides,
    );
    for (const producedRow of produced) {
      rows.push(producedRow);
      sources.push({ rowNo, groupIndex });
    }
  });
  return { rows, sources };
}

/** viewer 单元格编辑的解析结果：被改动的叶子路径与受影响的目标列。 */
export interface CellEditTarget {
  /** 叶子路径（"\u0000" 连接），即原始行记录里的键。 */
  pathKey: string;
  /** 该叶子映射到的目标列（普通列 1 个；拆行度量列 1 个；未映射为空数组）。 */
  dbColumns: string[];
}

/**
 * viewer 的 0 基 (row, col) → 被改动的叶子。
 * row 只用于算 Excel 行号（调用方再按行号找原始行记录）；col 必须命中某叶子列，
 * 否则返回 null（表头外 / 未进表头树的列不参与映射）。
 */
export function resolveCellEdit(
  adapted: AdaptedSheet,
  mapping: Mapping,
  col: number,
): CellEditTarget | null {
  let foundKey: string | null = null;
  for (const [key, column] of adapted.leafColumns) {
    if (column === col) {
      foundKey = key;
      break;
    }
  }
  if (foundKey == null) return null;
  const dbColumns = new Set<string>();
  for (const column of mapping.columns) {
    if (pathKey(column.excel_path) === foundKey && column.db_column.trim() !== "") {
      dbColumns.add(column.db_column);
    }
  }
  const unpivot = mapping.unpivot;
  if (unpivot) {
    for (const group of unpivot.groups) {
      for (const measure of unpivot.measures) {
        if (pathKey([...group.match_prefix, measure.excel_leaf]) === foundKey) {
          if (measure.db_column.trim() !== "") dbColumns.add(measure.db_column);
        }
      }
    }
  }
  return { pathKey: foundKey, dbColumns: [...dbColumns] };
}

/** viewer 原始值 → 原始行记录里的值：只有 Date 在边界转 ISO 日期字符串（与 modelAdapter 一致）。 */
export function normalizeCellValue(value: unknown): unknown {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return value;
}

/**
 * 把一次单元格编辑写回原始行记录，返回新数组（不改原数组）。
 * excelRowNo 不在 rowNumbers 里时返回 null（例如表头行、空行被跳过的行）。
 */
export function applyCellEditToRawRows(
  rawRows: Record<string, unknown>[],
  rowNumbers: number[],
  excelRowNo: number,
  editPathKey: string,
  value: unknown,
): Record<string, unknown>[] | null {
  const index = rowNumbers.indexOf(excelRowNo);
  if (index === -1) return null;
  const next = rawRows.slice();
  next[index] = { ...next[index], [editPathKey]: normalizeCellValue(value) };
  return next;
}

/**
 * 校验错误 → viewer 格坐标（0 基行列）。
 * 普通列按 excel_path 找叶子列；拆行度量列按来源分组找
 * [...match_prefix, excel_leaf]；维度列与常量列没有对应的 Excel 格，返回 null。
 */
export function resolveErrorCell(
  adapted: AdaptedSheet,
  mapping: Mapping,
  source: RowSource,
  column: string,
): { row: number; column: number } | null {
  const row = source.rowNo - 1;
  for (const item of mapping.columns) {
    if (item.db_column === column) {
      const col = adapted.leafColumns.get(pathKey(item.excel_path));
      return col == null ? null : { row, column: col };
    }
  }
  const unpivot = mapping.unpivot;
  if (unpivot && source.groupIndex != null) {
    const group = unpivot.groups[source.groupIndex];
    if (group) {
      for (const measure of unpivot.measures) {
        if (measure.db_column === column) {
          const col = adapted.leafColumns.get(pathKey([...group.match_prefix, measure.excel_leaf]));
          return col == null ? null : { row, column: col };
        }
      }
    }
  }
  return null;
}

/**
 * 业务键重复类错误只有 row_no + 列名、没有映射行下标时用的回退定位：
 * 取第一个行号相同且能定位到格的映射行（普通列的业务键在各拆行组里是同一格）。
 */
export function resolveErrorCellByRow(
  adapted: AdaptedSheet,
  mapping: Mapping,
  sources: RowSource[],
  rowNo: number,
  column: string,
): { row: number; column: number } | null {
  for (const source of sources) {
    if (source.rowNo !== rowNo) continue;
    const pos = resolveErrorCell(adapted, mapping, source, column);
    if (pos) return pos;
  }
  return null;
}

/** 带映射行下标的校验错误（revalidate 逐行 validateRow 时直接得到）。 */
export interface IndexedError {
  index: number;
  error: CellError;
}

/** 抽屉错误清单的一项：含 viewer 定位坐标（0 基），无法定位到格时 col 为 null。 */
export interface PositionedError {
  rowNo: number;
  column: string;
  code: string;
  row: number;
  col: number | null;
}

/**
 * 由带下标的错误算出 viewer 错误格集合与抽屉清单。
 * index 为 -1 的错误（无法对应到某条映射行，如回退定位失败的重复键错误）
 * 只进清单、不进错误格集合。
 */
export function collectErrorPositions(
  adapted: AdaptedSheet,
  mapping: Mapping,
  sources: RowSource[],
  errors: IndexedError[],
): { cells: ReadonlySet<string>; items: PositionedError[] } {
  const cells = new Set<string>();
  const items: PositionedError[] = [];
  for (const { index, error } of errors) {
    const source = index >= 0 ? sources[index] : undefined;
    let pos: { row: number; column: number } | null = null;
    if (source) {
      pos = resolveErrorCell(adapted, mapping, source, error.column);
    } else {
      pos = resolveErrorCellByRow(adapted, mapping, sources, error.row_no, error.column);
    }
    if (pos) cells.add(`${pos.row}:${pos.column}`);
    items.push({
      rowNo: error.row_no,
      column: error.column,
      code: error.code,
      row: error.row_no - 1,
      col: pos ? pos.column : null,
    });
  }
  return { cells, items };
}

/**
 * 已映射的 Excel 列（普通列 + 拆行度量列）在数据行范围内的可编辑白名单。
 * 每列一个矩形区域（0 基闭区间）：top 为首个数据行，bottom 为表末行；
 * 表头行不在白名单内（改表头会破坏映射）；未映射的列不在白名单内
 * （改了也不会入库）。列为空时返回 []，即 viewer 全只读。
 */
export function editableTargets(
  mapping: Mapping,
  adapted: AdaptedSheet,
  firstDataRow0: number,
  rowCount: number,
): MergeRange[] {
  if (rowCount <= firstDataRow0) return [];
  const columns = new Set<number>();
  for (const item of mapping.columns) {
    const col = adapted.leafColumns.get(pathKey(item.excel_path));
    if (col != null) columns.add(col);
  }
  const unpivot = mapping.unpivot;
  if (unpivot) {
    for (const group of unpivot.groups) {
      for (const measure of unpivot.measures) {
        const col = adapted.leafColumns.get(pathKey([...group.match_prefix, measure.excel_leaf]));
        if (col != null) columns.add(col);
      }
    }
  }
  const bottom = rowCount - 1;
  return [...columns]
    .sort((a, b) => a - b)
    .map((col) => ({ top: firstDataRow0, left: col, bottom, right: col }));
}
