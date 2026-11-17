<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { PanelRight } from "@lucide/vue";

import { api, ApiError, download, fetchBlob } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import DrawerSection from "@/components/layout/DrawerSection.vue";
import PageDrawer from "@/components/layout/PageDrawer.vue";
import MappingTable, { type MappingTableRow } from "@/components/template/MappingTable.vue";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import ExcelViewerHost from "@/features/excel-viewer/ExcelViewerHost.vue";
import {
  modelSheetIndex,
  modelToParsedSheet,
  type AdaptedSheet,
} from "@/features/excel-viewer/modelAdapter";
import { createQuickImportPlugin } from "@/features/excel-viewer/quickImportPlugin";
import { useExcelViewer, type SelectionRange } from "@/features/excel-viewer/useExcelViewer";
import { pathLabel } from "@/features/header/tree";
import { codeText, errorMessage, logText } from "@/lib/errors";
import { buildErrorCells, errorCellPosition } from "@/lib/importRecords";
import type { ImportError, ImportLog, ImportStatus, ImportTask, Page, Template } from "@/lib/types";
import { useSession } from "@/stores/session";

const props = defineProps<{ workspaceId: number | null }>();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { t } = useI18n();

const TERMINAL: ImportStatus[] = ["SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"];
const POLL_MS = 2000;
const ERROR_PAGE_SIZE = 50;

const task = ref<ImportTask | null>(null);
const logs = ref<ImportLog[]>([]);
const errors = ref<ImportError[]>([]);
const errorPage = ref(1);
const error = ref("");
const busy = ref(false);
const pendingOutcome = ref<"CONFIRMED_WRITTEN" | "CONFIRMED_NOT_WRITTEN" | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

/* ---------- 只读数据视图（Phase 2） ----------
 * viewer 只读挂载原文件（editable=false，不监听 cell-change，没有提交按钮）；
 * 映射取任务提交时的模板版本（GET /templates/{id}?version=…，历史版本保留在库里）；
 * 抽屉里点错误跳到对应单元格（错误行号是 1 基 Excel 行号，列是目标字段名，
 * 经版本映射 → 叶子列定位，见 @/lib/importRecords）。 */
const viewer = useExcelViewer();
const errorCells = ref<ReadonlySet<string>>(new Set());
const versionTemplate = ref<Template | null>(null);
const mappingLoadError = ref(false);
const adaptedSheet = ref<AdaptedSheet | null>(null);
const allErrors = ref<ImportError[]>([]);
const drawerOpen = ref(false);
const dataViewState = ref<"idle" | "loading" | "ready" | "expired" | "error">("idle");
const dataViewError = ref("");
const dataViewTaskId = ref<number | null>(null);
const allErrorsTaskId = ref<number | null>(null);

/** 插件引用创建一次、保持稳定（模板里不写内联数组，见 ExcelViewerHost 的说明）。 */
const viewerPlugins = [
  createQuickImportPlugin({
    onSelectionChange: (selection) => viewer.onSelectionChange(selection),
    getErrorCells: () => errorCells.value,
    getDimension: () => {
      const model = viewer.workbook.value;
      const sheet = model?.sheets[viewer.activeSheetIndex.value];
      return sheet ? sheet.dimension : null;
    },
    onViewerReady: (api) => viewer.setViewerApi(api),
  }),
];

const mappingRows = computed<MappingTableRow[]>(() =>
  (versionTemplate.value?.mapping.columns ?? []).map((column, index) => ({
    key: column.excel_path.join("\u0000"),
    index,
    excelLabel: pathLabel(column.excel_path),
    dbColumn: column.db_column,
    score: null,
  })),
);

const dataSheetIndex = computed(() => {
  const model = viewer.workbook.value;
  if (!model || !versionTemplate.value) return model?.activeSheet ?? 0;
  const index = modelSheetIndex(model, versionTemplate.value.sheet);
  return index >= 0 ? index : (model.activeSheet ?? 0);
});

function adaptSheet(sheetIndex: number): void {
  const model = viewer.workbook.value;
  const template = versionTemplate.value;
  if (!model || !template) return;
  adaptedSheet.value = modelToParsedSheet(
    model,
    sheetIndex,
    template.header_start_row - 1,
    template.header_row_count,
  );
  errorCells.value = buildErrorCells(allErrors.value, template.mapping, adaptedSheet.value);
}

function onViewerReady(): void {
  viewer.selectSheet(dataSheetIndex.value);
  adaptSheet(dataSheetIndex.value);
}

function onViewerSheetChange(payload: { index: number; name: string }): void {
  viewer.activeSheetIndex.value = payload.index;
  adaptSheet(payload.index);
}

function onViewerSelection(payload: { range: SelectionRange; active: { row: number; col: number } }): void {
  viewer.onSelectionChange(payload);
}

