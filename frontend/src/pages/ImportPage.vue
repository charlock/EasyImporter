<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import {
  Ellipsis,
  FileSpreadsheet,
  LocateFixed,
  PanelRight,
  Redo2,
  Search,
  Undo2,
  Zap,
} from "@lucide/vue";
import type { CellChangePayload, ViewerApi } from "ooxml-excel-editor/core";

import { api } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import DockBar from "@/components/layout/DockBar.vue";
import DrawerSection from "@/components/layout/DrawerSection.vue";
import PageDrawer from "@/components/layout/PageDrawer.vue";
import MappingTable from "@/components/template/MappingTable.vue";
import { gzipJsonl } from "@/features/excel/gzip";
import ExcelViewerHost from "@/features/excel-viewer/ExcelViewerHost.vue";
import {
  modelSheetIndex,
  modelToParsedSheet,
  type AdaptedSheet,
} from "@/features/excel-viewer/modelAdapter";
import { createQuickImportPlugin } from "@/features/excel-viewer/quickImportPlugin";
import {
  useExcelViewer,
  type SelectionRange,
} from "@/features/excel-viewer/useExcelViewer";
import {
  applyCellEditToRawRows,
  collectErrorPositions,
  editableTargets,
  expandMappedRows,
  resyncRowsFromModel,
  resolveCellEdit,
  resolveErrorCell,
  type IndexedError,
  type PositionedError,
  type RowSource,
} from "@/features/import/viewerSync";
import { downloadBlob, exportMappedXlsx, stripExtension } from "@/features/import/exportMapped";
import { missingHeaders, trimDataRows, type MappedRow } from "@/features/mapping/apply";
import { findDuplicateKeys, validateRow, type CellError } from "@/features/rules/execute";
import { pathLabel } from "@/features/header/tree";
import { codeText, errorMessage } from "@/lib/errors";
import type { ColumnRule, Template } from "@/lib/types";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const router = useRouter();

const templates = ref<Template[]>([]);
const templateId = ref<number | null>(null);
const template = ref<Template | null>(null);
const rules = ref<ColumnRule[]>([]);
const sourceFile = ref<File | null>(null);
/** 原始行记录（按表头路径索引，viewer 编辑的唯一事实来源）与对齐的 Excel 行号。 */
const rawRows = ref<Record<string, unknown>[]>([]);
const rawRowNumbers = ref<number[]>([]);
const mapped = ref<MappedRow[]>([]);
/** 与 mapped 一一对齐的来源（拆行时记录产出分组，供错误定位用）。 */
const mappedSources = ref<RowSource[]>([]);
const cleaned = ref<Record<string, unknown>[]>([]);
const submitting = ref(false);
const error = ref("");
const hiddenRows = ref(0);
const scopeConfirm = ref<{ estimated: number; scopes: number; resolve: (ok: boolean) => void } | null>(null);
const drawerOpen = ref(false);
/** 模板指定的工作表在当前文件里的下标；文件与模板对上后才有效。 */
const templateSheetIndex = ref(-1);
const adapted = ref<AdaptedSheet | null>(null);
/** 文件已通过表头校验，viewer 编辑才允许写回映射；表头缺失 / Sheet 不存在时为 false。 */
const fileReady = ref(false);
/** 带映射行下标的校验错误（逐行 validateRow 直接得到；重复键错误按行号回填下标）。 */
const indexedErrors = ref<IndexedError[]>([]);
/** cellStyle 标红用的错误格集合（key 为 `${row}:${col}`，0 基）。 */
const errorCells = ref<ReadonlySet<string>>(new Set());
const canUndo = ref(false);
const canRedo = ref(false);

/** viewer 单元格编辑的待处理队列（cell-change 批量粘贴时逐格发出，防抖后统一写回）。 */
const pendingEdits: { rowNo: number; pathKey: string; value: unknown }[] = [];
let editTimer: ReturnType<typeof setTimeout> | undefined;

/* ---------- viewer ---------- */
const viewer = useExcelViewer();

/** 当前活动表是否为模板指定的表：只有在该表上，错误标红与单元格编辑才生效。 */
const onTemplateSheet = computed(
  () => templateSheetIndex.value >= 0 && viewer.activeSheetIndex.value === templateSheetIndex.value,
);
/** viewer 是否可编辑：文件通过校验，且当前在模板指定的表上（切到其他表只看不改）。 */
const viewerEditable = computed(() => fileReady.value && onTemplateSheet.value);

