<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import RuleOverridesEditor from "@/components/template/RuleOverridesEditor.vue";
import SamplePreview from "@/components/template/SamplePreview.vue";
import SynonymGroups from "@/components/template/SynonymGroups.vue";
import UnpivotEditor from "@/components/template/UnpivotEditor.vue";
import PageHeader from "@/components/PageHeader.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { parseWorkbook, type ParsedSheet } from "@/features/excel/parse";
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
/** 本次上传的样例解析结果，用于缩略图预览；切模板时清空。 */
const sample = ref<ParsedSheet | null>(null);

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

// shadcn Select 只认字符串，数据源 id 在此做 string ⇄ number 转换。
const datasourceIdStr = computed({
  get: () => (form.value.datasource_id == null ? "" : String(form.value.datasource_id)),
  set: (value: string) => {
    form.value = { ...form.value, datasource_id: value === "" ? null : Number(value) };
  },
});

const selectedTableIndex = computed(() => {
  const index = tables.value.findIndex(
    (item) => item.schema === form.value.target_schema && item.name === form.value.target_table,
  );
  return index === -1 ? "" : String(index);
});

function onTableIndex(value: string): void {
  if (value === "") return;
  const table = tables.value[Number(value)];
  form.value = { ...form.value, target_schema: table?.schema ?? "", target_table: table?.name ?? "" };
}

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
    sample.value = null;
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

