<script setup lang="ts">
import { useVirtualizer } from "@tanstack/vue-virtual";
import { computed, nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { FileSpreadsheet, PanelRight } from "@lucide/vue";

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
import { parseInWorker } from "@/features/excel/parse";
import { pathLabel } from "@/features/header/tree";
import { applyMapping, missingHeaders, trimDataRows, type MappedRow } from "@/features/mapping/apply";
import { findDuplicateKeys, validateRow, type CellError, type DefaultApplied } from "@/features/rules/execute";
import { buildGrid, errorCount, type GridColumn, type GridRow } from "@/features/grid/model";
import { codeText, errorMessage } from "@/lib/errors";
import { columnLetter } from "@/lib/utils";
import type { ColumnRule, Template } from "@/lib/types";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const router = useRouter();

const ROW_HEIGHT = 34;

const templates = ref<Template[]>([]);
const templateId = ref<number | null>(null);
const template = ref<Template | null>(null);
const rules = ref<ColumnRule[]>([]);
const sourceFile = ref<File | null>(null);
const rows = ref<GridRow[]>([]);
const mapped = ref<MappedRow[]>([]);
const cleaned = ref<Record<string, unknown>[]>([]);
const parsing = ref(false);
const submitting = ref(false);
const error = ref("");
const hiddenRows = ref(0);
const editing = ref<{ index: number; key: string } | null>(null);
const scroller = ref<HTMLElement | null>(null);
const scopeConfirm = ref<{ estimated: number; scopes: number; resolve: (ok: boolean) => void } | null>(null);
const drawerOpen = ref(false);

// shadcn Select 只认字符串，模板 id 在此做 string ⇄ number 转换。
const templateIdStr = computed({
  get: () => (templateId.value == null ? "" : String(templateId.value)),
  set: (value: string) => {
    templateId.value = value === "" ? null : Number(value);
  },
});

const columns = computed<GridColumn[]>(() => {
  const mapping = template.value?.mapping;
  const keys = mapping
    ? [
        ...mapping.columns.map((item) => item.db_column),
        ...mapping.constants.map((item) => item.db_column),
        ...(mapping.unpivot
          ? [mapping.unpivot.dimension_column, ...mapping.unpivot.measures.map((item) => item.db_column)]
          : []),
      ]
    : [];
  return [...new Set(keys)].map((key) => ({
    key,
    label: key,
    rule: rules.value.find((rule) => rule.db_column === key) ?? null,
  }));
});

const problems = computed(() => errorCount(rows.value));

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
    !parsing.value &&
    !submitting.value,
);

