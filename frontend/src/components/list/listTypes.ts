import type { Component } from "vue";

import type { ImportStatus } from "@/lib/types";

/**
 * 列表单元格的表达类型。
 *
 * 同一列只用一种表达：ListColumn 的 kind 与 cell 的返回值在类型层面一一对应
 *（见下面的 ListColumn 联合类型），cellMatchesKind 再在运行时复核；
 * 同一列不会出现两种渲染或两种交互。
 */
export type ListCellValue =
  | { type: "text"; text: string; sub?: string }
  | { type: "link"; to: string; label: string; sub?: string[] }
  | { type: "badge"; label: string; tone: BadgeTone }
  | { type: "count"; primary: string; secondary?: string; danger?: boolean }
  | { type: "meta"; primary: string; secondary?: string };

export type BadgeTone = "success" | "danger" | "warning" | "info" | "muted";

export type ListColumnKind = "link" | "badge" | "text" | "meta" | "count" | "actions";

/** 徽章底色：与 StatusBadge 同一套色板，单点维护。 */
export const badgeToneClass: Record<BadgeTone, string> = {
  success: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  danger: "border-destructive/30 bg-destructive/15 text-destructive",
  warning: "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-400",
  info: "border-sky-500/30 bg-sky-500/15 text-sky-700 dark:text-sky-400",
  muted: "border-transparent bg-secondary text-secondary-foreground",
};

/** 导入状态 → 徽章底色（StatusBadge 与列表状态列共用）。 */
export function importStatusTone(status: ImportStatus): BadgeTone {
  switch (status) {
    case "SUCCEEDED":
      return "success";
    case "FAILED":
      return "danger";
    case "UNKNOWN":
      return "warning";
    case "RUNNING":
    case "COMMITTING":
      return "info";
    default:
      return "muted";
  }
}

interface ListColumnBase {
  key: string;
  header: string;
  class?: string;
  headerClass?: string;
}

/**
 * 列定义：kind 决定唯一的单元格表达，cell 的返回值类型随 kind 而定。
 * "actions" 列没有单元格值，行操作由 ListShell 的 actions prop 提供。
 */
export type ListColumn<T> =
  | (ListColumnBase & { kind: "link"; cell: (row: T) => Extract<ListCellValue, { type: "link" }> })
  | (ListColumnBase & { kind: "badge"; cell: (row: T) => Extract<ListCellValue, { type: "badge" }> })
  | (ListColumnBase & { kind: "text"; cell: (row: T) => Extract<ListCellValue, { type: "text" }> })
  | (ListColumnBase & { kind: "meta"; cell: (row: T) => Extract<ListCellValue, { type: "meta" }> })
  | (ListColumnBase & { kind: "count"; cell: (row: T) => Extract<ListCellValue, { type: "count" }> })
  | (ListColumnBase & { kind: "actions" });

/** 行操作菜单项：同一操作列内所有行共用同一种菜单交互。 */
export interface ListAction {
  label: string;
  icon?: Component;
  danger?: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
}

/** 运行时复核：单元格值的表达类型与列定义一致（类型层已保证，这里防手写越界）。 */
export function cellMatchesKind(kind: ListColumnKind, value: ListCellValue): boolean {
  if (kind === "actions") return false;
  return value.type === kind;
}

/**
 * tasks 风格的分页页码：首尾各两页 + 当前页前后一页，其余折叠为 "…"。
 * 总页数 ≤ 7 时全部展开。
 */
export function pageNumbers(current: number, total: number): (number | "…")[] {
  if (total <= 0) return [];
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = new Set([1, 2, total - 1, total, current - 1, current, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) out.push("…");
    out.push(sorted[i]);
  }
  return out;
}

/** 客户端文本过滤：query 为空返回原数组；否则任一指定字段包含即命中（不区分大小写）。 */
export function applyTextFilter<T>(rows: T[], query: string, fields: (row: T) => string[]): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((row) => fields(row).some((field) => field.toLowerCase().includes(q)));
}
