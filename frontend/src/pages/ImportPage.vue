<script setup lang="ts">
import { useVirtualizer } from "@tanstack/vue-virtual";
import { computed, nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
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
  return window.confirm(t("import.confirmScope", { n: preview.estimated_delete, scopes: preview.scope_count }));
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
  <div class="stack">
    <div class="page-head">
      <h1>{{ t("import.title") }}</h1>
      <RouterLink to="/imports">{{ t("import.history") }}</RouterLink>
    </div>

    <div class="card stack">
      <label class="field">
        <span>{{ t("import.pickTemplate") }}</span>
        <select v-model="templateId">
          <option v-for="item in templates" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>

      <label v-if="template" class="drop">
        <input type="file" accept=".xlsx" :disabled="parsing" @change="onFile" />
        <span>{{ parsing ? t("import.parsing") : t("import.drop") }}</span>
      </label>
      <p v-if="hiddenRows" class="muted">{{ t("import.hiddenRows", { n: hiddenRows }) }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <EmptyState v-if="!rows.length" :title="t('common.empty')" />
    <div v-else class="card">
      <div class="row" style="justify-content: space-between">
        <span>
          {{ mapped.length }} {{ t("import.rows") }} · {{ problems }} {{ t("import.errors") }}
          <span class="muted">· {{ t("import.editHint") }}</span>
        </span>
        <button :disabled="!canSubmit" @click="submit">{{ t("import.submit") }}</button>
      </div>
      <div ref="scroller" class="grid-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>{{ t("grid.rowNo") }}</th>
              <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="padTop" :style="{ height: `${padTop}px` }"><td :colspan="columns.length + 1" /></tr>
            <tr v-for="item in virtualRows" :key="item.index" :style="{ height: `${ROW_HEIGHT}px` }">
              <td>{{ rows[item.index].rowNo }}</td>
              <td
                v-for="column in columns"
                :key="column.key"
                :data-error="!!rows[item.index].cells[column.key]?.error"
                :title="rows[item.index].cells[column.key]?.error
                  ? codeText(rows[item.index].cells[column.key]!.error!.code) : undefined"
                @dblclick="startEdit(item.index, column.key)"
              >
                <input
                  v-if="editing?.index === item.index && editing.key === column.key"
                  class="cell-edit"
                  :value="rows[item.index].cells[column.key]?.value"
                  @blur="commitEdit"
                  @keydown.enter="($event.target as HTMLInputElement).blur()"
                  @keydown.esc="editing = null"
                />
                <span
                  v-else-if="rows[item.index].cells[column.key]?.defaultApplied"
                  class="muted"
                >{{ t("grid.defaultHint", { value: rows[item.index].cells[column.key]!.defaultApplied!.value }) }}</span>
                <template v-else>{{ rows[item.index].cells[column.key]?.value }}</template>
              </td>
            </tr>
            <tr v-if="padBottom" :style="{ height: `${padBottom}px` }"><td :colspan="columns.length + 1" /></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.drop {
  display: grid; place-items: center; padding: 32px; border: 1px dashed var(--line);
  border-radius: var(--radius); cursor: pointer; color: var(--muted);
}
.drop input { display: none; }
.grid-wrap { overflow: auto; max-height: 60vh; margin-top: 12px; }
.grid-wrap thead th { position: sticky; top: 0; background: var(--surface); z-index: 1; }
.grid-wrap td { white-space: nowrap; }
td[data-error="true"] { background: color-mix(in srgb, var(--danger) 16%, transparent); }
.cell-edit { width: 100%; min-width: 80px; padding: 2px 4px; }
</style>
