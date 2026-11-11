<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import RuleOverridesEditor from "@/components/template/RuleOverridesEditor.vue";
import SynonymGroups from "@/components/template/SynonymGroups.vue";
import UnpivotEditor from "@/components/template/UnpivotEditor.vue";
import { parseWorkbook } from "@/features/excel/parse";
import { pathLabel } from "@/features/header/tree";
import { errorMessage } from "@/lib/errors";
import type {
  Datasource, Mapping, RuleOverride, Strategy, Suggestion, TableInfo, TableSchema, Template,
} from "@/lib/types";

const props = defineProps<{ workspaceId: number | null }>();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();

interface TemplateForm {
  name: string;
  description: string;
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

const editing = computed(() => route.params.id !== undefined);
const datasources = ref<Datasource[]>([]);
const tables = ref<TableInfo[]>([]);
const schema = ref<TableSchema | null>(null);
const suggestions = ref<Suggestion[]>([]);
const error = ref("");
const saving = ref(false);

const form = ref<TemplateForm>({
  name: "",
  description: "",
  datasource_id: null,
  target_schema: "",
  target_table: "",
  sheet: "",
  header_start_row: 1,
  header_row_count: 1,
  strategy: "APPEND",
  business_keys: [],
  scope_columns: [],
  mapping: { columns: [], unpivot: null, constants: [] },
  rule_overrides: [],
});

const dbColumns = computed(() => schema.value?.columns.map((column) => column.name) ?? []);
const pathKey = (path: string[]): string => path.join("\u0000");
const suggestionByPath = computed(
  () => new Map(suggestions.value.map((item) => [pathKey(item.excel_path), item])),
);

async function guarded(action: () => Promise<void>): Promise<void> {
  try {
    await action();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

watch(
  () => props.workspaceId,
  (id) => guarded(async () => {
    datasources.value = id == null ? [] : await api.get<Datasource[]>("/datasources");
  }),
  { immediate: true },
);

watch(
  () => route.params.id,
  (id) => guarded(async () => {
    if (id === undefined || props.workspaceId == null) return;
    const template = await api.get<Template>(`/workspaces/${props.workspaceId}/templates/${id}`);
    form.value = {
      name: template.name,
      description: template.description,
      datasource_id: template.datasource_id,
      target_schema: template.target_schema,
      target_table: template.target_table,
      sheet: template.sheet,
      header_start_row: template.header_start_row,
      header_row_count: template.header_row_count,
      strategy: template.strategy,
      business_keys: template.business_keys,
      scope_columns: template.scope_columns,
      mapping: {
        columns: template.mapping.columns ?? [],
        constants: template.mapping.constants ?? [],
        unpivot: template.mapping.unpivot ?? null,
      },
      rule_overrides: template.rule_overrides ?? [],
    };
  }),
  { immediate: true },
);

watch(
  () => form.value.datasource_id,
  (id) => guarded(async () => {
    tables.value = id == null ? [] : await api.get<TableInfo[]>(`/datasources/${id}/tables`);
  }),
);

watch(
  () => [form.value.datasource_id, form.value.target_schema, form.value.target_table] as const,
  ([id, schemaName, table]) => guarded(async () => {
    schema.value = null;
    if (id == null || !table) return;
    schema.value = await api.get<TableSchema>(
      `/datasources/${id}/tables/${encodeURIComponent(table)}/schema`,
      { schema: schemaName },
    );
  }),
  { immediate: true },
);

function onTable(event: Event): void {
  const table = tables.value[Number((event.target as HTMLSelectElement).value)];
  form.value = { ...form.value, target_schema: table?.schema ?? "", target_table: table?.name ?? "" };
}

function isSelected(table: TableInfo): boolean {
  return table.schema === form.value.target_schema && table.name === form.value.target_table;
}

const onSample = (event: Event) => guarded(async () => {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const parsed = await parseWorkbook(file, {
    sheet: form.value.sheet,
    // 模板里存 Excel 行号（从 1 起），解析函数用 0 起的下标，与 ImportPage 一致。
    headerStartRow: form.value.header_start_row - 1,
    headerRowCount: form.value.header_row_count,
  });
  const paths = parsed.header.leaves.map((leaf) => leaf.path);
  // 还没选表时不能匹配，清掉上一次的建议，避免分数对到别的列上。
  suggestions.value = form.value.datasource_id && form.value.target_table
    ? await api.post<Suggestion[]>(`/workspaces/${props.workspaceId}/templates/suggest-mapping`, {
        datasource_id: form.value.datasource_id,
        target_schema: form.value.target_schema,
        target_table: form.value.target_table,
        paths,
      })
    : [];
  const matched = suggestionByPath.value;
  form.value = {
    ...form.value,
    sheet: parsed.name,
    mapping: {
      ...form.value.mapping,
      columns: paths.map((path) => ({ excel_path: path, db_column: matched.get(pathKey(path))?.db_column ?? "" })),
    },
  };
});

function setMapping(patch: Partial<Mapping>): void {
  form.value = { ...form.value, mapping: { ...form.value.mapping, ...patch } };
}

function setColumn(index: number, dbColumn: string): void {
  setMapping({
    columns: form.value.mapping.columns.map((item, i) => (i === index ? { ...item, db_column: dbColumn } : item)),
  });
}

function setConstant(index: number, patch: { db_column?: string; value?: string }): void {
  setMapping({
    constants: form.value.mapping.constants.map((item, i) => (i === index ? { ...item, ...patch } : item)),
  });
}

function toggleIn(field: "business_keys" | "scope_columns", column: string, checked: boolean): void {
  const current = form.value[field];
  const next = checked ? [...current, column] : current.filter((item) => item !== column);
  form.value = { ...form.value, [field]: next };
}

const inputValue = (event: Event): string => (event.target as HTMLInputElement).value;

const save = () => guarded(async () => {
  error.value = "";
  saving.value = true;
  try {
    const base = `/workspaces/${props.workspaceId}/templates`;
    const mapping = form.value.mapping;
    const payload = {
      ...form.value,
      mapping: {
        ...mapping,
        columns: mapping.columns.filter((item) => item.db_column.trim() !== ""),
        constants: mapping.constants.filter((item) => item.db_column.trim() !== ""),
      },
      rule_overrides: form.value.rule_overrides.filter((item) => item.db_column !== ""),
    };
    if (editing.value) await api.put(`${base}/${route.params.id}`, payload);
    else await api.post(base, payload);
    await router.push("/templates");
  } finally {
    saving.value = false;
  }
});
</script>

<template>
  <div class="stack">
    <div class="page-head"><h1>{{ editing ? form.name : t("template.create") }}</h1></div>
    <datalist id="db-columns">
      <option v-for="column in schema?.columns ?? []" :key="column.name" :value="column.name">
        {{ column.comment }}
      </option>
    </datalist>

    <div class="card stack">
      <label class="field"><span>{{ t("common.name") }}</span><input v-model="form.name" /></label>
      <label class="field"><span>{{ t("common.description") }}</span><input v-model="form.description" /></label>
      <label class="field">
        <span>{{ t("datasource.title") }}</span>
        <select v-model="form.datasource_id">
          <option v-for="item in datasources" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
      <label class="field">
        <span>{{ t("template.target") }}</span>
        <select @change="onTable">
          <option value="">—</option>
          <option
            v-for="(item, index) in tables"
            :key="`${item.schema}.${item.name}`"
            :value="index"
            :selected="isSelected(item)"
          >
            {{ item.schema ? `${item.schema}.${item.name}` : item.name }}
          </option>
        </select>
      </label>
      <div class="row">
        <label class="field"><span>{{ t("template.sheet") }}</span><input v-model="form.sheet" /></label>
        <label class="field"><span>{{ t("template.headerStart") }}</span>
          <input v-model.number="form.header_start_row" type="number" min="1" /></label>
        <label class="field"><span>{{ t("template.headerRows") }}</span>
          <input v-model.number="form.header_row_count" type="number" min="1" max="10" /></label>
      </div>
      <label class="drop">
        <input type="file" accept=".xlsx" @change="onSample" />
        <span>{{ t("template.sample") }} · {{ t("import.drop") }}</span>
      </label>
    </div>

    <div v-if="form.mapping.columns.length" class="card">
      <h2>{{ t("template.mapping") }}</h2>
      <table class="data">
        <tbody>
          <tr v-for="(column, index) in form.mapping.columns" :key="index">
            <td>{{ pathLabel(column.excel_path) }}</td>
            <td>
              <input
                :value="column.db_column"
                list="db-columns"
                :placeholder="t('template.pickColumn')"
                @input="setColumn(index, inputValue($event))"
              />
            </td>
            <td class="muted">{{ suggestionByPath.get(pathKey(column.excel_path))?.score ?? "" }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card stack">
      <h2>{{ t("template.constants") }}</h2>
      <div v-for="(item, index) in form.mapping.constants" :key="index" class="row">
        <input
          :value="item.db_column"
          list="db-columns"
          :placeholder="t('template.pickColumn')"
          @input="setConstant(index, { db_column: inputValue($event) })"
        />
        <input :value="item.value" :placeholder="t('common.value')" @input="setConstant(index, { value: inputValue($event) })" />
        <button class="ghost" @click="setMapping({ constants: form.mapping.constants.filter((_, i) => i !== index) })">
          {{ t("common.remove") }}
        </button>
      </div>
      <div>
        <button class="ghost" @click="setMapping({ constants: [...form.mapping.constants, { db_column: '', value: '' }] })">
          {{ t("common.add") }}
        </button>
      </div>
    </div>

    <UnpivotEditor
      :model-value="form.mapping.unpivot"
      :columns="dbColumns"
      @update:model-value="setMapping({ unpivot: $event })"
    />

    <div class="card stack">
      <label class="field">
        <span>{{ t("template.strategy") }}</span>
        <select v-model="form.strategy">
          <option value="APPEND">{{ t("strategy.APPEND") }}</option>
          <option value="UPSERT">{{ t("strategy.UPSERT") }}</option>
          <option value="REPLACE_SCOPE">{{ t("strategy.REPLACE_SCOPE") }}</option>
        </select>
      </label>
      <p v-if="!dbColumns.length" class="muted">{{ t("template.noTable") }}</p>
      <template v-else>
        <div class="field">
          <span>{{ t("template.businessKeys") }}</span>
          <div class="checks">
            <label v-for="column in dbColumns" :key="column" class="field inline">
              <input
                type="checkbox"
                :checked="form.business_keys.includes(column)"
                @change="toggleIn('business_keys', column, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ column }}</span>
            </label>
          </div>
        </div>
        <div v-if="form.strategy === 'REPLACE_SCOPE'" class="field">
          <span>{{ t("template.scopeColumns") }}</span>
          <div class="checks">
            <label v-for="column in dbColumns" :key="column" class="field inline">
              <input
                type="checkbox"
                :checked="form.scope_columns.includes(column)"
                @change="toggleIn('scope_columns', column, ($event.target as HTMLInputElement).checked)"
              />
              <span>{{ column }}</span>
            </label>
          </div>
        </div>
      </template>
    </div>

    <RuleOverridesEditor v-model="form.rule_overrides" :columns="dbColumns" />

    <div class="card stack">
      <p v-if="error" class="error">{{ error }}</p>
      <div class="row">
        <button :disabled="saving" @click="save">{{ t("common.save") }}</button>
        <RouterLink to="/templates"><button class="ghost">{{ t("common.cancel") }}</button></RouterLink>
      </div>
    </div>

    <SynonymGroups :workspace-id="workspaceId" />
  </div>
</template>

<style scoped>
.drop { display: grid; place-items: center; padding: 24px; border: 1px dashed var(--line); border-radius: var(--radius); cursor: pointer; }
.drop input { display: none; }
h2 { font-size: 16px; margin: 0 0 12px; }
.checks { display: flex; flex-wrap: wrap; gap: 8px 16px; }
</style>