function onViewerError(message: string): void {
  dataViewError.value = message;
}

/** 抽屉里点错误 → 跳到对应单元格（viewer 就绪且能定位时才跳）。 */
function jumpToError(item: ImportError): void {
  const template = versionTemplate.value;
  const target = template ? errorCellPosition(item, template.mapping, adaptedSheet.value) : null;
  if (!target) return;
  viewer.selectSheet(dataSheetIndex.value);
  viewer.scrollToCell(target.row, target.column, { select: true });
}

async function loadAllErrors(): Promise<void> {
  const current = task.value;
  if (!current || !current.error_count || allErrorsTaskId.value === current.id) return;
  allErrorsTaskId.value = current.id;
  const collected: ImportError[] = [];
  let page = 1;
  while (collected.length < 1000) {
    const result = await api.get<Page<ImportError>>(`${base.value}/errors`, { page, size: 100 });
    collected.push(...result.items);
    if (result.items.length < 100 || collected.length >= result.total) break;
    page += 1;
  }
  allErrors.value = collected;
  if (adaptedSheet.value && versionTemplate.value) {
    errorCells.value = buildErrorCells(allErrors.value, versionTemplate.value.mapping, adaptedSheet.value);
  }
}

async function loadDataView(): Promise<void> {
  const current = task.value;
  if (!current || props.workspaceId == null || dataViewTaskId.value === current.id) return;
  dataViewTaskId.value = current.id;
  dataViewState.value = "loading";
  dataViewError.value = "";
  mappingLoadError.value = false;
  try {
    versionTemplate.value = await api.get<Template>(
      `/workspaces/${props.workspaceId}/templates/${current.template_id}`,
      { version: current.template_version },
    );
  } catch {
    versionTemplate.value = null;
    mappingLoadError.value = true;
  }
  try {
    const blob = await fetchBlob(`${base.value}/file`);
    const file = new File(
      [blob],
      current.file_name || `import-${current.id}.xlsx`,
      { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    );
    await viewer.loadFile(file);
    dataViewState.value = "ready";
  } catch (caught) {
    // 原文件过期（410 IMPORT_FILES_EXPIRED）时只读视图不可用，映射条与错误抽屉仍可看；
    // 其他错误（网络等）走 error 态。
    dataViewState.value =
      caught instanceof ApiError && caught.code === "IMPORT_FILES_EXPIRED" ? "expired" : "error";
    dataViewError.value = errorMessage(caught);
  }
}

const base = computed(() => `/workspaces/${props.workspaceId}/imports/${route.params.id}`);
const terminal = computed(() => task.value != null && TERMINAL.includes(task.value.status));
const canCancel = computed(() => task.value?.status === "QUEUED" || task.value?.status === "RUNNING");
const canRetry = computed(() => task.value?.status === "FAILED" || task.value?.status === "CANCELLED");
const canResolve = computed(() => session.isAdmin && task.value?.status === "UNKNOWN");

async function loadLogs(): Promise<void> {
  const lastId = logs.value.at(-1)?.id ?? 0;
  const fresh = await api.get<ImportLog[]>(`${base.value}/logs`, { after_id: lastId });
  if (fresh.length) logs.value = [...logs.value, ...fresh];
}

async function loadErrors(): Promise<void> {
  if (!task.value?.error_count) {
    errors.value = [];
    return;
  }
  const page = await api.get<Page<ImportError>>(`${base.value}/errors`, {
    page: errorPage.value,
    size: ERROR_PAGE_SIZE,
  });
  errors.value = page.items;
}

async function refresh(): Promise<void> {
  clearTimeout(timer);
  if (props.workspaceId == null) return;
  try {
    task.value = await api.get<ImportTask>(base.value);
    await loadLogs();
    void loadDataView();
    if (terminal.value) {
      await loadErrors();
      await loadAllErrors();
    } else timer = setTimeout(refresh, POLL_MS);
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

watch(
  () => [props.workspaceId, route.params.id],
  () => {
    logs.value = [];
    errors.value = [];
    errorPage.value = 1;
    error.value = "";
    viewer.workbook.value = null;
    adaptedSheet.value = null;
    errorCells.value = new Set();
    allErrors.value = [];
    versionTemplate.value = null;
    mappingLoadError.value = false;
    dataViewState.value = "idle";
    dataViewError.value = "";
    dataViewTaskId.value = null;
    allErrorsTaskId.value = null;
    void refresh();
  },
  { immediate: true },
);
watch(errorPage, () => void loadErrors().catch((caught) => (error.value = errorMessage(caught))));
onBeforeUnmount(() => clearTimeout(timer));

async function run(action: () => Promise<void>): Promise<void> {
  error.value = "";
  busy.value = true;
  try {
    await action();
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    busy.value = false;
  }
}

const cancel = () => run(async () => {
  await api.post(`${base.value}/cancel`);
  await refresh();
});

const retry = () => run(async () => {
  const next = await api.post<ImportTask>(`${base.value}/retry`);
  await router.push(`/imports/${next.id}`);
});

const resolve = () => run(async () => {
  if (pendingOutcome.value == null) return;
  task.value = await api.post<ImportTask>(`${base.value}/resolve`, { outcome: pendingOutcome.value });
  pendingOutcome.value = null;
  await loadLogs();
});

const downloadFile = () =>
  run(() => download(`${base.value}/file`, task.value?.file_name || `import-${route.params.id}.xlsx`));
const exportErrors = () =>
  run(() => download(`${base.value}/error-report`, `import-${route.params.id}-errors.xlsx`));
</script>

<template>
  <div class="space-y-6">
    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <template v-if="task">
      <PageHeader :title="`#${task.id}`">
        <template #actions>
          <StatusBadge :status="task.status" />
          <Button v-if="canCancel" variant="outline" :disabled="busy" @click="cancel">
            {{ t("import.cancel") }}
          </Button>
          <Button v-if="canRetry" :disabled="busy" @click="retry">
            {{ t("import.retry") }}
          </Button>
          <template v-if="canResolve">
            <Button
              variant="outline"
              :disabled="busy"
              @click="pendingOutcome = 'CONFIRMED_WRITTEN'"
            >
              {{ t("import.resolveWritten") }}
            </Button>
            <Button
              variant="outline"
              :disabled="busy"
              @click="pendingOutcome = 'CONFIRMED_NOT_WRITTEN'"
            >
              {{ t("import.resolveNotWritten") }}
            </Button>
          </template>
          <Button variant="outline" :disabled="busy" @click="downloadFile">
            {{ t("import.downloadFile") }}
          </Button>
        </template>
      </PageHeader>

      <Card>
        <CardContent class="space-y-2 pt-6 text-sm">
          <p>{{ task.target_table }} · {{ task.strategy ? t(`strategy.${task.strategy}`) : "" }} · {{ task.operator }}</p>
          <p v-if="!terminal" class="text-muted-foreground">
            {{ t("import.progress", { processed: task.processed, total: task.row_count }) }}
          </p>
          <p class="text-muted-foreground">
            {{ t("import.counts", { inserted: task.inserted, updated: task.updated, deleted: task.deleted }) }}
            <span v-if="!task.counts_exact">{{ t("import.countsApprox") }}</span>
          </p>
          <p v-if="task.failure_code" class="text-destructive">
            {{ codeText(task.failure_code, task.failure_message) }}
          </p>
          <p v-if="task.failure_message && task.failure_message !== codeText(task.failure_code)" class="text-muted-foreground">
            {{ task.failure_message }}
          </p>
        </CardContent>
      </Card>

      <!-- 只读数据视图：原文件只读 viewer + 顶部映射条（该版本模板的映射）。
           viewer 以 :editable="false" 挂载，不监听 cell-change，没有提交按钮。 -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center justify-between">
            <span>{{ t("import.dataView") }}</span>
            <Button variant="outline" size="sm" @click="drawerOpen = true">
              <PanelRight />{{ t("import.details") }}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent class="space-y-3">
          <div v-if="versionTemplate" class="flex gap-2 overflow-x-auto pb-1 text-xs">
            <span
              v-for="row in mappingRows"
              :key="row.key"
              class="shrink-0 rounded-md border bg-muted/50 px-2 py-1"
            >
              {{ row.excelLabel }} → {{ row.dbColumn }}
            </span>
          </div>
          <p v-else-if="mappingLoadError" class="text-sm text-muted-foreground">
            {{ t("import.viewExpiredMapping") }}
          </p>
          <p v-if="dataViewState === 'loading'" class="text-sm text-muted-foreground">
            {{ t("common.loading") }}
          </p>
          <p v-if="dataViewState === 'expired'" class="text-sm text-muted-foreground">
            {{ t("import.viewFileExpired") }}
          </p>
          <p v-if="dataViewState === 'error' && dataViewError" class="text-sm text-destructive">
            {{ dataViewError }}
          </p>
          <div
            v-if="viewer.workbook.value"
            class="h-[calc(100vh-13rem)] min-h-[480px] overflow-hidden rounded-lg border"
          >
            <ExcelViewerHost
              :workbook="viewer.workbook.value"
              :editable="false"
              :plugins="viewerPlugins"
              height="100%"
              @selection-change="onViewerSelection"
              @sheet-change="onViewerSheetChange"
              @viewer-ready="onViewerReady"
              @error="onViewerError"
            />
          </div>
          <p v-if="viewer.workbook.value" class="text-xs text-muted-foreground">
            {{ t("import.dataViewReadOnly") }}
          </p>
        </CardContent>
      </Card>

      <Card v-if="task.error_count && errors.length">
        <CardHeader>
          <CardTitle class="flex items-center justify-between">
            <span>{{ task.error_count }} {{ t("import.errors") }}</span>
            <Button variant="outline" size="sm" :disabled="busy" @click="exportErrors">
              {{ t("import.exportErrors") }}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{{ t("grid.rowNo") }}</TableHead>
                <TableHead>{{ t("common.column") }}</TableHead>
                <TableHead>{{ t("import.errors") }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="item in errors" :key="item.id">
                <TableCell>{{ item.row_no }}</TableCell>
                <TableCell>{{ item.column }}</TableCell>
                <TableCell>{{ codeText(item.code) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <div v-if="task.error_count > ERROR_PAGE_SIZE" class="mt-4 flex items-center gap-2">
            <Button variant="outline" size="sm" :disabled="errorPage === 1" @click="errorPage -= 1">
              {{ t("common.prev") }}
            </Button>
            <span class="text-sm text-muted-foreground">{{ errorPage }}</span>
            <Button
              variant="outline"
              size="sm"
              :disabled="errorPage * ERROR_PAGE_SIZE >= task.error_count"
              @click="errorPage += 1"
            >
              {{ t("common.next") }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{{ t("import.logs") }}</CardTitle></CardHeader>
        <CardContent>
          <ScrollArea class="h-64">
            <p
              v-for="log in logs"
              :key="log.id"
              :class="log.level === 'INFO' ? 'text-sm text-muted-foreground' : 'text-sm text-destructive'"
            >
              {{ new Date(log.ts).toLocaleString() }} · {{ logText(log) }}
            </p>
          </ScrollArea>
        </CardContent>
      </Card>
    </template>

    <!-- 右侧抽屉（非模态，可开着抽屉看 viewer）：文件 / 模板 / 映射 / 错误与统计。
         点错误跳到对应单元格；无错误时显示无错误。 -->
    <PageDrawer v-if="task" v-model:open="drawerOpen">
      <template #title>{{ t("import.details") }}</template>
      <div class="space-y-5">
        <DrawerSection :title="t('import.file')">
          <dl class="space-y-1.5 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="shrink-0 text-muted-foreground">{{ t("common.name") }}</dt>
              <dd class="truncate">{{ task.file_name || "—" }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted-foreground">{{ t("import.rows") }}</dt>
              <dd>{{ task.row_count }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted-foreground">{{ t("template.target") }}</dt>
              <dd class="truncate">{{ task.target_table }}</dd>
            </div>
          </dl>
        </DrawerSection>

        <Separator />

        <DrawerSection :title="t('import.template')">
          <dl class="space-y-1.5 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="shrink-0 text-muted-foreground">{{ t("common.name") }}</dt>
              <dd class="truncate">{{ versionTemplate?.name ?? "—" }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted-foreground">{{ t("template.mapping") }}</dt>
              <dd>v{{ task.template_version }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-muted-foreground">{{ t("template.strategy") }}</dt>
              <dd>{{ task.strategy ? t(`strategy.${task.strategy}`) : "—" }}</dd>
            </div>
          </dl>
        </DrawerSection>

        <Separator v-if="versionTemplate" />

        <DrawerSection v-if="versionTemplate" :title="t('template.mapping')">
          <MappingTable :rows="mappingRows" read-only />
        </DrawerSection>

        <Separator v-if="versionTemplate" />

        <DrawerSection :title="t('import.errorStats')">
          <p class="mb-3 text-sm">{{ task.error_count }} {{ t("import.errors") }}</p>
          <ul v-if="allErrors.length" class="space-y-1 text-sm">
            <li v-for="item in allErrors" :key="item.id">
              <button
                class="text-left text-destructive hover:underline"
                :title="t('import.jumpToCell')"
                @click="jumpToError(item)"
              >
                #{{ item.row_no }} · {{ item.column }} · {{ codeText(item.code) }}
              </button>
            </li>
          </ul>
          <p v-else class="text-sm text-muted-foreground">{{ t("import.noErrorsHere") }}</p>
        </DrawerSection>
      </div>
    </PageDrawer>

    <AlertDialog :open="pendingOutcome !== null" @update:open="(open) => { if (!open) pendingOutcome = null; }">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {{ pendingOutcome === "CONFIRMED_WRITTEN" ? t("import.resolveWritten") : t("import.resolveNotWritten") }}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {{ t("import.resolveConfirm", { outcome: pendingOutcome === "CONFIRMED_WRITTEN" ? t("import.resolveWritten") : t("import.resolveNotWritten") }) }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction :disabled="busy" @click="resolve">{{ t("common.confirm") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