const onSample = (event: Event) => guarded(async () => {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const parsed = await parseWorkbook(file, {
    sheet: form.value.sheet,
    // 模板里存 Excel 行号（从 1 起），解析函数用 0 起的下标，与 ImportPage 一致。
    headerStartRow: form.value.header_start_row - 1,
    headerRowCount: form.value.header_row_count,
  });
  sample.value = parsed;
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

function setColumn(index: number, dbColumn: string | number): void {
  setMapping({
    columns: form.value.mapping.columns.map((item, i) => (i === index ? { ...item, db_column: String(dbColumn) } : item)),
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
  <div class="space-y-6">
    <PageHeader :title="editing ? form.name : t('template.create')" />
    <datalist id="db-columns">
      <option v-for="column in schema?.columns ?? []" :key="column.name" :value="column.name">
        {{ column.comment }}
      </option>
    </datalist>

    <!-- 一、基础信息 -->
    <Card>
      <CardHeader><CardTitle>{{ t("template.basicInfo") }}</CardTitle></CardHeader>
      <CardContent class="space-y-4">
        <div class="space-y-2">
          <Label for="tpl-name">{{ t("common.name") }}</Label>
          <Input id="tpl-name" v-model="form.name" />
        </div>
        <div class="space-y-2">
          <Label for="tpl-desc">{{ t("common.description") }}</Label>
          <Input id="tpl-desc" v-model="form.description" />
        </div>
        <div class="space-y-2">
          <Label>{{ t("datasource.title") }}</Label>
          <Select v-model="datasourceIdStr">
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="item in datasources" :key="item.id" :value="String(item.id)">
                {{ item.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>{{ t("template.target") }}</Label>
          <Select :model-value="selectedTableIndex" @update:model-value="onTableIndex(String($event))">
            <SelectTrigger>
              <SelectValue placeholder="—" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="(item, index) in tables"
                :key="`${item.schema}.${item.name}`"
                :value="String(index)"
              >
                {{ item.schema ? `${item.schema}.${item.name}` : item.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="grid grid-cols-3 gap-4">
          <div class="space-y-2">
            <Label for="tpl-sheet">{{ t("template.sheet") }}</Label>
            <Input id="tpl-sheet" v-model="form.sheet" />
          </div>
          <div class="space-y-2">
            <Label for="tpl-header-start">{{ t("template.headerStart") }}</Label>
            <Input id="tpl-header-start" v-model.number="form.header_start_row" type="number" min="1" />
          </div>
          <div class="space-y-2">
            <Label for="tpl-header-rows">{{ t("template.headerRows") }}</Label>
            <Input id="tpl-header-rows" v-model.number="form.header_row_count" type="number" min="1" max="10" />
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- 二、模版上传识别 -->
    <Card>
      <CardHeader><CardTitle>{{ t("template.uploadRecognize") }}</CardTitle></CardHeader>
      <CardContent class="space-y-4">
        <label class="grid cursor-pointer place-items-center rounded-lg border border-dashed px-4 py-6 text-sm text-muted-foreground hover:border-muted-foreground">
          <input type="file" accept=".xlsx" class="hidden" @change="onSample" />
          <span>{{ t("template.sample") }} · {{ t("import.drop") }}</span>
        </label>
        <SamplePreview v-if="sample" :sample="sample" />
        <p v-if="!sample && !form.mapping.columns.length" class="text-sm text-muted-foreground">
          {{ t("template.sampleHint") }}
        </p>
        <div v-if="form.mapping.columns.length">
          <h3 class="mb-2 text-sm font-medium">{{ t("template.mapping") }}</h3>
          <table class="w-full caption-bottom text-sm">
            <tbody>
              <tr v-for="(column, index) in form.mapping.columns" :key="index" class="border-b last:border-0">
                <td class="px-2 py-1 align-middle">{{ pathLabel(column.excel_path) }}</td>
                <td class="px-2 py-1 align-middle">
                  <Input
                    :model-value="column.db_column"
                    list="db-columns"
                    :placeholder="t('template.pickColumn')"
                    @update:model-value="setColumn(index, $event)"
                  />
                </td>
                <td class="px-2 py-1 align-middle text-muted-foreground">
                  {{ suggestionByPath.get(pathKey(column.excel_path))?.score ?? "" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>

    <!-- 三、导入规则 -->
    <Card>
      <CardHeader><CardTitle>{{ t("template.importRules") }}</CardTitle></CardHeader>
      <CardContent>
        <Tabs default-value="constants">
          <TabsList>
            <TabsTrigger value="constants">{{ t("template.constants") }}</TabsTrigger>
            <TabsTrigger value="unpivot">{{ t("template.unpivot") }}</TabsTrigger>
            <TabsTrigger value="strategy">{{ t("template.strategy") }}</TabsTrigger>
            <TabsTrigger value="rules">{{ t("template.rules") }}</TabsTrigger>
            <TabsTrigger value="synonyms">{{ t("template.synonyms") }}</TabsTrigger>
          </TabsList>

          <TabsContent value="constants" class="space-y-2">
            <div v-for="(item, index) in form.mapping.constants" :key="index" class="flex gap-2">
              <Input
                :model-value="item.db_column"
                list="db-columns"
                :placeholder="t('template.pickColumn')"
                @update:model-value="setConstant(index, { db_column: String($event) })"
              />
              <Input
                :model-value="item.value"
                :placeholder="t('common.value')"
                @update:model-value="setConstant(index, { value: String($event) })"
              />
              <Button variant="outline" @click="setMapping({ constants: form.mapping.constants.filter((_, i) => i !== index) })">
                {{ t("common.remove") }}
              </Button>
            </div>
            <Button variant="outline" @click="setMapping({ constants: [...form.mapping.constants, { db_column: '', value: '' }] })">
              {{ t("common.add") }}
            </Button>
          </TabsContent>

          <TabsContent value="unpivot">
            <UnpivotEditor
              :model-value="form.mapping.unpivot"
              :columns="dbColumns"
              @update:model-value="setMapping({ unpivot: $event })"
            />
          </TabsContent>

          <TabsContent value="strategy" class="space-y-4">
            <div class="space-y-2">
              <Label>{{ t("template.strategy") }}</Label>
              <Select v-model="form.strategy">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="APPEND">{{ t("strategy.APPEND") }}</SelectItem>
                  <SelectItem value="UPSERT">{{ t("strategy.UPSERT") }}</SelectItem>
                  <SelectItem value="REPLACE_SCOPE">{{ t("strategy.REPLACE_SCOPE") }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p v-if="!dbColumns.length" class="text-sm text-muted-foreground">{{ t("template.noTable") }}</p>
            <template v-else>
              <div class="space-y-2">
                <Label>{{ t("template.businessKeys") }}</Label>
                <div class="flex flex-wrap gap-x-4 gap-y-2">
                  <label v-for="column in dbColumns" :key="column" class="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox
                      :model-value="form.business_keys.includes(column)"
                      @update:model-value="toggleIn('business_keys', column, $event === true)"
                    />
                    <span>{{ column }}</span>
                  </label>
                </div>
              </div>
              <div v-if="form.strategy === 'REPLACE_SCOPE'" class="space-y-2">
                <Label>{{ t("template.scopeColumns") }}</Label>
                <div class="flex flex-wrap gap-x-4 gap-y-2">
                  <label v-for="column in dbColumns" :key="column" class="flex cursor-pointer items-center gap-2 text-sm">
                    <Checkbox
                      :model-value="form.scope_columns.includes(column)"
                      @update:model-value="toggleIn('scope_columns', column, $event === true)"
                    />
                    <span>{{ column }}</span>
                  </label>
                </div>
              </div>
            </template>
          </TabsContent>

          <TabsContent value="rules">
            <RuleOverridesEditor v-model="form.rule_overrides" :columns="dbColumns" />
          </TabsContent>

          <TabsContent value="synonyms">
            <SynonymGroups :workspace-id="workspaceId" />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>

    <Card>
      <CardContent class="space-y-4 pt-6">
        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>
        <div class="flex gap-2">
          <Button :disabled="saving" @click="save">{{ t("common.save") }}</Button>
          <Button variant="outline" as-child>
            <RouterLink to="/templates">{{ t("common.cancel") }}</RouterLink>
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
