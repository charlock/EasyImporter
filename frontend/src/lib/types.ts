/** 与后端 DTO 对齐的类型。 */

export type Role = "admin" | "importer";

export interface Me {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  workspace_ids: number[];
  csrf_token: string;
}

export interface User {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
}

export interface Workspace {
  id: number;
  name: string;
  description: string;
  member_count: number;
}

export type DbType = "postgres" | "mysql" | "dameng";

export interface Datasource {
  id: number;
  name: string;
  db_type: DbType;
  host: string;
  port: number;
  database: string;
  username: string;
  options: Record<string, unknown>;
}

export interface ColumnInfo {
  name: string;
  type: string;
  comment: string;
  nullable: boolean;
  default: string | null;
  is_primary_key: boolean;
}

export interface UniqueKey {
  name: string;
  columns: string[];
}

export interface TableSchema {
  schema: string;
  table_name: string;
  columns: ColumnInfo[];
  unique_keys: UniqueKey[];
  engine: string;
}

export interface TableInfo {
  schema: string;
  name: string;
}

export type Strategy = "APPEND" | "UPSERT" | "REPLACE_SCOPE";

export interface ColumnMapping {
  excel_path: string[];
  db_column: string;
}

export interface UnpivotGroup {
  dimension_value: string;
  match_prefix: string[];
}

export interface UnpivotMeasure {
  excel_leaf: string;
  db_column: string;
}

export interface Unpivot {
  dimension_column: string;
  groups: UnpivotGroup[];
  measures: UnpivotMeasure[];
  skip_empty_measures: boolean;
}

export interface ConstantMapping {
  db_column: string;
  value: string;
}

export interface Mapping {
  columns: ColumnMapping[];
  unpivot: Unpivot | null;
  constants: ConstantMapping[];
}

export interface RuleOverride {
  db_column: string;
  required?: boolean | null;
  enum?: string[] | null;
  pattern?: string | null;
  default?: string | null;
  max_length?: number | null;
}

export interface Template {
  id: number;
  workspace_id: number;
  name: string;
  description: string;
  current_version: number;
  is_archived: boolean;
  datasource_id: number | null;
  target_schema: string;
  target_table: string;
  sheet: string;
  header_start_row: number;
  header_row_count: number;
  strategy: Strategy;
  business_keys: string[];
  scope_columns: string[];
  mapping: Mapping;
  rule_overrides: RuleOverride[];
}

export interface Suggestion {
  excel_path: string[];
  db_column: string;
  score: number;
  reason: string;
}

export interface SynonymGroup {
  id: number;
  terms: string[];
}

export type ImportStatus =
  | "QUEUED" | "RUNNING" | "COMMITTING" | "SUCCEEDED" | "FAILED" | "CANCELLED" | "UNKNOWN";

export interface ImportTask {
  id: number;
  status: ImportStatus;
  template_id: number;
  template_version: number;
  operator: string;
  target_table: string;
  strategy: Strategy | "";
  row_count: number;
  processed: number;
  inserted: number;
  updated: number;
  deleted: number;
  counts_exact: boolean;
  error_count: number;
  failure_code: string;
  failure_message: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ImportLog {
  id: number;
  ts: string;
  level: string;
  code: string;
  params: Record<string, unknown>;
  message: string;
}

export interface ImportError {
  id: number;
  row_no: number;
  column: string;
  code: string;
  params: Record<string, unknown>;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export type RuleType = "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";

export interface ColumnRule {
  db_column: string;
  type: RuleType;
  precision: number | null;
  scale: number | null;
  required: boolean;
  default: string | null;
  max_length: number | null;
  enum: string[] | null;
  pattern: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  params?: Record<string, unknown>;
}