/** plugins 用稳定引用（setup 内只建一次，禁止模板内联数组；见 ExcelViewerHost 注释）。 */
const plugins = [
  createQuickImportPlugin({
    onSelectionChange: onSelection,
    getErrorCells: () => errorCells.value,
    getDimension: () => {
      const model = viewer.workbook.value;
      const sheet = model?.sheets[viewer.activeSheetIndex.value];
      return sheet ? sheet.dimension : null;
    },
    onViewerReady: (api) => viewer.setViewerApi(api),
  }),
];

/** 抽屉错误清单（前 20 条，含 viewer 定位坐标；无法定位到格时 col 为 null）。 */
const errorItems = computed<PositionedError[]>(() => {
  if (!adapted.value || !template.value) return [];
  return collectErrorPositions(
    adapted.value,
    template.value.mapping,
    mappedSources.value,
    indexedErrors.value,
  ).items.slice(0, 20);
});

const problems = computed(() => indexedErrors.value.length);

/** 选中格正好是错误格时，overlay 浮出错误说明（库没有悬停事件，用选区代替悬停）。 */
const selectedError = computed(() => {
  const sel = viewer.selection.value;
  if (!sel || !onTemplateSheet.value) return null;
  if (!errorCells.value.has(`${sel.active.row}:${sel.active.col}`)) return null;
  const item = errorItems.value.find(
    (entry) => entry.row === sel.active.row && entry.col === sel.active.col,
  );
  if (!item) return null;
  return { row: item.row, col: item.col!, message: codeText(item.code) };
});

/** overlay 提示的位置：slotProps.rectOf 给出格子在渲染区的矩形；tick 变化时重算。 */
function errorTooltipStyle(slotProps: {
  rectOf: (row: number, col: number) => { x: number; y: number; w: number; h: number } | null;
  tick: number;
}): Record<string, string> | null {
  const target = selectedError.value;
  if (!target) return null;
  void slotProps.tick;
  const rect = slotProps.rectOf(target.row, target.col);
  if (!rect) return null;
  return { left: `${rect.x}px`, top: `${rect.y + rect.h + 4}px` };
}

// shadcn Select 只认字符串，模板 id 在此做 string ⇄ number 转换。
const templateIdStr = computed({
  get: () => (templateId.value == null ? "" : String(templateId.value)),
  set: (value: string) => {
    templateId.value = value === "" ? null : Number(value);
  },
});

/** 模板里勾了“导入时输入”的常量列：导入时必须逐文件填值（模板里的 value 仅作默认值）。 */
const requiredConstants = computed(
  () =>
    template.value?.mapping.constants.filter(
      (constant) => constant.require_input === true && constant.db_column.trim() !== "",
    ) ?? [],
);
/** 各必填常量的本次填值，键为目标列名；切换模板时用模板默认值重填。 */
const constantInputs = ref<Record<string, string>>({});
const constantsComplete = computed(() =>
  requiredConstants.value.every((constant) => (constantInputs.value[constant.db_column] ?? "").trim() !== ""),
);
const canSubmit = computed(
  () =>
    mapped.value.length > 0 &&
    problems.value === 0 &&
    constantsComplete.value &&
    !viewer.parsing.value &&
    !submitting.value,
);

/** 本次填的常量值（按目标列），重展开映射行时一并写进产出行。 */
function currentConstantOverrides(): Record<string, string> {
  return Object.fromEntries(
    requiredConstants.value.map((constant) => [constant.db_column, constantInputs.value[constant.db_column] ?? ""]),
  );
}

/** 由原始行记录整行重展开映射（viewer 编辑与常量填写后都走这里，保证 mapped 与来源对齐）。 */
function rebuildMapped(): void {
  const current = template.value;
  if (!current) {
    mapped.value = [];
    mappedSources.value = [];
    return;
  }
  const overrides = currentConstantOverrides();
  const rows: MappedRow[] = [];
  const sources: RowSource[] = [];
  rawRows.value.forEach((row, index) => {
    const expanded = expandMappedRows(row, current.mapping, rawRowNumbers.value[index] ?? index + 1, overrides);
    rows.push(...expanded.rows);
    sources.push(...expanded.sources);
  });
  mapped.value = rows;
  mappedSources.value = sources;
}

/** 把本次填的常量值写进已映射的行，再重新校验；输入框失焦/回车时调用。 */
function applyConstantOverrides(): void {
  if (!requiredConstants.value.length || !mapped.value.length) return;
  rebuildMapped();
  revalidate();
}

