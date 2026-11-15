<script setup lang="ts">
import { useVirtualizer } from "@tanstack/vue-virtual";
import { computed, nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
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
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { gzipJsonl } from "@/features/excel/gzip";
import { parseInWorker } from "@/features/excel/parse";
import { pathLabel } from "@/features/header/tree";
import { applyMapping, missingHeaders, trimDataRows, type MappedRow } from "@/features/mapping/apply";
import { findDuplicateKeys, validateRow, type CellError, type DefaultApplied } from "@/features/rules/execute";
import { buildGrid, errorCount, type GridColumn, type GridRow } from "@/features/grid/model";
import { codeText, errorMessage } from "@/lib/errors";
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
const canSubmit = computed(
  () => mapped.value.length > 0 && problems.value === 0 && !parsing.value && !submitting.value,
);

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
  if (id == null) return;
  try {
    template.value = await api.get<Template>(`/workspaces/${props.workspaceId}/templates/${id}`);
    rules.value = await api.get<ColumnRule[]>(`/workspaces/${props.workspaceId}/templates/${id}/rules`);
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
  <div class="space-y-6">
    <PageHeader :title="t('import.title')">
      <template #actions>
        <Button variant="outline" as-child>
          <RouterLink to="/imports">{{ t("import.history") }}</RouterLink>
        </Button>
      </template>
    </PageHeader>

    <Card>
      <CardContent class="space-y-4 pt-6">
        <div class="max-w-sm">
          <Select v-model="templateIdStr">
            <SelectTrigger>
              <SelectValue :placeholder="t('import.pickTemplate')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="item in templates" :key="item.id" :value="String(item.id)">
                {{ item.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <label
          v-if="template"
          class="grid cursor-pointer place-items-center rounded-lg border border-dashed px-4 py-8 text-sm text-muted-foreground hover:border-muted-foreground"
        >
          <input type="file" accept=".xlsx" class="hidden" :disabled="parsing" @change="onFile" />
          <span>{{ parsing ? t("import.parsing") : t("import.drop") }}</span>
        </label>
        <p v-if="hiddenRows" class="text-sm text-muted-foreground">
          {{ t("import.hiddenRows", { n: hiddenRows }) }}
        </p>
        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>
      </CardContent>
    </Card>

    <EmptyState v-if="!rows.length" :title="t('common.empty')" />
    <Card v-else>
      <CardContent class="pt-6">
        <div class="mb-4 flex items-center justify-between">
          <span class="text-sm">
            {{ mapped.length }} {{ t("import.rows") }} · {{ problems }} {{ t("import.errors") }}
            <span class="text-muted-foreground">· {{ t("import.editHint") }}</span>
          </span>
          <Button :disabled="!canSubmit" @click="submit">{{ t("import.submit") }}</Button>
        </div>
        <div ref="scroller" class="max-h-[60vh] overflow-auto">
          <table class="w-full caption-bottom text-sm">
            <thead>
              <tr class="border-b">
                <th class="sticky top-0 z-10 h-9 bg-background px-2 text-left align-middle font-medium text-muted-foreground">{{ t("grid.rowNo") }}</th>
                <th
                  v-for="column in columns"
                  :key="column.key"
                  class="sticky top-0 z-10 h-9 bg-background px-2 text-left align-middle font-medium text-muted-foreground"
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
                class="border-b"
              >
                <td class="px-2 py-1 align-middle">{{ rows[item.index].rowNo }}</td>
                <td
                  v-for="column in columns"
                  :key="column.key"
                  class="whitespace-nowrap px-2 py-1 align-middle"
                  :class="rows[item.index].cells[column.key]?.error ? 'bg-destructive/15' : ''"
                  :title="rows[item.index].cells[column.key]?.error
                    ? codeText(rows[item.index].cells[column.key]!.error!.code) : undefined"
                  @dblclick="startEdit(item.index, column.key)"
                >
                  <input
                    v-if="editing?.index === item.index && editing.key === column.key"
                    class="cell-edit w-full min-w-20 rounded-md border border-input bg-background px-1 py-0.5 text-sm"
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
      </CardContent>
    </Card>

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
