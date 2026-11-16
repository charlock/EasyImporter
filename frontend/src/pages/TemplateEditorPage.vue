<template>
  <!-- 停靠栏：模板下拉 + 新建 + 样例 chip + 状态徽章 + 快速导入 + 上传 + 编辑/配置/取消/保存 -->
  <div
    class="sticky top-14 z-30 -mx-4 md:-mx-6 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b px-4 md:px-6 py-2 flex flex-wrap items-center gap-2"
  >
    <Select :model-value="templateSelectValue" @update:model-value="onTemplateSelect">
      <SelectTrigger class="w-56 h-8">
        <SelectValue :placeholder="t('template.selectTemplate')" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="item in templates" :key="item.id" :value="String(item.id)">
          {{ item.name }}
        </SelectItem>
        <SelectSeparator />
        <SelectItem value="new">{{ t("template.newTemplateItem") }}</SelectItem>
      </SelectContent>
    </Select>
    <Button
      variant="outline"
      size="icon"
      class="h-8 w-8"
      :disabled="!buttonStates.addNew"
      :title="t('template.newTemplateItem')"
      @click="startNew"
    >
      <Plus class="h-4 w-4" />
    </Button>
    <span v-if="sampleFileName" class="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <FileSpreadsheet class="h-4 w-4" />{{ sampleFileName }}
    </span>
    <span class="rounded-full px-2 py-0.5 text-xs" :class="stateBadge.cls">{{ stateBadge.text }}</span>
    <div class="flex-1" />
    <DropdownMenu>
      <DropdownMenuTrigger as-child>
        <Button variant="outline" size="sm" :disabled="!buttonStates.quickImport">
          <Zap class="mr-1 h-4 w-4" />{{ t("template.quickImport") }}
          <ChevronDown class="ml-1 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-72">
        <DropdownMenuItem @click="openQuickImport('start-row')">
          <div>
            <div class="font-medium">{{ t("template.quickStartRow") }}</div>
            <div class="text-xs text-muted-foreground">{{ t("template.dataStartRow") }}</div>
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem @click="openQuickImport('mapping')">
          <div>
            <div class="font-medium">{{ t("template.quickMapping") }}</div>
            <div class="text-xs text-muted-foreground">{{ t("template.mappingRow") }}</div>
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem @click="openQuickImport('rules')">
          <div>
            <div class="font-medium">{{ t("template.rules") }}</div>
            <div class="text-xs text-muted-foreground">{{ t("template.rules") }}</div>
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem @click="openQuickImport('synonyms')">
          <div>
            <div class="font-medium">{{ t("template.synonyms") }}</div>
            <div class="text-xs text-muted-foreground">{{ t("template.synonyms") }}</div>
          </div>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <label
      class="inline-flex h-8 cursor-pointer items-center rounded-md border px-3 text-sm hover:bg-accent"
      :class="buttonStates.uploadSample ? '' : 'pointer-events-none opacity-50'"
    >
      <Upload class="mr-1 h-4 w-4" />{{ t("template.uploadSample") }}
      <input type="file" accept=".xlsx" class="hidden" :disabled="!buttonStates.uploadSample" @change="onSample" />
    </label>
    <Button
      v-if="pageModel.state === 'S1'"
      variant="outline"
      size="sm"
      :disabled="!buttonStates.edit"
      @click="startEdit"
    >
      <Pencil class="mr-1 h-4 w-4" />{{ t("common.edit") }}
    </Button>
    <Button variant="outline" size="sm" :disabled="!buttonStates.configure" @click="drawerOpen = true">
      <SlidersHorizontal class="mr-1 h-4 w-4" />{{ t("template.configure") }}
    </Button>
    <Button variant="outline" size="sm" :disabled="!buttonStates.cancel" @click="cancelEdit">
      {{ t("common.cancel") }}
    </Button>
    <Button size="sm" :disabled="!buttonStates.save" :title="saveDisabledReason" @click="saveTemplate">
      {{ t("common.save") }}
    </Button>
  </div>

  <Alert v-if="error" variant="destructive" class="mt-4">
    <AlertDescription>{{ error }}</AlertDescription>
  </Alert>

  <!-- 主区域：有样例挂 ExcelViewerHost；无样例保留 drop zone；有映射无样例保留回退映射表 -->
  <div
    v-if="viewer.workbook.value"
    class="mt-4 h-[calc(100vh-13rem)] min-h-[480px] overflow-hidden rounded-lg border"
  >
    <ExcelViewerHost
      :workbook="viewer.workbook.value"
      :editable="viewerEditable(pageModel)"
      :plugins="plugins"
      height="100%"
      @selection-change="onSelection"
      @sheet-change="onSheetChange"
      @viewer-ready="onViewerReady"
      @error="onViewerError"
    />
  </div>
  <div v-else class="mt-4 space-y-4">
    <label
      class="flex min-h-64 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-muted-foreground"
    >
      <FileSpreadsheet class="h-8 w-8" />
      <span>{{ t("template.uploadSample") }}</span>
      <span class="text-xs">{{ t("template.sampleHint") }}</span>
      <input type="file" accept=".xlsx" class="hidden" @change="onSample" />
    </label>
    <div v-if="form.mapping.columns.length">
      <h2 class="mb-2 text-sm font-medium">{{ t("template.mapping") }}</h2>
      <table class="w-full text-sm">
        <tbody>
          <tr v-for="(column, index) in form.mapping.columns" :key="pathKey(column.excel_path)" class="border-b">
            <td class="py-1 pr-2">{{ pathLabel(column.excel_path) }}</td>
            <td class="py-1 pr-2">
              <Input
                class="h-7"
                :model-value="column.db_column"
                list="db-columns"
                :placeholder="t('template.pickColumn')"
                :disabled="readOnly"
                @update:model-value="(value) => setColumn(index, String(value))"
              />
            </td>
            <td class="py-1 text-muted-foreground">
              {{ suggestionScores.get(pathKey(column.excel_path)) ?? "—" }}
            </td>
          </tr>
        </tbody>
      </table>
      <datalist id="db-columns">
        <option v-for="column in dbColumns" :key="column" :value="column" />
      </datalist>
    </div>
  </div>

  <!-- 设定窗：非模态（:modal="false"），以便开着抽屉时仍能在 Viewer 里点选；reka 在非模态下不渲染遮罩。
       注意：Sheet 默认 fixed inset-y-0 z-50，会盖住 AppShell 头部右侧与停靠栏右侧的按钮
       （保存/取消/配置等点不到）。效果图里抽屉是 .main 内的 absolute、z-20，停靠栏 z-30 在其上。
       这里用行内 top 把抽屉顶边推到停靠栏底边之下（3.5rem 头部 + 1.5rem 主区上内边距 + 53px 停靠栏高，
       1440px 视口实测），z-index 降到 20（低于停靠栏的 30），height:auto 配 inset-y-0 的 bottom:0
       使抽屉恰好撑满剩余高度。 -->
  <Sheet :modal="false" :open="drawerOpen" @update:open="(value) => (drawerOpen = value)">
    <SheetContent
      side="right"
      class="w-full overflow-y-auto sm:max-w-[640px]"
      style="top: calc(3.5rem + 1.5rem + 53px); z-index: 20; height: auto"
      @pointer-down-outside="(event) => event.preventDefault()"
      @focus-outside="(event) => event.preventDefault()"
    >
      <SheetHeader>
        <SheetTitle>{{ form.name || t("template.create") }}</SheetTitle>
      </SheetHeader>
      <div
        v-if="pendingRowFill != null && activeTab !== 'start-row' && pageModel.state !== 'S1'"
        class="mt-4 flex items-center justify-between rounded-md bg-accent px-3 py-2 text-sm"
      >
        <span>{{ t("template.selectionRow", { n: pendingRowFill }) }}</span>
        <Button size="sm" variant="outline" @click="applyAndGoToStartRow">
          {{ t("template.bringFromSelection") }}
        </Button>
      </div>

      <div class="mt-4 space-y-4" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
        <section>
          <h3 class="mb-2 text-sm font-medium">{{ t("template.basicInfo") }}</h3>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <Label>{{ t("common.name") }}</Label>
              <Input v-model="form.name" />
            </div>
            <div>
              <Label>{{ t("common.description") }}</Label>
              <Input v-model="form.description" />
            </div>
            <div>
              <Label>{{ t("datasource.title") }}</Label>
              <Select v-model="datasourceIdStr">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="source in datasources" :key="source.id" :value="String(source.id)">
                    {{ source.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{{ t("template.target") }}</Label>
              <Select :model-value="targetSelectValue" @update:model-value="onTargetSelect">
                <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="(table, index) in tables" :key="table.name" :value="String(index)">
                    {{ table.schema ? `${table.schema}.${table.name}` : table.name }}
                  </SelectItem>
                  <SelectSeparator />
                  <SelectItem :value="AUTO_TABLE_VALUE">{{ t("template.autoTable") }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div v-if="autoTableMode" class="mt-2 space-y-2 rounded-md border p-3">
            <div>
              <Label>{{ t("template.autoTableName") }}</Label>
              <Input v-model="autoTableName" />
            </div>
            <p v-if="previewHint" class="text-xs text-muted-foreground">{{ previewHint }}</p>
            <Button variant="outline" size="sm" :disabled="!canPreviewDdl || inferring" @click="previewDdl">
              {{ t("template.previewDdl") }}
            </Button>
          </div>
          <div class="mt-2 grid grid-cols-2 gap-2">
            <div>
              <Label>{{ t("template.sheet") }}</Label>
              <Input v-model="form.sheet" />
            </div>
          </div>
        </section>

        <Separator />

        <section>
          <h3 class="mb-2 text-sm font-medium">{{ t("template.strategy") }}</h3>
          <Select v-model="form.strategy">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="APPEND">{{ t("strategy.APPEND") }}</SelectItem>
              <SelectItem value="UPSERT">{{ t("strategy.UPSERT") }}</SelectItem>
              <SelectItem value="REPLACE_SCOPE">{{ t("strategy.REPLACE_SCOPE") }}</SelectItem>
            </SelectContent>
          </Select>
          <div class="mt-2">
            <Label>{{ t("template.businessKeys") }}</Label>
            <div class="mt-1 flex flex-wrap gap-2">
              <label v-for="column in dbColumns" :key="column" class="flex items-center gap-1 text-sm">
                <Checkbox
                  :model-value="form.business_keys.includes(column)"
                  @update:model-value="(checked) => toggleIn('business_keys', column, checked === true)"
                />
                {{ column }}
              </label>
            </div>
          </div>
          <div v-if="form.strategy === 'REPLACE_SCOPE'" class="mt-2">
            <Label>{{ t("template.scopeColumns") }}</Label>
            <div class="mt-1 flex flex-wrap gap-2">
              <label v-for="column in dbColumns" :key="column" class="flex items-center gap-1 text-sm">
                <Checkbox
                  :model-value="form.scope_columns.includes(column)"
                  @update:model-value="(checked) => toggleIn('scope_columns', column, checked === true)"
                />
                {{ column }}
              </label>
            </div>
          </div>
          <p v-if="form.strategy === 'UPSERT' && !form.business_keys.length" class="mt-1 text-xs text-muted-foreground">
            {{ t("template.upsertNeedsKeys") }}
          </p>
        </section>
      </div>

      <Separator class="my-4" />

      <Tabs v-model="activeTab" class="w-full">
        <TabsList class="grid w-full grid-cols-4">
          <TabsTrigger value="start-row">{{ t("template.quickStartRow") }}</TabsTrigger>
          <TabsTrigger value="mapping">{{ t("template.quickMapping") }}</TabsTrigger>
          <TabsTrigger value="rules">{{ t("template.rules") }}</TabsTrigger>
          <TabsTrigger value="synonyms">{{ t("template.synonyms") }}</TabsTrigger>
        </TabsList>

        <TabsContent value="start-row">
          <div class="space-y-3" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <div class="grid grid-cols-3 gap-2">
              <div>
                <Label>{{ t("template.headerStart") }}</Label>
                <Input v-model.number="form.header_start_row" type="number" min="1" />
              </div>
              <div>
                <Label>{{ t("template.headerRows") }}</Label>
                <Input v-model.number="form.header_row_count" type="number" min="1" max="10" />
              </div>
              <div>
                <Label>{{ t("template.dataStartRow") }}</Label>
                <Input v-model.number="dataStartRow" type="number" min="1" />
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                :disabled="pendingRowFill == null"
                @click="pendingRowFill != null && applyDataStartRow(pendingRowFill)"
              >
                {{ t("template.bringFromSelection") }}
              </Button>
              <Button variant="outline" size="sm" :disabled="!sample" @click="detectHeader">
                {{ t("template.detectHeader") }}
              </Button>
              <Button variant="ghost" size="sm" @click="restoreHeaderStart">{{ t("template.restore") }}</Button>
            </div>
            <p v-if="pendingRowFill != null" class="text-sm text-muted-foreground">
              {{ t("template.selectionRow", { n: pendingRowFill }) }}
            </p>
          </div>
        </TabsContent>

        <TabsContent value="mapping">
          <div class="space-y-3" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <div v-if="!sample" class="text-sm text-muted-foreground">
              {{ t("template.noSampleForMapping") }}
            </div>
            <template v-else>
              <div class="flex items-center gap-2">
                <Button variant="outline" size="sm" @click="refreshSuggest">
                  {{ t("template.rematch") }}
                </Button>
                <label class="ml-auto flex items-center gap-2 text-sm">
                  <Checkbox
                    :model-value="onlySelectedColumns"
                    @update:model-value="(checked) => (onlySelectedColumns = checked === true)"
                  />
                  {{ t("template.onlySelectedColumns") }}
                </label>
              </div>
              <table class="w-full text-sm">
                <tbody>
                  <tr
                    v-for="row in mappingRows"
                    :key="pathKey(row.column.excel_path)"
                    class="border-b"
                    :class="selectedPathKeys.has(pathKey(row.column.excel_path)) ? 'bg-accent/60' : ''"
                  >
                    <td class="py-1 pr-2">{{ pathLabel(row.column.excel_path) }}</td>
                    <td class="py-1 pr-2">
                      <Input
                        class="h-7"
                        :model-value="row.column.db_column"
                        list="db-columns"
                        :placeholder="t('template.pickColumn')"
                        @update:model-value="(value) => setColumn(row.index, String(value))"
                      />
                    </td>
                    <td class="py-1 text-muted-foreground">
                      {{ suggestionScores.get(pathKey(row.column.excel_path)) ?? "—" }}
                    </td>
                  </tr>
                </tbody>
              </table>
              <p v-if="selectedPathKeys.size" class="text-xs text-muted-foreground">
                {{ t("template.selectionColumns", { n: selectedPathKeys.size }) }}
              </p>
            </template>
            <div>
              <h3 class="mb-2 text-sm font-medium">{{ t("template.constants") }}</h3>
              <div
                v-for="(constant, index) in form.mapping.constants"
                :key="index"
                class="mb-1 grid grid-cols-[1fr_1fr_auto] items-center gap-2"
              >
                <Input
                  :model-value="constant.db_column"
                  list="db-columns"
                  :placeholder="t('template.pickColumn')"
                  @update:model-value="(value) => setConstant(index, 'db_column', String(value))"
                />
                <Input
                  :model-value="constant.value"
                  :placeholder="t('common.value')"
                  @update:model-value="(value) => setConstant(index, 'value', String(value))"
                />
                <Button variant="ghost" size="sm" @click="removeConstant(index)">{{ t("common.remove") }}</Button>
              </div>
              <Button variant="outline" size="sm" @click="addConstant">{{ t("common.add") }}</Button>
            </div>
            <div>
              <h3 class="mb-2 text-sm font-medium">{{ t("template.unpivot") }}</h3>
              <UnpivotEditor v-model="form.mapping.unpivot" :columns="dbColumns" />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="rules">
          <div class="space-y-3" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <p v-if="activeLeafPathKey" class="text-xs text-muted-foreground">
              {{ t("template.selectedColumn") }}：{{ pathLabel(activeLeafPathKey.split("\u0000")) }}
              <span v-if="activeDbColumn"> → {{ activeDbColumn }}</span>
            </p>
            <RuleOverridesEditor v-model="form.rule_overrides" :columns="dbColumns" />
          </div>
        </TabsContent>

        <TabsContent value="synonyms">
          <div class="space-y-3" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <p v-if="activeLeafPathKey" class="text-xs text-muted-foreground">
              {{ t("template.selectedColumn") }}：{{ pathLabel(activeLeafPathKey.split("\u0000")) }}
              <span v-if="activeDbColumn"> → {{ activeDbColumn }}</span>
            </p>
            <SynonymGroups :workspace-id="workspaceId" />
          </div>
        </TabsContent>
      </Tabs>
    </SheetContent>
  </Sheet>

  <!-- 建表语句预览对话框 -->
  <Dialog :open="ddlDialogOpen" @update:open="(value) => (ddlDialogOpen = value)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ t("template.createTableTitle") }}</DialogTitle>
        <DialogDescription>{{ autoTableName }}</DialogDescription>
      </DialogHeader>
      <div class="space-y-3">
        <table class="w-full text-sm">
          <tbody>
            <tr v-for="column in inferredColumns" :key="column.db_column" class="border-b">
              <td class="py-1 pr-2">{{ column.db_column }}</td>
              <td class="py-1 pr-2">{{ column.db_type }}</td>
              <td class="py-1">{{ column.nullable ? t("common.yes") : t("common.no") }}</td>
            </tr>
          </tbody>
        </table>
        <pre class="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">{{ ddlPreview }}</pre>
        <Alert v-if="tableExists" variant="destructive">
          <AlertDescription>
            {{ t("template.tableExists", { table: existingTable?.table ?? autoTableName }) }}
          </AlertDescription>
        </Alert>
      </div>
      <DialogFooter>
        <Button v-if="tableExists" variant="outline" @click="useExistingTable">
          {{ t("template.useExistingTable") }}
        </Button>
        <Button variant="outline" @click="ddlDialogOpen = false">{{ t("common.cancel") }}</Button>
        <Button :disabled="creating || tableExists" @click="createTable">
          {{ t("template.createTable") }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 放弃未保存修改确认 -->
  <AlertDialog :open="discardOpen" @update:open="(value) => { if (!value) resolveDiscard(false); }">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ t("template.discardConfirmTitle") }}</AlertDialogTitle>
        <AlertDialogDescription>{{ t("template.discardConfirm") }}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="resolveDiscard(false)">{{ t("common.cancel") }}</AlertDialogCancel>
        <AlertDialogAction @click="resolveDiscard(true)">{{ t("common.confirm") }}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { ChevronDown, FileSpreadsheet, Pencil, Plus, SlidersHorizontal, Upload, Zap } from "@lucide/vue";
import { toast } from "vue-sonner";

import { ApiError, api } from "@/api/client";
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import RuleOverridesEditor from "@/components/template/RuleOverridesEditor.vue";
import SynonymGroups from "@/components/template/SynonymGroups.vue";
import UnpivotEditor from "@/components/template/UnpivotEditor.vue";
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
  type ViewerSelection,
} from "@/features/excel-viewer/useExcelViewer";
import {
  computeButtonStates,
  initialModel,
  transition,
  viewerEditable,
  type TemplatePageModel,
} from "@/features/template/state";
import { errorMessage } from "@/lib/errors";
import { pathLabel } from "@/features/header/tree";
import type {
  Datasource,
  Mapping,
  RuleOverride,
  Strategy,
  Suggestion,
  TableInfo,
  TableSchema,
  Template,
} from "@/lib/types";
import type { ViewerApi } from "ooxml-excel-editor/core";

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

function blankForm(): TemplateForm {
  return {
    name: "",
    description: "",
    datasource_id: null,
    target_schema: "",
    target_table: "",
    sheet: "Sheet1",
    header_start_row: 1,
    header_row_count: 1,
    strategy: "APPEND",
    business_keys: [],
    scope_columns: [],
    mapping: { columns: [], unpivot: null, constants: [] },
    rule_overrides: [],
  };
}

const AUTO_TABLE_VALUE = "__auto__";

/* ---------- 页面状态机 ---------- */
const pageModel = ref<TemplatePageModel>(initialModel);
const readOnly = computed(() => pageModel.value.state === "S1");

/* ---------- 表单与快照（脏判断） ---------- */
const form = ref<TemplateForm>(blankForm());
const savedSnapshot = ref(JSON.stringify(form.value));
const dirty = computed(() => JSON.stringify(form.value) !== savedSnapshot.value);
const valid = computed(
  () =>
    form.value.name.trim() !== "" &&
    form.value.datasource_id != null &&
    form.value.target_table !== "" &&
    form.value.mapping.columns.some((column) => column.db_column.trim() !== ""),
);
const buttonStates = computed(() =>
  computeButtonStates(pageModel.value, { valid: valid.value, dirty: dirty.value, saving: saving.value }),
);
const saveDisabledReason = computed(() => (buttonStates.value.save ? "" : t("template.saveDisabled")));
const stateBadge = computed(() => {
  switch (pageModel.value.state) {
    case "S0":
      return { text: t("template.stateUnselected"), cls: "bg-muted text-muted-foreground" };
    case "S1":
      return { text: t("template.stateViewing"), cls: "bg-muted text-muted-foreground" };
    case "S2":
      return { text: t("template.stateNew"), cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-100" };
    case "S3":
      return {
        text: t("template.stateEditing"),
        cls: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100",
      };
  }
});

/* ---------- 列表与元数据 ---------- */
const templates = ref<Template[]>([]);
const datasources = ref<Datasource[]>([]);
const tables = ref<TableInfo[]>([]);
const schemaColumns = ref<TableSchema["columns"]>([]);
const suggestions = ref<Suggestion[]>([]);
const error = ref("");
const saving = ref(false);
const drawerOpen = ref(false);
const activeTab = ref("start-row");
const onlySelectedColumns = ref(false);
const pendingRowFill = ref<number | null>(null);

/* ---------- 样例与 Viewer ---------- */
const viewer = useExcelViewer();
const errorCells = ref<ReadonlySet<string>>(new Set());
const sample = ref<AdaptedSheet | null>(null);
const sampleFileName = ref("");

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

/* ---------- 智能建表 ---------- */
const autoTableMode = ref(false);
const autoTableName = ref("");
const ddlPreview = ref("");
const inferredColumns = ref<{ db_column: string; db_type: string; nullable: boolean }[]>([]);
const ddlDialogOpen = ref(false);
const inferring = ref(false);
const creating = ref(false);
const tableExists = ref(false);
const existingTable = ref<{ schema: string; table: string } | null>(null);

/* ---------- 放弃确认 ---------- */
const discardOpen = ref(false);
let discardResolve: ((ok: boolean) => void) | null = null;

const templateSelectValue = computed(() => {
  if (pageModel.value.state === "S2") return "new";
  if (pageModel.value.selectedId != null) return String(pageModel.value.selectedId);
  return "";
});

const datasourceIdStr = computed({
  get: () => (form.value.datasource_id == null ? "" : String(form.value.datasource_id)),
  set: (value: string) => {
    form.value = { ...form.value, datasource_id: value === "" ? null : Number(value) };
  },
});

const selectedTableIndex = computed({
  get: () => {
    const index = tables.value.findIndex(
      (table) => table.schema === form.value.target_schema && table.name === form.value.target_table,
    );
    return index === -1 ? "" : String(index);
  },
  set: (index: string) => onTableIndex(index),
});

const targetSelectValue = computed({
  get: () => (autoTableMode.value ? AUTO_TABLE_VALUE : selectedTableIndex.value),
  set: (value: string) => onTargetSelect(value),
});

const selectedDatasource = computed(
  () => datasources.value.find((source) => source.id === form.value.datasource_id) ?? null,
);

const dbColumns = computed(() => schemaColumns.value.map((column) => column.name));
const suggestionByPath = computed(() => new Map(suggestions.value.map((item) => [pathKey(item.excel_path), item])));
const suggestionScores = computed(() => {
  const scores = new Map<string, number>();
  for (const item of suggestions.value) scores.set(pathKey(item.excel_path), item.score);
  return scores;
});

/* ---------- 选区派生 ---------- */
const selectedLeafColumns = computed<Set<number>>(() => {
  const sel = viewer.selection.value;
  const cols = new Set<number>();
  if (!sel) return cols;
  if (sel.kind === "column" || sel.kind === "range") {
    for (let column = sel.range.left; column <= sel.range.right; column += 1) cols.add(column);
  } else {
    cols.add(sel.active.col);
  }
  return cols;
});
const selectedPathKeys = computed(() => {
  const keys = new Set<string>();
  if (!sample.value) return keys;
  for (const [key, column] of sample.value.leafColumns) {
    if (selectedLeafColumns.value.has(column)) keys.add(key);
  }
  return keys;
});
const activeLeafPathKey = computed<string | null>(() => {
  const sel = viewer.selection.value;
  if (!sel || !sample.value) return null;
  for (const [key, column] of sample.value.leafColumns) {
    if (column === sel.active.col) return key;
  }
  return null;
});
const activeDbColumn = computed(() => {
  if (!activeLeafPathKey.value) return "";
  const column = form.value.mapping.columns.find((item) => pathKey(item.excel_path) === activeLeafPathKey.value);
  return column?.db_column ?? "";
});
const mappingRows = computed(() =>
  form.value.mapping.columns
    .map((column, index) => ({ column, index }))
    .filter(
      ({ column }) =>
        !onlySelectedColumns.value ||
        selectedPathKeys.value.size === 0 ||
        selectedPathKeys.value.has(pathKey(column.excel_path)),
    ),
);

const dataStartRow = computed({
  get: () => form.value.header_start_row + form.value.header_row_count,
  set: (value: number) => {
    form.value = { ...form.value, header_start_row: Math.max(1, value - form.value.header_row_count) };
  },
});

function pathKey(path: string[]): string {
  return path.join("\u0000");
}

function guarded(fn: () => Promise<void> | void): void {
  void Promise.resolve()
    .then(fn)
    .catch((caught: unknown) => {
      error.value = errorMessage(caught);
    });
}

function askDiscard(): Promise<boolean> {
  discardOpen.value = true;
  return new Promise<boolean>((resolve) => {
    discardResolve = resolve;
  });
}
function resolveDiscard(ok: boolean): void {
  discardOpen.value = false;
  discardResolve?.(ok);
  discardResolve = null;
}

function resetSample(): void {
  sample.value = null;
  sampleFileName.value = "";
  pendingRowFill.value = null;
  viewer.workbook.value = null;
  viewer.sourceBuffer.value = null;
  viewer.selection.value = null;
}

function setColumn(index: number, value: string): void {
  const columns = form.value.mapping.columns.map((column, i) =>
    i === index ? { ...column, db_column: value } : column,
  );
  form.value = { ...form.value, mapping: { ...form.value.mapping, columns } };
}

function setConstant(index: number, field: "db_column" | "value", value: string): void {
  const constants = form.value.mapping.constants.map((constant, i) =>
    i === index ? { ...constant, [field]: value } : constant,
  );
  form.value = { ...form.value, mapping: { ...form.value.mapping, constants } };
}

function addConstant(): void {
  form.value = {
    ...form.value,
    mapping: { ...form.value.mapping, constants: [...form.value.mapping.constants, { db_column: "", value: "" }] },
  };
}

function removeConstant(index: number): void {
  form.value = {
    ...form.value,
    mapping: {
      ...form.value.mapping,
      constants: form.value.mapping.constants.filter((_, i) => i !== index),
    },
  };
}

function toggleIn(field: "business_keys" | "scope_columns", column: string, checked: boolean): void {
  const current = form.value[field];
  const next = checked ? [...current, column] : current.filter((item) => item !== column);
  form.value = { ...form.value, [field]: next };
}

function onTableIndex(index: string): void {
  if (index === "") return;
  const table = tables.value[Number(index)];
  if (!table) return;
  form.value = { ...form.value, target_schema: table.schema, target_table: table.name };
}

function onTargetSelect(value: unknown): void {
  if (typeof value !== "string") return;
  if (value === AUTO_TABLE_VALUE) {
    autoTableMode.value = true;
    if (!autoTableName.value) autoTableName.value = defaultTableName();
    return;
  }
  autoTableMode.value = false;
  onTableIndex(value);
}

/* ---------- 模板加载 / 状态转移 ---------- */
async function loadTemplate(id: number): Promise<void> {
  const data = await api.get<Template>(`/workspaces/${props.workspaceId}/templates/${id}`);
  resetSample();
  form.value = {
    name: data.name,
    description: data.description ?? "",
    datasource_id: data.datasource_id,
    target_schema: data.target_schema,
    target_table: data.target_table,
    sheet: data.sheet,
    header_start_row: data.header_start_row,
    header_row_count: data.header_row_count,
    strategy: data.strategy,
    business_keys: [...data.business_keys],
    scope_columns: [...data.scope_columns],
    mapping: {
      columns: (data.mapping.columns ?? []).map((column) => ({ ...column })),
      unpivot: data.mapping.unpivot ? { ...data.mapping.unpivot } : null,
      constants: (data.mapping.constants ?? []).map((constant) => ({ ...constant })),
    },
    rule_overrides: (data.rule_overrides ?? []).map((rule) => ({ ...rule })),
  };
  savedSnapshot.value = JSON.stringify(form.value);
  pageModel.value = { state: "S1", returnState: "S0", selectedId: id, previousId: null };
  drawerOpen.value = false;
}

function enterNewDraft(): void {
  resetSample();
  form.value = blankForm();
  savedSnapshot.value = JSON.stringify(form.value);
  pageModel.value = transition(pageModel.value, { type: "startNew" });
  drawerOpen.value = true;
}

async function selectTemplate(id: number): Promise<void> {
  if (id === pageModel.value.selectedId && pageModel.value.state !== "S2") return;
  if (dirty.value && (await askDiscard()) === false) return;
  resetSample();
  pageModel.value = transition(pageModel.value, { type: "select", id });
  drawerOpen.value = false;
  await router.push(`/templates/${id}`);
}

async function startNew(): Promise<void> {
  if (pageModel.value.state === "S2") return;
  if (dirty.value && (await askDiscard()) === false) return;
  enterNewDraft();
  await router.push("/templates/new");
}

function startEdit(): void {
  pageModel.value = transition(pageModel.value, { type: "startEdit" });
}

async function cancelEdit(): Promise<void> {
  if (dirty.value && (await askDiscard()) === false) return;
  const before = pageModel.value;
  pageModel.value = transition(before, { type: "cancel" });
  drawerOpen.value = false;
  if (before.state === "S3") {
    if (before.selectedId != null) await guarded(() => loadTemplate(before.selectedId as number));
  } else if (before.state === "S2") {
    if (before.returnState === "S1" && before.previousId != null) {
      await router.push(`/templates/${before.previousId}`);
    } else {
      await router.push("/templates");
    }
  }
}

async function saveTemplate(): Promise<void> {
  if (!buttonStates.value.save) return;
  saving.value = true;
  error.value = "";
  try {
    const payload = {
      name: form.value.name,
      description: form.value.description,
      datasource_id: form.value.datasource_id,
      target_schema: form.value.target_schema,
      target_table: form.value.target_table,
      sheet: form.value.sheet,
      header_start_row: form.value.header_start_row,
      header_row_count: form.value.header_row_count,
      strategy: form.value.strategy,
      business_keys: form.value.business_keys,
      scope_columns: form.value.scope_columns,
      mapping: {
        columns: form.value.mapping.columns.filter((column) => column.db_column.trim() !== ""),
        unpivot: form.value.mapping.unpivot,
        constants: form.value.mapping.constants.filter((constant) => constant.db_column.trim() !== ""),
      },
      rule_overrides: form.value.rule_overrides.filter((rule) => rule.db_column.trim() !== ""),
    };
    let savedId: number | null = null;
    if (pageModel.value.state === "S3" && pageModel.value.selectedId != null) {
      const updated = await api.put<Template>(
        `/workspaces/${props.workspaceId}/templates/${pageModel.value.selectedId}`,
        payload,
      );
      savedId = updated.id;
    } else {
      const created = await api.post<Template>(`/workspaces/${props.workspaceId}/templates`, payload);
      savedId = created.id;
    }
    if (savedId != null) {
      pageModel.value = transition(pageModel.value, { type: "saveSuccess", id: savedId });
    }
    await router.push("/templates");
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    saving.value = false;
  }
}

async function onTemplateSelect(value: unknown): Promise<void> {
  if (typeof value !== "string") return;
  if (value === "new") {
    await startNew();
    return;
  }
  const id = Number(value);
  if (!Number.isNaN(id)) await selectTemplate(id);
}

function openQuickImport(tab: string): void {
  activeTab.value = tab;
  drawerOpen.value = true;
}

/* ---------- 样例解析与建议映射 ---------- */
function adaptSheet(sheetIndex: number, applyToForm: boolean): void {
  const model = viewer.workbook.value;
  if (!model) return;
  const adapted = modelToParsedSheet(
    model,
    sheetIndex,
    form.value.header_start_row - 1,
    form.value.header_row_count,
  );
  sample.value = adapted;
  if (applyToForm && form.value.sheet !== adapted.name) {
    form.value = { ...form.value, sheet: adapted.name };
  }
}

async function resuggest(applyMapping: boolean): Promise<void> {
  if (!sample.value) return;
  const paths = sample.value.header.leaves.map((leaf) => leaf.path);
  suggestions.value =
    form.value.datasource_id && form.value.target_table
      ? await api.post<Suggestion[]>(`/workspaces/${props.workspaceId}/templates/suggest-mapping`, {
          datasource_id: form.value.datasource_id,
          target_schema: form.value.target_schema,
          target_table: form.value.target_table,
          paths,
        })
      : [];
  if (applyMapping) {
    const matched = suggestionByPath.value;
    form.value = {
      ...form.value,
      mapping: {
        ...form.value.mapping,
        columns: paths.map((path) => ({
          excel_path: path,
          db_column: matched.get(pathKey(path))?.db_column ?? "",
        })),
      },
    };
  }
}

const onSample = (event: Event) =>
  guarded(async () => {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    const model = await viewer.loadFile(file);
    sampleFileName.value = file.name;
    const idx = modelSheetIndex(model, form.value.sheet);
    const sheetIdx = idx >= 0 ? idx : (model.activeSheet ?? 0);
    if (viewer.workbook.value) viewer.workbook.value.activeSheet = sheetIdx;
    viewer.activeSheetIndex.value = sheetIdx;
    viewer.selectSheet(sheetIdx);
    const inEdit = pageModel.value.state === "S2" || pageModel.value.state === "S3";
    adaptSheet(sheetIdx, inEdit);
    await resuggest(inEdit);
  });

const onSheetChange = (payload: { index: number; name: string }) =>
  guarded(async () => {
    viewer.activeSheetIndex.value = payload.index;
    const inEdit = pageModel.value.state === "S2" || pageModel.value.state === "S3";
    adaptSheet(payload.index, inEdit);
    await resuggest(inEdit);
  });

function onSelection(payload: { range: SelectionRange; active: { row: number; col: number } }): void {
  viewer.onSelectionChange(payload);
  const sel = viewer.selection.value;
  if (sel) handleSelectionFill(sel);
}

function onViewerReady(api: ViewerApi): void {
  viewer.setViewerApi(api);
  viewer.selectSheet(viewer.activeSheetIndex.value);
}

function onViewerError(message: string): void {
  error.value = message;
}

/* ---------- 选区自动带入 ---------- */
function handleSelectionFill(sel: ViewerSelection): void {
  if (sel.kind !== "row") return;
  const excelRow = sel.range.top + 1;
  pendingRowFill.value = excelRow;
  if (drawerOpen.value && activeTab.value === "start-row" && pageModel.value.state !== "S1") {
    const before = form.value.header_start_row;
    applyDataStartRow(excelRow);
    if (form.value.header_start_row !== before) {
      toast.success(t("template.rowApplied", { n: excelRow }));
    }
  }
}

function applyDataStartRow(excelRow: number): void {
  const next = Math.max(1, excelRow - form.value.header_row_count);
  if (form.value.header_start_row !== next) {
    form.value = { ...form.value, header_start_row: next };
  }
  pendingRowFill.value = null;
}

function applyAndGoToStartRow(): void {
  if (pendingRowFill.value == null) return;
  applyDataStartRow(pendingRowFill.value);
  activeTab.value = "start-row";
}

function restoreHeaderStart(): void {
  try {
    const snapshot = JSON.parse(savedSnapshot.value) as TemplateForm;
    form.value = {
      ...form.value,
      header_start_row: snapshot.header_start_row,
      header_row_count: snapshot.header_row_count,
    };
  } catch {
    // 快照损坏时不做任何事
  }
  pendingRowFill.value = null;
}

async function detectHeader(): Promise<void> {
  const model = viewer.workbook.value;
  if (!model) return;
  const sheet = model.sheets[viewer.activeSheetIndex.value];
  if (!sheet) return;
  const rangeData = viewer.getRangeData(
    viewer.activeSheetIndex.value,
    { top: 0, left: 0, bottom: 9, right: Math.max(0, sheet.dimension.cols - 1) },
    { format: false },
  );
  let bestRow = 0;
  let bestCount = -1;
  rangeData.forEach((row, i) => {
    const count = row.filter((value) => typeof value === "string" && value.trim() !== "").length;
    if (count > bestCount) {
      bestCount = count;
      bestRow = i;
    }
  });
  if (bestCount <= 0) {
    toast.error(t("template.noHeaderDetected"));
    return;
  }
  form.value = { ...form.value, header_start_row: bestRow + 1 };
  toast.success(t("template.headerDetected", { n: bestRow + 1 }));
}

function refreshSuggest(): void {
  guarded(() => resuggest(true));
}

/* ---------- 智能建表 ---------- */
function defaultTableName(): string {
  const base = form.value.name.toLowerCase().replace(/[^a-z0-9_]/g, "");
  if (base) return base;
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `import_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
}

function inferColumnsPayload(): { db_column: string; samples: unknown[] }[] {
  const columns: { db_column: string; samples: unknown[] }[] = [];
  const rows = sample.value?.rows ?? [];
  const takeSamples = (key: string): unknown[] => rows.slice(0, 200).map((row) => row[key]);
  for (const column of form.value.mapping.columns) {
    if (!column.db_column.trim()) continue;
    columns.push({ db_column: column.db_column.trim(), samples: takeSamples(pathKey(column.excel_path)) });
  }
  for (const constant of form.value.mapping.constants) {
    if (!constant.db_column.trim()) continue;
    columns.push({ db_column: constant.db_column.trim(), samples: [constant.value] });
  }
  const unpivot = form.value.mapping.unpivot;
  if (unpivot) {
    for (const measure of unpivot.measures) {
      if (!measure.db_column.trim()) continue;
      const samples: unknown[] = [];
      for (const group of unpivot.groups) {
        samples.push(...takeSamples(pathKey([...group.match_prefix, measure.excel_leaf])));
      }
      columns.push({ db_column: measure.db_column.trim(), samples: samples.slice(0, 200) });
    }
  }
  return columns;
}

const canPreviewDdl = computed(() => {
  if (!autoTableMode.value || !form.value.datasource_id) return false;
  if (selectedDatasource.value?.db_type !== "postgres") return false;
  if (form.value.strategy === "UPSERT" && form.value.business_keys.length === 0) return false;
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(autoTableName.value)) return false;
  return inferColumnsPayload().length > 0;
});

const previewHint = computed(() => {
  if (!autoTableMode.value) return "";
  if (selectedDatasource.value?.db_type !== "postgres") return t("template.autoTablePgOnly");
  if (form.value.strategy === "UPSERT" && form.value.business_keys.length === 0) {
    return t("template.upsertNeedsKeys");
  }
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(autoTableName.value)) return t("template.invalidIdentifier");
  return "";
});

async function previewDdl(): Promise<void> {
  if (!form.value.datasource_id) return;
  inferring.value = true;
  error.value = "";
  try {
    const res = await api.post<{
      columns: { db_column: string; db_type: string; nullable: boolean }[];
      ddl: string;
    }>(`/workspaces/${props.workspaceId}/datasources/${form.value.datasource_id}/tables/infer`, {
      target_schema: form.value.target_schema || "public",
      table_name: autoTableName.value,
      columns: inferColumnsPayload(),
      unique_keys: form.value.business_keys,
    });
    inferredColumns.value = res.columns;
    ddlPreview.value = res.ddl;
    tableExists.value = false;
    existingTable.value = null;
    ddlDialogOpen.value = true;
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    inferring.value = false;
  }
}

async function createTable(): Promise<void> {
  if (!form.value.datasource_id) return;
  creating.value = true;
  error.value = "";
  try {
    const res = await api.post<TableInfo>(
      `/workspaces/${props.workspaceId}/datasources/${form.value.datasource_id}/tables/auto-create`,
      {
        target_schema: form.value.target_schema || "public",
        target_table: autoTableName.value,
        columns: inferredColumns.value,
        unique_keys: form.value.business_keys,
      },
    );
    ddlDialogOpen.value = false;
    autoTableMode.value = false;
    tables.value = await api.get<TableInfo[]>(`/datasources/${form.value.datasource_id}/tables`);
    form.value = { ...form.value, target_schema: res.schema, target_table: res.name };
    toast.success(t("template.tableCreated"));
    // 注意：新表是按当前映射建出来的，映射本身依然有效；但新表没有列注释，
    // 再跑一次建议映射会返回空并把映射清空（resuggest(true) 会覆写），所以这里
    // 只刷新建议分数显示，不动映射。
    await guarded(() => resuggest(false));
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === "TABLE_EXISTS") {
      tableExists.value = true;
      const params = caught.params as { schema?: string; table?: string };
      existingTable.value = {
        schema: String(params.schema ?? ""),
        table: String(params.table ?? autoTableName.value),
      };
    } else {
      error.value = errorMessage(caught);
    }
  } finally {
    creating.value = false;
  }
}

async function useExistingTable(): Promise<void> {
  if (!existingTable.value || !form.value.datasource_id) return;
  ddlDialogOpen.value = false;
  autoTableMode.value = false;
  form.value = {
    ...form.value,
    target_schema: existingTable.value.schema,
    target_table: existingTable.value.table,
  };
  // 同 createTable：只刷新建议分数，不覆写映射（否则无注释的表会把映射清空）。
  await guarded(() => resuggest(false));
}

/* ---------- 监听 ---------- */
watch(
  () => props.workspaceId,
  (id) => {
    guarded(async () => {
      datasources.value = id == null ? [] : await api.get<Datasource[]>("/datasources");
      templates.value = id == null ? [] : await api.get<Template[]>(`/workspaces/${id}/templates`);
    });
  },
  { immediate: true },
);

watch(
  () => route.params.id,
  (id) => {
    guarded(async () => {
      if (props.workspaceId == null) return;
      if (id === undefined) {
        if (pageModel.value.state !== "S2") enterNewDraft();
        return;
      }
      await loadTemplate(Number(id));
    });
  },
  { immediate: true },
);

watch(
  () => form.value.datasource_id,
  (id) => {
    guarded(async () => {
      tables.value = id == null ? [] : await api.get<TableInfo[]>(`/datasources/${id}/tables`);
    });
  },
);

watch(
  () => [form.value.datasource_id, form.value.target_schema, form.value.target_table] as const,
  ([datasourceId, schema, table]) => {
    guarded(async () => {
      if (!datasourceId || !table) {
        schemaColumns.value = [];
        return;
      }
      const data = await api.get<TableSchema>(
        `/datasources/${datasourceId}/tables/${encodeURIComponent(table)}/schema`,
        { schema },
      );
      schemaColumns.value = data.columns;
    });
  },
  { immediate: true },
);

let headerResuggestTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  // 注意：这里必须用字符串 key 做比较。之前用数组 [start, count] 作 watch 源时，
  // 每次求值都产生新数组引用，Vue 的 Object.is 比较恒为不等——于是 form.value 的
  // 任何一次重赋值（例如 resuggest(true) 回填映射）都会再次触发本 watcher，
  // 400ms 后又跑一次 resuggest(true)，形成无限循环（实测约每 430ms 一个
  // suggest-mapping 请求）；切到无注释的新表后循环里某次返回空还会把映射清空。
  () => `${form.value.header_start_row}/${form.value.header_row_count}`,
  () => {
    if (!viewer.workbook.value || !sample.value) return;
    adaptSheet(viewer.activeSheetIndex.value, false);
    clearTimeout(headerResuggestTimer);
    headerResuggestTimer = setTimeout(() => {
      guarded(() => resuggest(pageModel.value.state === "S2" || pageModel.value.state === "S3"));
    }, 400);
  },
);
</script>