/** 抽屉“映射”section 的只读行：当前模板的映射，分数无数据（表内显示“—”）。 */
const importMappingRows = computed(() =>
  (template.value?.mapping.columns ?? []).map((column, index) => ({
    key: column.excel_path.join("\u0000"),
    index,
    excelLabel: pathLabel(column.excel_path),
    dbColumn: column.db_column,
    score: null,
  })),
);

/** 映射条 chips：Excel 列 → 目标字段（viewer 上方，DOM 横向条）。 */
const mappingChips = computed(() =>
  (template.value?.mapping.columns ?? []).map((column) => ({
    key: column.excel_path.join("\u0000"),
    excelLabel: pathLabel(column.excel_path),
    dbColumn: column.db_column,
  })),
);

/** 导出映射数据用的目标列（普通列 + 常量列 + 拆行维度/度量列，去重、去空）。 */
const dbColumns = computed(() => {
  const mapping = template.value?.mapping;
  if (!mapping) return [];
  const keys = [
    ...mapping.columns.map((column) => column.db_column),
    ...mapping.constants.map((constant) => constant.db_column),
    ...(mapping.unpivot
      ? [mapping.unpivot.dimension_column, ...mapping.unpivot.measures.map((item) => item.db_column)]
      : []),
  ];
  return [...new Set(keys)].filter((key) => key.trim() !== "");
});

/** 由带下标的错误重算错误格集合；不在模板表上时集合置空，避免标红错表。 */
function refreshErrorCells(): void {
  if (!adapted.value || !template.value || !onTemplateSheet.value) {
    errorCells.value = new Set();
    return;
  }
  errorCells.value = collectErrorPositions(
    adapted.value,
    template.value.mapping,
    mappedSources.value,
    indexedErrors.value,
  ).cells;
}

function refreshUndoRedo(): void {
  // 库先发事件、后把逆操作入栈：事件处理里同步读 canUndo() 会读到入栈前的旧值，
  // 且之后无事件再刷新，菜单就一直显示禁用；推迟到微任务，等入栈完成后再读。
  queueMicrotask(() => {
    try {
      canUndo.value = viewer.viewerApi.value?.canUndo() ?? false;
      canRedo.value = viewer.viewerApi.value?.canRedo() ?? false;
    } catch {
      canUndo.value = false;
      canRedo.value = false;
    }
  });
}

function revalidate(): void {
  const indexed: IndexedError[] = [];
  cleaned.value = mapped.value.map((row, index) => {
    const result = validateRow(rules.value, row.values, row.row_no);
    for (const err of result.errors) indexed.push({ index, error: err });
    return { ...result.cleaned, _row: row.row_no };
  });
  for (const err of findDuplicateKeys(cleaned.value, template.value?.business_keys ?? [])) {
    indexed.push({ index: resolveDuplicateIndex(err), error: err });
  }
  indexedErrors.value = indexed;
  refreshErrorCells();
}

/** 重复键错误只有行号与列名：取同行第一个能定位到格的映射行下标（普通列业务键在各拆行组里是同一格）。 */
function resolveDuplicateIndex(err: CellError): number {
  const current = template.value;
  if (!current || !adapted.value) return -1;
  for (let i = 0; i < mapped.value.length; i += 1) {
    if (mapped.value[i]!.row_no !== err.row_no) continue;
    if (resolveErrorCell(adapted.value, current.mapping, mappedSources.value[i]!, err.column)) return i;
  }
  return mapped.value.findIndex((row) => row.row_no === err.row_no);
}

function resetData(): void {
  pendingEdits.length = 0;
  if (editTimer !== undefined) {
    clearTimeout(editTimer);
    editTimer = undefined;
  }
  rawRows.value = [];
  rawRowNumbers.value = [];
  mapped.value = [];
  mappedSources.value = [];
  cleaned.value = [];
  indexedErrors.value = [];
  errorCells.value = new Set();
  hiddenRows.value = 0;
  adapted.value = null;
  templateSheetIndex.value = -1;
  fileReady.value = false;
  canUndo.value = false;
  canRedo.value = false;
  viewer.workbook.value = null;
  viewer.sourceBuffer.value = null;
  viewer.selection.value = null;
}

watch(
  () => props.workspaceId,
  async (id) => {
    try {
      templates.value = id == null ? [] : await api.get<Template[]>(`/workspaces/${id}/templates`);
      templateId.value = templates.value[0]?.id ?? null;
    } catch (caught) {
      error.value = errorMessage(caught);
    }
  },
  { immediate: true },
);

