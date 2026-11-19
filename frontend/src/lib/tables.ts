import type { TableInfo } from "@/lib/types";

/** 目标表下拉的查询过滤：按 "schema.name" 或表名子串匹配，不区分大小写；
 * 空查询返回全部。供目标表下拉（含“自动生成目标表”置顶项）使用。 */
export function filterTargetTables(tables: TableInfo[], query: string): TableInfo[] {
  const q = query.trim().toLowerCase();
  if (!q) return tables;
  return tables.filter((table) =>
    `${table.schema ? `${table.schema}.` : ""}${table.name}`.toLowerCase().includes(q),
  );
}

/** 目标表下拉的稳定键：用 schema + 表名定位，避免过滤后下标错位。 */
export function tableKey(table: TableInfo): string {
  return `${table.schema}\u0000${table.name}`;
}