/** 把本次填的常量值写进已映射的行（整列取该值），再重新校验；输入框失焦/回车时调用。 */
function applyConstantOverrides(): void {
  if (!requiredConstants.value.length || !mapped.value.length) return;
  const overrides = Object.fromEntries(
    requiredConstants.value.map((constant) => [constant.db_column, constantInputs.value[constant.db_column] ?? ""]),
  );
  mapped.value = mapped.value.map((row) => ({ ...row, values: { ...row.values, ...overrides } }));
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

/** 抽屉里的校验清单：前 20 条错误（行号 · 列 · 错误）。 */
const errorList = computed(() => {
  const list: { rowNo: number; column: string; code: string }[] = [];
  for (const row of rows.value) {
    for (const [key, cell] of Object.entries(row.cells)) {
      if (cell?.error) {
        list.push({ rowNo: row.rowNo, column: key, code: cell.error.code });
        if (list.length >= 20) return list;
      }
    }
  }
  return list;
});

const virtualizer = useVirtualizer(
  computed(() => ({
    count: rows.value.length,
    getScrollElement: () => scroller.value,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })),
);
const virtualRows = computed(() => virtualizer.value.getVirtualItems());
const padTop = computed(() => virtualRows.value[0]?.start ?? 0);
const padBottom = computed(() => {
  const last = virtualRows.value.at(-1);
  return last ? virtualizer.value.getTotalSize() - last.end : 0;
});

function resetData(): void {
  rows.value = [];
  mapped.value = [];
  cleaned.value = [];
  hiddenRows.value = 0;
  editing.value = null;
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
  parsing.value = true;
  error.value = "";
  try {
    const current = template.value;
    const parsed = await parseInWorker(file, {
      sheet: current.sheet,
      headerStartRow: current.header_start_row - 1,
      headerRowCount: current.header_row_count,
    });
    const missing = missingHeaders(current.mapping, parsed.header.leaves.map((leaf) => leaf.path));
    if (missing.length) {
      error.value = `${codeText("TEMPLATE_HEADER_MISMATCH")}。${t("import.missingHeaders", {
        list: missing.map(pathLabel).join("、"),
      })}`;
      return;
    }
    hiddenRows.value = parsed.hiddenRows;
    mapped.value = trimDataRows(parsed.rows).flatMap((row, index) =>
      applyMapping(row, current.mapping, parsed.rowNumbers[index] ?? index + 1),
    );
    revalidate();
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    parsing.value = false;
  }
}

function revalidate(): void {
  const errors: CellError[] = [];
  const defaults: DefaultApplied[] = [];
  cleaned.value = mapped.value.map((row) => {
    const result = validateRow(rules.value, row.values, row.row_no);
    errors.push(...result.errors);
    defaults.push(...result.defaults);
    return { ...result.cleaned, _row: row.row_no };
  });
  errors.push(...findDuplicateKeys(cleaned.value, template.value?.business_keys ?? []));
  rows.value = buildGrid(mapped.value, columns.value, errors, defaults);
}

async function startEdit(index: number, key: string): Promise<void> {
  editing.value = { index, key };
  await nextTick();
  scroller.value?.querySelector<HTMLInputElement>("input.cell-edit")?.focus();
}

function commitEdit(event: Event): void {
  const target = editing.value;
  editing.value = null;
  if (!target) return;
  const value = (event.target as HTMLInputElement).value;
  // 拆行后同一 Excel 行会产出多条记录，按下标改，不能按行号改。
  mapped.value = mapped.value.map((row, position) =>
    position === target.index ? { ...row, values: { ...row.values, [target.key]: value } } : row,
  );
  revalidate();
}

function askScope(estimated: number, scopes: number): Promise<boolean> {
  return new Promise((resolve) => {
    scopeConfirm.value = { estimated, scopes, resolve };
  });
}

function closeScope(ok: boolean): void {
  scopeConfirm.value?.resolve(ok);
  scopeConfirm.value = null;
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
    // 提交前再覆盖一次常量值：用户可能填完值后未失焦就直接点提交。
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
        <SelectTrigger class="h-8 w-56 shrink-0">
          <SelectValue :placeholder="t('import.pickTemplate')" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="item in templates" :key="item.id" :value="String(item.id)">
            {{ item.name }}
          </SelectItem>
        </SelectContent>
      </Select>
      <span class="flex shrink-0 items-center gap-1 text-sm text-muted-foreground">
        <FileSpreadsheet class="size-4" />
        {{ sourceFile?.name ?? t("import.noFile") }}
      </span>
      <span v-if="rows.length" class="shrink-0 text-sm">
        {{ mapped.length }} {{ t("import.rows") }} · {{ problems }} {{ t("import.errors") }}
        <span class="text-muted-foreground">· {{ t("import.editHint") }}</span>
      </span>
      <span v-if="hiddenRows" class="shrink-0 text-sm text-muted-foreground">
        {{ t("import.hiddenRows", { n: hiddenRows }) }}
      </span>
      <div class="min-w-2 flex-1" />
      <Button variant="outline" size="sm" class="shrink-0" as-child>
        <label class="cursor-pointer">
          <input type="file" accept=".xlsx" class="hidden" :disabled="parsing || !template" @change="onFile" />
          {{ t("import.selectFile") }}
        </label>
      </Button>
      <Button variant="outline" size="sm" class="shrink-0" @click="drawerOpen = true">
        <PanelRight />{{ t("import.details") }}
      </Button>
      <Button size="sm" class="shrink-0" :disabled="!canSubmit" @click="submit">{{ t("import.submit") }}</Button>
    </DockBar>

    <Alert v-if="error" variant="destructive" class="mt-4">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <!-- 主区域：识别后的工作表（Excel 样式虚拟网格） -->
    <div v-if="!rows.length">
      <label class="grid min-h-[320px] cursor-pointer place-items-center rounded-lg border border-dashed px-4 py-16 text-sm text-muted-foreground hover:border-muted-foreground">
        <input type="file" accept=".xlsx" class="hidden" :disabled="parsing || !template" @change="onFile" />
        <span>{{ parsing ? t("import.parsing") : t("import.drop") }}</span>
      </label>
    </div>
    <div v-else ref="scroller" class="max-h-[calc(100vh-13rem)] min-h-[300px] overflow-auto rounded-lg border">
      <table class="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th class="sticky left-0 top-0 z-30 h-7 w-12 border-b border-r bg-muted px-1 text-center align-middle font-medium text-muted-foreground" />
            <th
              v-for="(_, index) in columns"
              :key="`letter-${index}`"
              class="sticky top-0 z-20 h-7 border-b border-r bg-muted px-2 text-center align-middle font-medium text-muted-foreground"
            >
              {{ columnLetter(index) }}
            </th>
          </tr>
          <tr>
            <th class="sticky left-0 top-7 z-30 h-8 w-12 border-b border-r bg-muted px-1 text-center align-middle font-medium text-muted-foreground">
              {{ t("grid.rowNo") }}
            </th>
            <th
              v-for="column in columns"
              :key="column.key"
              class="sticky top-7 z-20 h-8 border-b border-r bg-muted/70 px-2 text-left align-middle font-medium"
            >
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="padTop" :style="{ height: `${padTop}px` }"><td :colspan="columns.length + 1" /></tr>
          <tr
            v-for="item in virtualRows"
            :key="item.index"
            :style="{ height: `${ROW_HEIGHT}px` }"
          >
            <td class="sticky left-0 z-10 w-12 border-b border-r bg-background px-1 py-1 text-center align-middle text-muted-foreground">
              {{ rows[item.index].rowNo }}
            </td>
            <td
              v-for="column in columns"
              :key="column.key"
              class="whitespace-nowrap border-b border-r px-2 py-1 align-middle"
              :class="rows[item.index].cells[column.key]?.error ? 'bg-destructive/15' : ''"
              :title="rows[item.index].cells[column.key]?.error
                ? codeText(rows[item.index].cells[column.key]!.error!.code) : undefined"
              @dblclick="startEdit(item.index, column.key)"
            >
              <input
                v-if="editing?.index === item.index && editing.key === column.key"
                class="cell-edit w-full min-w-20 rounded-md border border-input bg-background px-1 py-0.5 text-xs"
                :value="rows[item.index].cells[column.key]?.value"
                @blur="commitEdit"
                @keydown.enter="($event.target as HTMLInputElement).blur()"
                @keydown.esc="editing = null"
              />
              <span
                v-else-if="rows[item.index].cells[column.key]?.defaultApplied"
                class="text-muted-foreground"
              >{{ t("grid.defaultHint", { value: rows[item.index].cells[column.key]!.defaultApplied!.value }) }}</span>
              <template v-else>{{ rows[item.index].cells[column.key]?.value }}</template>
            </td>
          </tr>
          <tr v-if="padBottom" :style="{ height: `${padBottom}px` }"><td :colspan="columns.length + 1" /></tr>
        </tbody>
      </table>
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
            <ul v-if="errorList.length" class="space-y-1 text-sm">
              <li v-for="(item, i) in errorList" :key="i" class="text-destructive">
                #{{ item.rowNo }} · {{ item.column }} · {{ codeText(item.code) }}
              </li>
            </ul>
            <p v-else class="text-sm text-muted-foreground">{{ t("import.noErrorItems") }}</p>
        </DrawerSection>
      </div>
    </PageDrawer>

    <AlertDialog :open="scopeConfirm !== null" @update:open="(open) => { if (!open) closeScope(false); }">
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
