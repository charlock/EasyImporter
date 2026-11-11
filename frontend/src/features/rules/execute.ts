/** 校验规则执行，与后端 app/rules/engine.py 共用 fixtures/rules/*.json。
 *
 * 结论必须一致：同样的输入得到同样的错误码和同样的转换结果。
 */

import type { ColumnInfo, ColumnRule, RuleOverride, RuleType } from "@/lib/types";

const DB_TYPE_RULES: [string, RuleType][] = [
  ["BOOL", "boolean"],
  ["INT", "integer"],
  ["BIGINT", "integer"],
  ["SMALLINT", "integer"],
  ["TINYINT", "integer"],
  ["NUMERIC", "decimal"],
  ["DECIMAL", "decimal"],
  ["NUMBER", "decimal"],
  ["FLOAT", "decimal"],
  ["DOUBLE", "decimal"],
  ["REAL", "decimal"],
  ["DATETIME", "datetime"],
  ["TIMESTAMP", "datetime"],
  ["DATE", "date"],
  ["CHAR", "string"],
  ["TEXT", "string"],
  ["CLOB", "string"],
  ["VARCHAR", "string"],
];

const BOOL_TRUE = new Set(["是", "y", "yes", "true", "1"]);
const BOOL_FALSE = new Set(["否", "n", "no", "false", "0"]);
const DATE_FORMATS = [
  /^(\d{4})-(\d{1,2})-(\d{1,2})$/,
  /^(\d{4})\/(\d{1,2})\/(\d{1,2})$/,
  /^(\d{4})\.(\d{1,2})\.(\d{1,2})$/,
  /^(\d{4})(\d{2})(\d{2})$/,
];
const DATETIME_FORMATS = [
  /^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{2}):(\d{2})$/,
  /^(\d{4})\/(\d{1,2})\/(\d{1,2}) (\d{1,2}):(\d{2}):(\d{2})$/,
];
const UNIT_SUFFIX = /[（(][^）)]*[）)]$/;
const PUNCT = /[\s\-_.,，。、/\\:：;；'"\`]+/g;

export interface CellError {
  row_no: number;
  column: string;
  code: string;
  params: Record<string, unknown>;
}

export interface DefaultApplied {
  row: number;
  column: string;
  value: string;
}

function ruleTypeOf(dbType: string): RuleType {
  const upper = dbType.toUpperCase();
  for (const [marker, ruleType] of DB_TYPE_RULES) {
    if (upper.includes(marker)) return ruleType;
  }
  return "string";
}

function varcharLength(dbType: string): number | null {
  const match = /\((\d+)/.exec(dbType);
  return match && dbType.toUpperCase().includes("CHAR") ? Number(match[1]) : null;
}

function decimalSpec(dbType: string): [number | null, number | null] {
  const match = /\((\d+)\s*,\s*(\d+)\)/.exec(dbType);
  return match ? [Number(match[1]), Number(match[2])] : [null, null];
}

/** 由目标表元数据推导规则，再套用只能收紧的覆盖项。 */
export function buildRules(columns: ColumnInfo[], overrides: RuleOverride[]): ColumnRule[] {
  const byName = new Map(overrides.map((override) => [override.db_column, override]));
  return columns.map((column) => {
    const [precision, scale] = decimalSpec(column.type);
    const rule: ColumnRule = {
      db_column: column.name,
      type: ruleTypeOf(column.type),
      precision,
      scale,
      required: !column.nullable && column.default === null,
      default: null,
      max_length: varcharLength(column.type),
      enum: null,
      pattern: null,
    };
    const override = byName.get(column.name);
    if (override) {
      if (override.required === true) rule.required = true;
      if (override.enum && override.enum.length) rule.enum = override.enum.map(String);
      if (override.pattern) rule.pattern = override.pattern;
      if (override.default != null) rule.default = String(override.default);
      if (override.max_length) {
        const limit = override.max_length;
        rule.max_length = Math.min(rule.max_length ?? limit, limit);
      }
    }
    return rule;
  });
}

function isBlank(value: unknown): boolean {
  return value == null || (typeof value === "string" && value.trim() === "");
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function parseDate(text: string): { date: string; time: string } | null {
  for (const format of DATETIME_FORMATS) {
    const match = format.exec(text);
    if (match) {
      const [, year, month, day, hour, minute, second] = match;
      return {
        date: `${year}-${pad(Number(month))}-${pad(Number(day))}`,
        time: `${pad(Number(hour))}:${minute}:${second}`,
      };
    }
  }
  for (const format of DATE_FORMATS) {
    const match = format.exec(text);
    if (match) {
      const [, year, month, day] = match;
      return { date: `${year}-${pad(Number(month))}-${pad(Number(day))}`, time: "00:00:00" };
    }
  }
  return null;
}

/** Excel 序列号按 1899-12-30 为原点换算。 */
function fromSerial(serial: number): string {
  const origin = Date.UTC(1899, 11, 30);
  const date = new Date(origin + serial * 86400000);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

function roundTo(value: number, scale: number): string {
  const factor = 10 ** scale;
  return (Math.round((value + Number.EPSILON) * factor) / factor).toFixed(scale);
}

function convert(rule: ColumnRule, raw: unknown): { value: unknown; error: string | null } {
  const text = typeof raw === "number" ? raw : String(raw).trim();
  if (rule.enum && !rule.enum.includes(String(text))) return { value: null, error: "ENUM_MISMATCH" };

  if (rule.type === "string") {
    const value = String(text);
    if (rule.max_length && value.length > rule.max_length) return { value: null, error: "TOO_LONG" };
    if (rule.pattern && !new RegExp(`^(?:${rule.pattern})$`).test(value)) {
      return { value: null, error: "PATTERN_MISMATCH" };
    }
    return { value, error: null };
  }
  if (rule.type === "integer") {
    const number = Number(String(text).replace(/,/g, ""));
    if (!Number.isFinite(number) || !Number.isInteger(number)) return { value: null, error: "TYPE_MISMATCH" };
    return { value: number, error: null };
  }
  if (rule.type === "decimal") {
    const number = Number(String(text).replace(/,/g, "").replace("%", ""));
    if (!Number.isFinite(number)) return { value: null, error: "TYPE_MISMATCH" };
    return { value: rule.scale != null ? roundTo(number, rule.scale) : String(number), error: null };
  }
  if (rule.type === "boolean") {
    const token = String(text).trim().toLowerCase();
    if (BOOL_TRUE.has(token)) return { value: true, error: null };
    if (BOOL_FALSE.has(token)) return { value: false, error: null };
    return { value: null, error: "TYPE_MISMATCH" };
  }
  if (rule.type === "date" || rule.type === "datetime") {
    if (typeof raw === "number") {
      const date = fromSerial(raw);
      return { value: rule.type === "date" ? date : `${date}T00:00:00`, error: null };
    }
    const parsed = parseDate(String(text));
    if (!parsed) return { value: null, error: "TYPE_MISMATCH" };
    return { value: rule.type === "date" ? parsed.date : `${parsed.date}T${parsed.time}`, error: null };
  }
  return { value: String(text), error: null };
}

export interface RowResult {
  cleaned: Record<string, unknown>;
  errors: CellError[];
  defaults: DefaultApplied[];
}

/** 校验并转换一行。空值命中默认值时不报错，记入 defaults。 */
export function validateRow(rules: ColumnRule[], row: Record<string, unknown>, rowNo: number): RowResult {
  const cleaned: Record<string, unknown> = {};
  const errors: CellError[] = [];
  const defaults: DefaultApplied[] = [];
  for (const rule of rules) {
    const raw = row[rule.db_column];
    if (isBlank(raw)) {
      if (rule.default != null) {
        const { value, error } = convert(rule, rule.default);
        if (error) errors.push({ row_no: rowNo, column: rule.db_column, code: error, params: {} });
        else {
          cleaned[rule.db_column] = value;
          defaults.push({ row: rowNo, column: rule.db_column, value: rule.default });
        }
      } else if (rule.required) {
        errors.push({ row_no: rowNo, column: rule.db_column, code: "REQUIRED", params: {} });
      } else {
        cleaned[rule.db_column] = null;
      }
      continue;
    }
    const { value, error } = convert(rule, raw);
    if (error) errors.push({ row_no: rowNo, column: rule.db_column, code: error, params: {} });
    else cleaned[rule.db_column] = value;
  }
  return { cleaned, errors, defaults };
}

/** 业务键在本次数据内不能重复，重复的每一行都标出。 */
export function findDuplicateKeys(rows: Record<string, unknown>[], businessKeys: string[]): CellError[] {
  if (!businessKeys.length) return [];
  const seen = new Map<string, number>();
  const duplicates = new Set<number>();
  rows.forEach((row, index) => {
    const parts = businessKeys.map((column) => row[column]);
    if (parts.some((part) => part == null || part === "")) return;
    const key = JSON.stringify(parts);
    const first = seen.get(key);
    if (first !== undefined) {
      duplicates.add(first);
      duplicates.add(index);
    } else {
      seen.set(key, index);
    }
  });
  return [...duplicates]
    .sort((a, b) => a - b)
    .map((index) => ({
      row_no: Number(rows[index]._row ?? index + 1),
      column: businessKeys[0],
      code: "DUPLICATE_KEY_IN_FILE",
      params: { columns: businessKeys },
    }));
}

/** 自动匹配用的归一化：去空白标点、全角转半角、英文小写、去单位后缀。 */
export function normalizeName(text: string): string {
  const half = [...text]
    .map((char) => {
      const code = char.charCodeAt(0);
      return code >= 0xff01 && code <= 0xff5e ? String.fromCharCode(code - 0xfee0) : char;
    })
    .join("")
    .replaceAll("　", " ");
  return half.trim().replace(UNIT_SUFFIX, "").replace(PUNCT, "").toLowerCase();
}