watch(templateId, async (id) => {
  resetData();
  template.value = null;
  constantInputs.value = {};
  if (id == null) return;
  try {
    template.value = await api.get<Template>(`/workspaces/${props.workspaceId}/templates/${id}`);
    rules.value = await api.get<ColumnRule[]>(`/workspaces/${props.workspaceId}/templates/${id}/rules`);
    constantInputs.value = Object.fromEntries(
      (template.value.mapping.constants ?? [])
        .filter((constant) => constant.require_input === true)
        .map((constant) => [constant.db_column, constant.value ?? ""]),
    );
  } catch (caught) {
    error.value = errorMessage(caught);
  }
});

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !template.value) return;
  resetData();
  sourceFile.value = file;
  error.value = "";
  try {
    const current = template.value;
    const model = await viewer.loadFile(file);
    // 指定的 Sheet 不存在即导入失败，不静默回退到第一张表。
    const sheetIndex = modelSheetIndex(model, current.sheet);
    if (sheetIndex < 0) {
      error.value = t("import.sheetMissing", {
        sheet: current.sheet,
        sheets: model.sheets.map((sheet) => sheet.name).join("、"),
      });
      return;
    }
    templateSheetIndex.value = sheetIndex;
    viewer.selectSheet(sheetIndex);
    const adaptedSheet = modelToParsedSheet(
      model,
      sheetIndex,
      current.header_start_row - 1,
      current.header_row_count,
    );
    adapted.value = adaptedSheet;
    const missing = missingHeaders(current.mapping, adaptedSheet.header.leaves.map((leaf) => leaf.path));
    if (missing.length) {
      error.value = `${codeText("TEMPLATE_HEADER_MISMATCH")}。${t("import.missingHeaders", {
        list: missing.map(pathLabel).join("、"),
      })}`;
      return;
    }
    hiddenRows.value = adaptedSheet.hiddenRows;
    const trimmed = trimDataRows(adaptedSheet.rows);
    rawRows.value = trimmed;
    rawRowNumbers.value = adaptedSheet.rowNumbers.slice(0, trimmed.length);
    fileReady.value = true;
    rebuildMapped();
    revalidate();
    applyEditableTargets();
    refreshUndoRedo();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

/** 已映射列在数据行范围内的可编辑白名单（表头行与未映射列禁改，命中发 permission-denied）。 */
function applyEditableTargets(): void {
  const api = viewer.viewerApi.value;
  const current = template.value;
  const sheet = adapted.value;
  if (!api || !current || !sheet) return;
  const dimension = viewer.workbook.value?.sheets[templateSheetIndex.value]?.dimension;
  if (!dimension) return;
  const firstDataRow0 = current.header_start_row - 1 + current.header_row_count;
  api.setEditableTargets(editableTargets(current.mapping, sheet, firstDataRow0, dimension.rows));
}

function onSelection(payload: { range: SelectionRange; active: { row: number; col: number } }): void {
  viewer.onSelectionChange(payload);
}

function onViewerReady(api: ViewerApi): void {
  viewer.setViewerApi(api);
  viewer.selectSheet(viewer.activeSheetIndex.value);
  applyEditableTargets();
  refreshUndoRedo();
}

function onViewerError(message: string): void {
  error.value = message;
}

function onSheetChange(payload: { index: number; name: string }): void {
  viewer.activeSheetIndex.value = payload.index;
  // 切到其他表只看不改：错误标红随之清空，切回模板表时恢复。
  refreshErrorCells();
}

/**
 * viewer 单元格改动（事后通知；批量粘贴逐格发出）：先写回原始行记录，
 * 防抖 150ms 后统一重展开 + 重校验，避免每格都重算一次。
 */
function onCellChange(payload: CellChangePayload): void {
  const current = template.value;
  const sheet = adapted.value;
  if (!current || !sheet || !fileReady.value) return;
  if (!onTemplateSheet.value) return;
  const target = resolveCellEdit(sheet, current.mapping, payload.after.col);
  if (!target || target.dbColumns.length === 0) return;
  pendingEdits.push({ rowNo: payload.after.row + 1, pathKey: target.pathKey, value: payload.after.raw });
  refreshUndoRedo();
  if (editTimer !== undefined) clearTimeout(editTimer);
  editTimer = setTimeout(flushCellEdits, 150);
}

function flushCellEdits(): void {
  editTimer = undefined;
  if (!pendingEdits.length || !fileReady.value) {
    pendingEdits.length = 0;
    return;
  }
  let next = rawRows.value;
  for (const edit of pendingEdits) {
    const updated = applyCellEditToRawRows(next, rawRowNumbers.value, edit.rowNo, edit.pathKey, edit.value);
    if (updated) next = updated;
  }
  pendingEdits.length = 0;
  rawRows.value = next;
  rebuildMapped();
  revalidate();
}

/**
 * viewer 行列结构变更（插/删行列及其撤销/重做；op 为 'restore' 时是结构撤销的重放）：
 * 结构只改 viewer 内部模型，rawRows 不会自动跟上——必须从实时模型重取数据、
 * 重建映射并重校验，否则删掉的总计行会一直留在错误列表与提交数据里。
 * 单元格编辑的待写回队列直接丢弃：模型里已有这些值，重解析会一并取回。
 */
function onStructChange(): void {
  const current = template.value;
  const sheet = adapted.value;
  if (!current || !sheet || !onTemplateSheet.value) return;
  pendingEdits.length = 0;
  if (editTimer !== undefined) {
    clearTimeout(editTimer);
    editTimer = undefined;
  }
  const model = viewer.viewerApi.value?.getWorkbook() ?? viewer.workbook.value;
  if (!model) return;
  const next = resyncRowsFromModel(
    model,
    templateSheetIndex.value,
    current.header_start_row - 1,
    current.header_row_count,
  );
  adapted.value = next.adapted;
  const missing = missingHeaders(current.mapping, next.adapted.header.leaves.map((leaf) => leaf.path));
  if (missing.length) {
    // 删掉已映射列：文件不再符合模板定义，与上传时一致，报错并停用编辑。
    error.value = `${codeText("TEMPLATE_HEADER_MISMATCH")}。${t("import.missingHeaders", {
      list: missing.map(pathLabel).join("、"),
    })}`;
    fileReady.value = false;
    mapped.value = [];
    mappedSources.value = [];
    cleaned.value = [];
    indexedErrors.value = [];
    errorCells.value = new Set();
    return;
  }
  // 结构撤销把表头恢复回来时，清掉之前的表头缺失报错。
  if (!fileReady.value) error.value = "";
  rawRows.value = next.rawRows;
  rawRowNumbers.value = next.rowNumbers;
  hiddenRows.value = next.hiddenRows;
  fileReady.value = true;
  rebuildMapped();
  revalidate();
  applyEditableTargets();
  refreshUndoRedo();
}

/** 抽屉点「定位」：切回模板表（如在看其他表），滚动并选中对应格。 */
function locateError(item: PositionedError): void {
  if (item.col == null || templateSheetIndex.value < 0) return;
  if (!onTemplateSheet.value) viewer.selectSheet(templateSheetIndex.value);
  viewer.scrollToCell(item.row, item.col, { select: true });
}

function openFind(): void {
  viewer.viewerApi.value?.openFindReplaceDialog("find");
}

function undoEdit(): void {
  viewer.undo();
  refreshUndoRedo();
}

function redoEdit(): void {
  viewer.redo();
  refreshUndoRedo();
}

async function exportMappedFile(): Promise<void> {
  try {
    const blob = await exportMappedXlsx(dbColumns.value, mapped.value, indexedErrors.value);
    downloadBlob(
      blob,
      `${sourceFile.value ? stripExtension(sourceFile.value.name) : "import"}-mapped.xlsx`,
    );
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function exportOriginalFile(): Promise<void> {
  try {
    const blob = await viewer.exportXlsx();
    downloadBlob(
      blob,
      sourceFile.value ? `${stripExtension(sourceFile.value.name)}-edited.xlsx` : "edited.xlsx",
    );
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function exportCsvFile(): Promise<void> {
  try {
    const blob = await viewer.exportCsv();
    downloadBlob(blob, sourceFile.value ? `${stripExtension(sourceFile.value.name)}.csv` : "export.csv");
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

function askScope(estimated: number, scopes: number): Promise<boolean> {
  return new Promise((resolve) => {
    scopeConfirm.value = { estimated, scopes, resolve };
  });
}

function closeScope(ok: boolean): void {
  // 已结算过（例如确认点击已先结算）时不再重复结算。
  if (scopeConfirm.value === null) return;
  scopeConfirm.value.resolve(ok);
  scopeConfirm.value = null;
}

/**
 * 对话框 open 变化：Radix 关闭对话框（Action/Cancel 点击、Escape）时会先触发
 * update:open、再触发按钮自身的 click；若在这里立即以 false 结算，确认点击的
 * true 会被吞掉（promise 只能结算一次）。因此把 false 结算推迟到微任务：
 * 同一次点击里的 click 处理器先跑完（以 true 结算），微任务里守卫已返回；
 * Escape 关闭时没有点击结算，微任务再以 false 结算，调用方不会挂起。
 */
function onScopeOpenChange(open: boolean): void {
  if (open) return;
  queueMicrotask(() => closeScope(false));
}

/** REPLACE_SCOPE 先问后端将删除多少行，让用户知道代价再确认。 */
async function confirmScope(current: Template): Promise<boolean> {
  const unique = new Map<string, Record<string, unknown>>();
  for (const row of cleaned.value) {
    const scope = Object.fromEntries(current.scope_columns.map((column) => [column, row[column] ?? null]));
    unique.set(JSON.stringify(scope), scope);
  }
  const preview = await api.post<{ estimated_delete: number; scope_count: number }>(
    `/workspaces/${props.workspaceId}/imports/preview-scope`,
    { template_id: current.id, template_version: current.current_version, scopes: [...unique.values()] },
  );
  return askScope(preview.estimated_delete, preview.scope_count);
}

async function submit(): Promise<void> {
  const current = template.value;
  if (!current || !canSubmit.value) return;
  error.value = "";
  submitting.value = true;
  try {
    // 提交前先把未落盘的单元格编辑刷掉（150ms 防抖窗口内直接点提交会丢改动），
    // 再覆盖一次常量值：用户可能填完值后未失焦就直接点提交。
    flushCellEdits();
    applyConstantOverrides();
    if (current.strategy === "REPLACE_SCOPE" && !(await confirmScope(current))) return;
    const payload = mapped.value.map((row) => ({ ...row.values, _row: row.row_no }));
    const form = new FormData();
    form.append("meta", JSON.stringify({
      template_id: current.id,
      template_version: current.current_version,
      row_count: payload.length,
    }));
    form.append("file", sourceFile.value as File);
    form.append("rows", await gzipJsonl(payload), "rows.jsonl.gz");
    const task = await api.upload<{ id: number }>(`/workspaces/${props.workspaceId}/imports`, form);
    await router.push(`/imports/${task.id}`);
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="space-y-4">
    <!-- 顶部停靠栏：模板、文件、计数与操作放一行 -->
    <DockBar>
      <Select v-model="templateIdStr">
        <SelectTrigger class="h-8 w-48 shrink-0">
          <SelectValue :placeholder="t('import.pickTemplate')" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="item in templates" :key="item.id" :value="String(item.id)">
            {{ item.name }}
          </SelectItem>
        </SelectContent>
      </Select>
      <!-- 文件名过长时截断，避免把停靠栏撑到换行（1440px 下停靠栏须保持单行 53px）；悬停看全名。 -->
      <span
        class="flex min-w-0 max-w-40 shrink-0 items-center gap-1 truncate text-sm text-muted-foreground"
        :title="sourceFile?.name"
      >
        <FileSpreadsheet class="size-4 shrink-0" />
        {{ sourceFile?.name ?? t("import.noFile") }}
      </span>
      <span v-if="mapped.length" class="shrink-0 text-sm">
        {{ mapped.length }} {{ t("import.rows") }} · {{ problems }} {{ t("import.errors") }}
        <!-- 辅助提示只在够宽时显示：1440px 下停靠栏须保持单行 53px，提示会把计数撑到换行。 -->
        <span class="hidden text-muted-foreground min-[1500px]:inline">· {{ t("import.editHint") }}</span>
      </span>
      <span v-if="hiddenRows" class="shrink-0 text-sm text-muted-foreground">
        {{ t("import.hiddenRows", { n: hiddenRows }) }}
      </span>
      <div class="min-w-2 flex-1" />
      <Button variant="outline" size="sm" class="shrink-0" as-child>
        <label class="cursor-pointer">
          <input type="file" accept=".xlsx" class="hidden" :disabled="viewer.parsing.value || !template" @change="onFile" />
          {{ t("import.selectFile") }}
        </label>
      </Button>
      <Button variant="outline" size="sm" class="shrink-0" :disabled="!template" @click="drawerOpen = true">
        <Zap class="mr-1 size-4" />{{ t("template.quickImport") }}
      </Button>
      <!-- 查找/撤销/重做与导出收进「更多」：这几个按钮放外面会把停靠栏撑到两行
        （1440px 下 93px）。实测复刻：只收查找/撤销/重做仍不够，导出也一并收进才单行。 -->
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="icon" class="h-8 w-8 shrink-0" :title="t('import.more')">
            <Ellipsis class="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem :disabled="!viewer.workbook.value" @click="openFind">
            <Search class="mr-1 size-4" />{{ t("import.find") }}
          </DropdownMenuItem>
          <DropdownMenuItem :disabled="!canUndo" @click="undoEdit">
            <Undo2 class="mr-1 size-4" />{{ t("import.undo") }}
          </DropdownMenuItem>
          <DropdownMenuItem :disabled="!canRedo" @click="redoEdit">
            <Redo2 class="mr-1 size-4" />{{ t("import.redo") }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem :disabled="!mapped.length" @click="exportMappedFile">
            {{ t("import.exportMapped") }}
          </DropdownMenuItem>
          <DropdownMenuItem @click="exportOriginalFile">{{ t("import.exportOriginal") }}</DropdownMenuItem>
          <DropdownMenuItem @click="exportCsvFile">{{ t("import.exportCsv") }}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button variant="outline" size="sm" class="shrink-0" @click="drawerOpen = true">
        <PanelRight />{{ t("import.details") }}
      </Button>
      <Button
        size="sm"
        class="shrink-0"
        :disabled="!canSubmit"
        :title="problems > 0 && mapped.length > 0 ? t('import.submitDisabledErrors') : undefined"
        @click="submit"
      >
        {{ t("import.submit") }}
      </Button>
    </DockBar>

    <Alert v-if="error" variant="destructive" class="mt-4">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <!-- 映射条：Excel 列 → 目标字段（viewer 上方 DOM 横向条）；右侧为策略与业务键 -->
    <div
      v-if="viewer.workbook.value"
      class="flex items-center gap-1.5 overflow-x-auto rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
    >
      <span class="shrink-0 font-medium text-foreground">{{ t("template.mapping") }}</span>
      <span
        v-for="chip in mappingChips"
        :key="chip.key"
        class="shrink-0 whitespace-nowrap rounded-full border bg-background px-2.5 py-0.5 text-foreground"
      >
        {{ chip.excelLabel }} <span class="text-muted-foreground">→</span> {{ chip.dbColumn || "—" }}
      </span>
      <span class="ml-auto shrink-0 pl-3">
        {{ t("template.strategy") }}：{{ template ? t(`strategy.${template.strategy}`) : "—" }} ·
        {{ t("template.businessKeys") }}：{{ template?.business_keys.join("、") || "—" }}
      </span>
    </div>

    <!-- 主区域：原始文件由 ExcelViewerHost 显示（与模板页同一套封装层） -->
    <div v-if="viewer.workbook.value" class="h-[calc(100vh-13rem)] min-h-[480px] overflow-hidden rounded-lg border">
      <ExcelViewerHost
        :workbook="viewer.workbook.value"
        :editable="viewerEditable"
        :plugins="plugins"
        height="100%"
        @selection-change="onSelection"
        @cell-change="onCellChange"
        @struct-change="onStructChange"
        @sheet-change="onSheetChange"
        @viewer-ready="onViewerReady"
        @error="onViewerError"
      >
        <template #overlay="slotProps">
          <div
            v-if="selectedError"
            class="pointer-events-none absolute z-10 max-w-72 rounded-md bg-neutral-900 px-2 py-1 text-xs text-white shadow-lg"
            :style="errorTooltipStyle(slotProps)"
          >
            {{ selectedError.message }}
          </div>
        </template>
      </ExcelViewerHost>
    </div>
    <div v-else>
      <label class="grid min-h-[320px] cursor-pointer place-items-center rounded-lg border border-dashed px-4 py-16 text-sm text-muted-foreground hover:border-muted-foreground">
        <input type="file" accept=".xlsx" class="hidden" :disabled="viewer.parsing.value || !template" @change="onFile" />
        <span>{{ viewer.parsing.value ? t("import.parsing") : t("import.drop") }}</span>
      </label>
    </div>

    <!-- 右侧抽屉：文件 / 模板 / 映射 / 导入常量 / 校验。外壳见 PageDrawer（非模态、
         640px、顶边推到停靠栏底边之下）。导入页停靠栏实测也是 53px：模板下拉触发器
         class 上写的是 h-8，但 shadcn-vue SelectTrigger 自带的默认 h-9 在层叠中胜出，
         实测 36px 高（走查 1440px 视口量过），故用默认的 53，不传 dock-bar-height-px。 -->
    <PageDrawer v-model:open="drawerOpen">
      <template #title>{{ t("import.details") }}</template>
      <div class="space-y-5">
        <DrawerSection :title="t('import.file')">
          <dl class="space-y-1.5 text-sm">
              <div class="flex justify-between gap-4">
                <dt class="shrink-0 text-muted-foreground">{{ t("common.name") }}</dt>
                <dd class="truncate">{{ sourceFile?.name ?? "—" }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="shrink-0 text-muted-foreground">{{ t("template.sheet") }}</dt>
                <dd class="truncate">
                  {{ adapted?.name ?? template?.sheet ?? "—" }}<template v-if="viewer.sheetNamesList.value.length > 1">（{{ t("import.sheetCount", { n: viewer.sheetNamesList.value.length }) }}）</template>
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted-foreground">{{ t("import.rows") }}</dt>
                <dd>{{ mapped.length }}</dd>
              </div>
            </dl>
            <p v-if="hiddenRows" class="mt-2 text-sm text-muted-foreground">
              {{ t("import.hiddenRows", { n: hiddenRows }) }}
            </p>
        </DrawerSection>

        <Separator />

        <DrawerSection :title="t('import.template')">
          <dl class="space-y-1.5 text-sm">
              <div class="flex justify-between gap-4">
                <dt class="shrink-0 text-muted-foreground">{{ t("common.name") }}</dt>
                <dd class="truncate">{{ template?.name ?? "—" }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="shrink-0 text-muted-foreground">{{ t("template.target") }}</dt>
                <dd class="truncate">{{ template ? `${template.target_schema}.${template.target_table}` : "—" }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted-foreground">{{ t("template.strategy") }}</dt>
                <dd>{{ template ? t(`strategy.${template.strategy}`) : "—" }}</dd>
              </div>
              <div class="flex justify-between gap-4">
                <dt class="shrink-0 text-muted-foreground">{{ t("template.businessKeys") }}</dt>
                <dd class="truncate">{{ template?.business_keys.join(", ") || "—" }}</dd>
              </div>
            </dl>
        </DrawerSection>

        <Separator />

        <DrawerSection v-if="template" :title="t('template.mapping')">
          <MappingTable :rows="importMappingRows" read-only />
          <p class="mt-2 text-xs text-muted-foreground">{{ t("import.quickImportReadOnly") }}</p>
        </DrawerSection>

        <Separator v-if="template" />

        <DrawerSection v-if="requiredConstants.length" :title="t('import.requiredConstants')">
          <p class="mb-3 text-xs text-muted-foreground">{{ t("import.requiredConstantsHint") }}</p>
            <div v-for="constant in requiredConstants" :key="constant.db_column" class="mb-2 space-y-1.5">
              <Label>
                {{ constant.db_column }} <span class="text-destructive">*</span>
              </Label>
              <Input
                :model-value="constantInputs[constant.db_column] ?? ''"
                :placeholder="t('import.constantPlaceholder', { column: constant.db_column })"
                @update:model-value="(value) => (constantInputs[constant.db_column] = String(value))"
                @change="applyConstantOverrides"
              />
              <p
                v-if="(constantInputs[constant.db_column] ?? '').trim() === ''"
                class="text-xs text-destructive"
              >
                {{ t("import.constantRequired", { column: constant.db_column }) }}
              </p>
            </div>
        </DrawerSection>

        <Separator v-if="requiredConstants.length" />

        <DrawerSection :title="t('import.validation')">
          <p class="mb-3 text-sm">{{ problems }} {{ t("import.errors") }}</p>
            <ul v-if="errorItems.length" class="space-y-1 text-sm">
              <li v-for="(item, i) in errorItems" :key="i" class="flex items-center gap-2 text-destructive">
                <span>#{{ item.rowNo }} · {{ item.column }} · {{ codeText(item.code) }}</span>
                <button
                  v-if="item.col != null"
                  type="button"
                  class="ml-auto shrink-0 text-xs text-green-700 hover:underline"
                  @click="locateError(item)"
                >
                  <LocateFixed class="mr-0.5 inline size-3" />{{ t("import.locate") }}
                </button>
              </li>
            </ul>
            <p v-else class="text-sm text-muted-foreground">{{ t("import.noErrorItems") }}</p>
            <p class="mt-2 text-xs text-muted-foreground">{{ t("import.locateHint") }}</p>
        </DrawerSection>
      </div>
    </PageDrawer>

    <AlertDialog :open="scopeConfirm !== null" @update:open="onScopeOpenChange">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ t("import.confirmScopeTitle") }}</AlertDialogTitle>
          <AlertDialogDescription>
            {{ t("import.confirmScope", { n: scopeConfirm?.estimated ?? 0, scopes: scopeConfirm?.scopes ?? 0 }) }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction @click="closeScope(true)">{{ t("common.confirm") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
