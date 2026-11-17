<template>
  <!-- 停靠栏：模板下拉 + 新建 + 样例 chip + 状态徽章 + 快速导入 + 上传 + 编辑/配置/取消/保存 -->
  <DockBar>
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
  </DockBar>

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
    <!-- 新建/编辑入口：先选/上传样例，再做基础配置；样例上传后自动进入正常编辑器视图 -->
    <div v-if="showEntry" class="space-y-6 rounded-lg border p-6">
      <div>
        <h2 class="text-lg font-semibold">
          {{ pageModel.state === "S2" ? t("template.entryTitleNew") : t("template.entryTitleEdit") }}
        </h2>
        <p v-if="pageModel.state === 'S3'" class="mt-1 text-sm text-muted-foreground">
          {{ t("template.entryKeepData") }}
        </p>
      </div>

      <section class="space-y-2">
        <h3 class="text-sm font-medium">
          {{ pageModel.state === "S3" ? t("template.entryStep1Replace") : t("template.entryStep1") }}
        </h3>
        <p class="text-sm text-muted-foreground">{{ t("template.entryStep1Hint") }}</p>
        <label
          class="inline-flex h-9 cursor-pointer items-center rounded-md border px-3 text-sm hover:bg-accent"
        >
          <Upload class="mr-1 h-4 w-4" />{{ t("template.uploadSample") }}
          <input type="file" accept=".xlsx" class="hidden" @change="onSample" />
        </label>
      </section>

      <Separator />

      <section class="space-y-3">
        <h3 class="text-sm font-medium">{{ t("template.entryStep2") }}</h3>
        <p class="text-sm text-muted-foreground">{{ t("template.entryStep2Hint") }}</p>
        <div class="grid max-w-2xl grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label>{{ t("common.name") }}</Label>
            <Input v-model="form.name" />
          </div>
          <div class="space-y-1.5">
            <Label>{{ t("common.description") }}</Label>
            <Input v-model="form.description" />
          </div>
          <div class="space-y-1.5">
            <Label>{{ t("datasource.title") }}</Label>
            <Select v-model="datasourceIdStr">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="source in datasources" :key="source.id" :value="String(source.id)">
                  {{ source.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label>{{ t("template.target") }}</Label>
            <Select :model-value="targetSelectValue" @update:model-value="onTargetSelect">
              <SelectTrigger class="w-full"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="(table, index) in tables" :key="table.name" :value="String(index)">
                  {{ table.schema ? `${table.schema}.${table.name}` : table.name }}
                </SelectItem>
                <SelectSeparator />
                <SelectItem :value="AUTO_TABLE_VALUE">{{ t("template.autoTable") }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label>{{ t("template.strategy") }}</Label>
            <Select v-model="form.strategy">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="APPEND">{{ t("strategy.APPEND") }}</SelectItem>
                <SelectItem value="UPSERT">{{ t("strategy.UPSERT") }}</SelectItem>
                <SelectItem value="REPLACE_SCOPE">{{ t("strategy.REPLACE_SCOPE") }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div>
          <Button variant="outline" size="sm" @click="drawerOpen = true">
            <SlidersHorizontal class="mr-1 h-4 w-4" />{{ t("template.entryOpenConfig") }}
          </Button>
        </div>
      </section>

      <div class="flex justify-end">
        <Button @click="entryDismissed = true">{{ t("template.entryEnterEditor") }}</Button>
      </div>
    </div>

    <template v-else>
    <label
      class="flex min-h-64 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-muted-foreground"
    >
      <FileSpreadsheet class="h-8 w-8" />
      <span>{{ t("template.uploadSample") }}</span>
      <span class="text-xs">{{ t("template.sampleHint") }}</span>
      <input type="file" accept=".xlsx" class="hidden" @change="onSample" />
    </label>
    <div v-if="form.mapping.columns.length">
      <h2 class="mb-3 text-sm font-medium">{{ t("template.mapping") }}</h2>
      <table class="w-full text-sm">
        <tbody>
          <tr v-for="(column, index) in form.mapping.columns" :key="pathKey(column.excel_path)" class="border-b">
            <td class="py-1.5 pr-2">{{ pathLabel(column.excel_path) }}</td>
            <td class="py-1.5 pr-2">
              <Input
                class="h-7"
                :model-value="column.db_column"
                list="db-columns"
                :placeholder="t('template.pickColumn')"
                :disabled="readOnly"
                @update:model-value="(value) => setColumn(index, String(value))"
              />
            </td>
            <td class="py-1.5 text-muted-foreground">
              {{ suggestionScores.get(pathKey(column.excel_path)) ?? "—" }}
            </td>
          </tr>
        </tbody>
      </table>
      <datalist id="db-columns">
        <option v-for="column in dbColumns" :key="column" :value="column" />
      </datalist>
    </div>
    </template>
  </div>

  <!-- 设定窗：外壳见 PageDrawer（非模态、640px、顶边推到停靠栏底边之下，z-20）。 -->
  <PageDrawer v-model:open="drawerOpen">
    <template #title>{{ form.name || t("template.create") }}</template>
      <div
        v-if="showMissingBadges"
        class="flex flex-wrap items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm"
      >
        <span class="font-medium text-destructive">{{ t("template.missingTitle") }}</span>
        <Badge v-for="key in missingRequired" :key="key" variant="destructive">
          {{ t(`template.missing.${key}`) }}
        </Badge>
      </div>
      <div
        v-if="pendingRowFill != null && activeTab !== 'start-row' && pageModel.state !== 'S1'"
        class="flex items-center justify-between rounded-md bg-accent px-3 py-2.5 text-sm"
      >
        <span>{{ t("template.selectionRow", { n: pendingRowFill }) }}</span>
        <Button size="sm" variant="outline" @click="applyAndGoToStartRow">
          {{ t("template.bringFromSelection") }}
        </Button>
      </div>

      <div class="space-y-5" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
        <DrawerSection :title="t('template.basicInfo')">
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <Label>{{ t("common.name") }}</Label>
              <Input v-model="form.name" />
            </div>
            <div class="space-y-1.5">
              <Label>{{ t("common.description") }}</Label>
              <Input v-model="form.description" />
            </div>
            <div class="space-y-1.5">
              <Label>{{ t("datasource.title") }}</Label>
              <Select v-model="datasourceIdStr">
                <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="source in datasources" :key="source.id" :value="String(source.id)">
                    {{ source.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-1.5">
              <Label>{{ t("template.target") }}</Label>
              <Select :model-value="targetSelectValue" @update:model-value="onTargetSelect">
                <SelectTrigger class="w-full"><SelectValue placeholder="—" /></SelectTrigger>
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
          <div v-if="autoTableMode" class="mt-3 space-y-3 rounded-md border bg-muted/40 p-4">
            <div class="space-y-1.5">
              <Label>{{ t("template.autoTableName") }}</Label>
              <Input v-model="autoTableName" />
            </div>
            <p v-if="previewHint" class="text-xs text-muted-foreground">{{ previewHint }}</p>
            <Button variant="outline" size="sm" :disabled="!canPreviewDdl || inferring" @click="previewDdl">
              {{ t("template.previewDdl") }}
            </Button>
          </div>
          <div class="mt-3 grid grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <Label>{{ t("template.sheet") }}</Label>
              <Input v-model="form.sheet" />
            </div>
          </div>
        </DrawerSection>

        <Separator />

        <DrawerSection :title="t('template.strategy')">
          <Select v-model="form.strategy">
            <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="APPEND">{{ t("strategy.APPEND") }}</SelectItem>
              <SelectItem value="UPSERT">{{ t("strategy.UPSERT") }}</SelectItem>
              <SelectItem value="REPLACE_SCOPE">{{ t("strategy.REPLACE_SCOPE") }}</SelectItem>
            </SelectContent>
          </Select>
          <div class="mt-3 space-y-1.5">
            <Label>{{ t("template.businessKeys") }}</Label>
            <div class="flex flex-wrap gap-2">
              <label v-for="column in dbColumns" :key="column" class="flex items-center gap-1 text-sm">
                <Checkbox
                  :model-value="form.business_keys.includes(column)"
                  @update:model-value="(checked) => toggleIn('business_keys', column, checked === true)"
                />
                {{ column }}
              </label>
            </div>
          </div>
          <div v-if="form.strategy === 'REPLACE_SCOPE'" class="mt-3 space-y-1.5">
            <Label>{{ t("template.scopeColumns") }}</Label>
            <div class="flex flex-wrap gap-2">
              <label v-for="column in dbColumns" :key="column" class="flex items-center gap-1 text-sm">
                <Checkbox
                  :model-value="form.scope_columns.includes(column)"
                  @update:model-value="(checked) => toggleIn('scope_columns', column, checked === true)"
                />
                {{ column }}
              </label>
            </div>
          </div>
          <p v-if="form.strategy === 'UPSERT' && !form.business_keys.length" class="mt-2 text-xs text-muted-foreground">
            {{ t("template.upsertNeedsKeys") }}
          </p>
        </DrawerSection>
      </div>

      <Separator />

      <Tabs v-model="activeTab" class="w-full">
        <TabsList class="grid w-full grid-cols-4">
          <TabsTrigger value="start-row">{{ t("template.quickStartRow") }}</TabsTrigger>
          <TabsTrigger value="mapping">{{ t("template.quickMapping") }}</TabsTrigger>
          <TabsTrigger value="rules">{{ t("template.rules") }}</TabsTrigger>
          <TabsTrigger value="synonyms">{{ t("template.synonyms") }}</TabsTrigger>
        </TabsList>

        <TabsContent value="start-row" class="pt-4">
          <div class="space-y-4" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <div class="grid grid-cols-3 gap-3">
              <div class="space-y-1.5">
                <Label>{{ t("template.headerStart") }}</Label>
                <Input v-model.number="form.header_start_row" type="number" min="1" />
              </div>
              <div class="space-y-1.5">
                <Label>{{ t("template.headerRows") }}</Label>
                <Input v-model.number="form.header_row_count" type="number" min="1" max="10" />
              </div>
              <div class="space-y-1.5">
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

        <TabsContent value="mapping" class="pt-4">
          <div class="space-y-4" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
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
              <MappingTable
                :rows="mappingTableRows"
                @update:db-column="({ index, value }) => setColumn(index, value)"
              />
              <p v-if="selectedPathKeys.size" class="text-xs text-muted-foreground">
                {{ t("template.selectionColumns", { n: selectedPathKeys.size }) }}
              </p>
            </template>
            <DrawerSection :title="t('template.constants')">
              <div
                v-for="(constant, index) in form.mapping.constants"
                :key="index"
                class="mb-2 grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2"
              >
                <Input
                  :model-value="constant.db_column"
                  list="db-columns"
                  :placeholder="t('template.pickColumn')"
                  @update:model-value="(value) => setConstant(index, 'db_column', String(value))"
                />
                <Input
                  :model-value="constant.value"
                  :placeholder="
                    constant.require_input ? t('template.constantDefault') : t('common.value')
                  "
                  @update:model-value="(value) => setConstant(index, 'value', String(value))"
                />
                <label class="flex shrink-0 items-center gap-1 text-sm whitespace-nowrap">
                  <Checkbox
                    :model-value="constant.require_input === true"
                    @update:model-value="(checked) => setConstantFlag(index, 'require_input', checked === true)"
                  />
                  {{ t("template.requireInput") }}
                </label>
                <Button variant="ghost" size="sm" @click="removeConstant(index)">{{ t("common.remove") }}</Button>
              </div>
              <Button variant="outline" size="sm" @click="addConstant">{{ t("common.add") }}</Button>
            </DrawerSection>
            <DrawerSection :title="t('template.unpivot')">
              <UnpivotEditor v-model="form.mapping.unpivot" :columns="dbColumns" />
            </DrawerSection>
          </div>
        </TabsContent>

        <TabsContent value="rules" class="pt-4">
          <div class="space-y-4" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <p v-if="activeLeafPathKey" class="text-xs text-muted-foreground">
              {{ t("template.selectedColumn") }}：{{ pathLabel(activeLeafPathKey.split("\u0000")) }}
              <span v-if="activeDbColumn"> → {{ activeDbColumn }}</span>
            </p>
            <RuleOverridesEditor v-model="form.rule_overrides" :columns="dbColumns" />
          </div>
        </TabsContent>

        <TabsContent value="synonyms" class="pt-4">
          <div class="space-y-4" :class="readOnly ? 'pointer-events-none opacity-60' : ''">
            <p v-if="activeLeafPathKey" class="text-xs text-muted-foreground">
              {{ t("template.selectedColumn") }}：{{ pathLabel(activeLeafPathKey.split("\u0000")) }}
              <span v-if="activeDbColumn"> → {{ activeDbColumn }}</span>
            </p>
            <SynonymGroups :workspace-id="workspaceId" />
          </div>
        </TabsContent>
      </Tabs>
  </PageDrawer>

  <!-- 建表语句预览对话框 -->
  <Dialog :open="ddlDialogOpen" @update:open="(value) => (ddlDialogOpen = value)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ t("template.createTableTitle") }}</DialogTitle>
        <DialogDescription>{{ autoTableName }}</DialogDescription>
      </DialogHeader>
      <div class="space-y-4">
        <table class="w-full text-sm">
          <tbody>
            <tr v-for="column in inferredColumns" :key="column.db_column" class="border-b">
              <td class="py-1.5 pr-2">{{ column.db_column }}</td>
              <td class="py-1.5 pr-2">{{ column.db_type }}</td>
              <td class="py-1">{{ column.nullable ? t("common.yes") : t("common.no") }}</td>
            </tr>
          </tbody>
        </table>
        <pre class="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">{{ ddlPreview }}</pre>
        <p v-if="form.strategy === 'UPSERT' && !form.business_keys.length" class="text-xs text-muted-foreground">
          {{ t("template.upsertNeedsKeys") }}
        </p>
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
        <Button :disabled="createTableDisabled" @click="createTable">
          {{ t("template.createTable") }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 保存执行步骤对话框 -->
  <Dialog :open="saveDialogOpen" @update:open="(value) => { if (!value && !saving) saveDialogOpen = false; }">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>{{ t("template.saveProgressTitle") }}</DialogTitle>
      </DialogHeader>
      <div class="space-y-3">
        <div v-for="step in saveSteps" :key="step.key" class="flex items-start gap-3">
          <span class="mt-0.5">
            <Loader2 v-if="step.status === 'running'" class="h-4 w-4 animate-spin text-primary" />
            <Check v-else-if="step.status === 'done'" class="h-4 w-4 text-green-600" />
            <X v-else-if="step.status === 'failed'" class="h-4 w-4 text-destructive" />
            <span v-else class="block h-4 w-4 rounded-full border" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium">{{ step.label }}</p>
            <p
              v-if="step.detail"
              :class="[
                'text-xs break-words',
                step.status === 'failed' ? 'text-destructive' : 'text-muted-foreground',
              ]"
            >
              {{ step.detail }}
            </p>
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" :disabled="saving" @click="saveDialogOpen = false">
          {{ t("common.close") }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 放弃未保存修改确认 -->
  <AlertDialog :open="discardOpen" @update:open="onDiscardOpenChange">
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
import { Check, ChevronDown, FileSpreadsheet, Loader2, Pencil, Plus, SlidersHorizontal, Upload, X, Zap } from "@lucide/vue";
import { toast } from "vue-sonner";

import { ApiError, api } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import DockBar from "@/components/layout/DockBar.vue";
import DrawerSection from "@/components/layout/DrawerSection.vue";
import PageDrawer from "@/components/layout/PageDrawer.vue";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import MappingTable from "@/components/template/MappingTable.vue";
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
  missingRequiredFields,
  shouldShowEntry,
  transition,
  viewerEditable,
  type TemplatePageModel,
} from "@/features/template/state";
import { errorMessageWithDetail } from "@/lib/errors";
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
/** 与必填缺失 Badge 同源：valid = 清单为空。 */
const missingRequired = computed(() =>
  // 自动建表模式下目标表就是待创建的表名：填好表名即算满足，保存时再自动建表。
  missingRequiredFields({
    ...form.value,
    target_table: autoTableMode.value ? autoTableName.value : form.value.target_table,
  }),
);
const showMissingBadges = computed(
  () => (pageModel.value.state === "S2" || pageModel.value.state === "S3") && missingRequired.value.length > 0,
);
const valid = computed(() => missingRequired.value.length === 0);
const buttonStates = computed(() =>
  computeButtonStates(pageModel.value, { valid: valid.value, dirty: dirty.value, saving: saving.value }),
);
const saveDisabledReason = computed(() => {
  if (buttonStates.value.save) return "";
  if (missingRequired.value.length > 0) {
    return t("template.saveDisabledMissing", {
      list: missingRequired.value.map((key) => t(`template.missing.${key}`)).join("、"),
    });
  }
  if (!dirty.value) return t("template.saveNoChanges");
  return t("template.saveDisabled");
});
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

/** 保存时的执行步骤：自动建表模式下先建表再保存，否则只有保存一步。 */
type SaveStepStatus = "pending" | "running" | "done" | "failed";
interface SaveStep {
  key: "create-table" | "save-template";
  label: string;
  status: SaveStepStatus;
  detail: string;
}
const saveSteps = ref<SaveStep[]>([]);
const saveDialogOpen = ref(false);

function setSaveStep(key: SaveStep["key"], status: SaveStepStatus, detail = ""): void {
  const step = saveSteps.value.find((item) => item.key === key);
  if (step) {
    step.status = status;
    step.detail = detail;
  }
}
const drawerOpen = ref(false);
const activeTab = ref("start-row");
const onlySelectedColumns = ref(false);
const pendingRowFill = ref<number | null>(null);

/** 入口面板是否被用户点“进入编辑器”跳过；切模板/新建时由 resetSample 复位。 */
const entryDismissed = ref(false);

/* ---------- 样例与 Viewer ---------- */
const viewer = useExcelViewer();
const errorCells = ref<ReadonlySet<string>>(new Set());
const sample = ref<AdaptedSheet | null>(null);
const sampleFileName = ref("");

const showEntry = computed(() =>
  shouldShowEntry(pageModel.value, {
    hasSample: viewer.workbook.value != null,
    dismissed: entryDismissed.value,
  }),
);

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

/** 业务键/范围列等复选框的候选列：已有表时取表结构；自动建表模式下表还不
 * 存在，取推断列清单（映射列 + 常量 + 度量列 + 维度列），否则 UPSERT 的业务键
 * 与 REPLACE_SCOPE 的范围列在自动建表模式下无从选择。 */
const dbColumns = computed(() =>
  autoTableMode.value
    ? inferColumnsPayload().map((column) => column.db_column)
    : schemaColumns.value.map((column) => column.name),
);
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
/** 供 MappingTable 用的行：分数无建议时为 null（表内显示“—”），选中列高亮。 */
const mappingTableRows = computed(() =>
  mappingRows.value.map(({ column, index }) => ({
    key: pathKey(column.excel_path),
    index,
    excelLabel: pathLabel(column.excel_path),
    dbColumn: column.db_column,
    score: suggestionScores.value.get(pathKey(column.excel_path)) ?? null,
    highlighted: selectedPathKeys.value.has(pathKey(column.excel_path)),
  })),
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
      error.value = errorMessageWithDetail(caught);
    });
}

function askDiscard(): Promise<boolean> {
  discardOpen.value = true;
  return new Promise<boolean>((resolve) => {
    discardResolve = resolve;
  });
}
function resolveDiscard(ok: boolean): void {
  // 已结算过（例如确认点击已先结算）时不再重复结算。
  if (discardResolve === null) return;
  discardOpen.value = false;
  discardResolve(ok);
  discardResolve = null;
}

/**
 * 对话框 open 变化：与导入页 askScope 同一竞态（见 ImportPage.vue 的
 * onScopeOpenChange）：Radix 先触发 update:open、再触发按钮自身的 click，
 * 立即以 false 结算会吞掉确认点击的 true；推迟到微任务再结算。
 */
function onDiscardOpenChange(open: boolean): void {
  if (open) return;
  queueMicrotask(() => resolveDiscard(false));
}

function resetSample(): void {
  sample.value = null;
  sampleFileName.value = "";
  pendingRowFill.value = null;
  entryDismissed.value = false;
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

function setConstantFlag(index: number, field: "require_input", value: boolean): void {
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
    // 切到自动建表后，之前选过的目标表就不再是本次保存的目标：清掉，避免保存时
    // 拿着一张旧表去校验（之前因此出现过“模板配置不合法”却看不出原因的情况）。
    form.value = { ...form.value, target_table: "" };
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
  // 新建先呈现入口面板（选/上传样例 → 基础配置），不再自动打开配置抽屉。
  drawerOpen.value = false;
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
  // 自动建表模式下保存分两步走：先在后台建表（校验 + 建表），再保存模板；
  // 用户不用再手动点“预览建表语句 / 确认建表”，执行节点在对话框里实时显示。
  const needsTable = autoTableMode.value && form.value.datasource_id != null;
  const steps: SaveStep[] = [];
  if (needsTable) {
    steps.push({
      key: "create-table",
      label: t("template.saveStepCreateTable"),
      status: "pending",
      detail: autoTableName.value,
    });
  }
  steps.push({ key: "save-template", label: t("template.saveStepSaveTemplate"), status: "pending", detail: "" });
  saveSteps.value = steps;
  saveDialogOpen.value = true;
  try {
    if (needsTable) {
      setSaveStep("create-table", "running");
      const created = await ensureAutoTableForSave();
      setSaveStep("create-table", "done", created.detail);
    }
    setSaveStep("save-template", "running");
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
    setSaveStep("save-template", "done");
    saveDialogOpen.value = false;
    if (savedId != null) {
      pageModel.value = transition(pageModel.value, { type: "saveSuccess", id: savedId });
    }
    await router.push("/templates");
  } catch (caught) {
    const message = errorMessageWithDetail(caught);
    const running = saveSteps.value.find((step) => step.status === "running");
    if (running) setSaveStep(running.key, "failed", message);
    error.value = message;
    // 对话框保持打开，让用户看清哪一步失败、为什么失败；点关闭后回到抽屉再改。
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
    // 样例已挂上：入口面板收起，进入正常编辑器视图。
    entryDismissed.value = true;
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
    // 维度列也是目标表的一列（后端 validate_template 按 mapped_columns 校验，
    // 维度列在其中）：不带它建出的表缺该列，保存时报 TEMPLATE_INVALID。
    // 样本取各分组的维度值；名字若已在清单里则跳过，后端 infer 遇重名会直接报错。
    const dimension = unpivot.dimension_column.trim();
    if (dimension && !columns.some((item) => item.db_column === dimension)) {
      columns.push({ db_column: dimension, samples: unpivot.groups.map((group) => group.dimension_value) });
    }
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
  // UPSERT 未选业务键时也放开预览（infer 本身不建表，无业务键也能出 DDL）；
  // 真正建表仍被对话框里的「建表」按钮拦住（见 createTableDisabled），避免
  // 建出没有唯一约束的表、保存时再报 UNIQUE_KEY_REQUIRED。
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(autoTableName.value)) return false;
  return inferColumnsPayload().length > 0;
});

/** 对话框里「建表」按钮的禁用条件：UPSERT 没有业务键时不许建表，否则建出的表
 * 没有唯一约束、保存模板时再报 UNIQUE_KEY_REQUIRED，还留下一张孤表。 */
const createTableDisabled = computed(
  () =>
    creating.value ||
    tableExists.value ||
    (form.value.strategy === "UPSERT" && form.value.business_keys.length === 0),
);

const previewHint = computed(() => {
  if (!autoTableMode.value) return "";
  if (selectedDatasource.value?.db_type !== "postgres") return t("template.autoTablePgOnly");
  if (form.value.strategy === "UPSERT" && form.value.business_keys.length === 0) {
    return t("template.upsertNeedsKeys");
  }
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(autoTableName.value)) return t("template.invalidIdentifier");
  return "";
});

/** 推断建表列清单并取 DDL（只校验、不建表）；预览和保存自动建表共用。 */
async function runInfer(): Promise<{
  columns: { db_column: string; db_type: string; nullable: boolean }[];
  ddl: string;
}> {
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
  return res;
}

async function previewDdl(): Promise<void> {
  if (!form.value.datasource_id) return;
  inferring.value = true;
  error.value = "";
  try {
    await runInfer();
    tableExists.value = false;
    existingTable.value = null;
    ddlDialogOpen.value = true;
  } catch (caught) {
    error.value = errorMessageWithDetail(caught);
  } finally {
    inferring.value = false;
  }
}

/** 按推断出的列清单执行建表。 */
async function runAutoCreate(
  columns: { db_column: string; db_type: string; nullable: boolean }[],
): Promise<TableInfo> {
  return api.post<TableInfo>(
    `/workspaces/${props.workspaceId}/datasources/${form.value.datasource_id}/tables/auto-create`,
    {
      target_schema: form.value.target_schema || "public",
      target_table: autoTableName.value,
      columns,
      unique_keys: form.value.business_keys,
    },
  );
}

/** 建表成功后的收尾：退出自动建表模式，选中新表并刷新建议分数（不动映射）。 */
async function applyCreatedTable(res: TableInfo): Promise<void> {
  autoTableMode.value = false;
  tables.value = await api.get<TableInfo[]>(`/datasources/${form.value.datasource_id}/tables`);
  form.value = { ...form.value, target_schema: res.schema, target_table: res.name };
  // 注意：新表是按当前映射建出来的，映射本身依然有效；但新表没有列注释，
  // 再跑一次建议映射会返回空并把映射清空（resuggest(true) 会覆写），所以这里
  // 只刷新建议分数显示，不动映射。
  await guarded(() => resuggest(false));
}

/** 目标表已存在时直接使用它（与新建表同理，只刷新建议分数，不覆写映射）。 */
async function applyExistingTable(schema: string, table: string): Promise<void> {
  autoTableMode.value = false;
  form.value = { ...form.value, target_schema: schema, target_table: table };
  await guarded(() => resuggest(false));
}

/**
 * 保存时自动建表：先 infer 校验（列名、业务键都在这一步校验），再建表。
 * 表已存在时不报错，直接使用已存在表——保存时还会按真实表结构再校验一次映射。
 */
async function ensureAutoTableForSave(): Promise<{ detail: string }> {
  const inferred = await runInfer();
  try {
    const created = await runAutoCreate(inferred.columns);
    await applyCreatedTable(created);
    return {
      detail: t("template.saveStepTableCreated", { table: created.name, n: inferred.columns.length }),
    };
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === "TABLE_EXISTS") {
      const params = caught.params as { schema?: string; table?: string };
      const table = String(params.table ?? autoTableName.value);
      const schema = String(params.schema ?? form.value.target_schema ?? "public");
      await applyExistingTable(schema, table);
      return { detail: t("template.saveStepTableReused", { table }) };
    }
    throw caught;
  }
}

async function createTable(): Promise<void> {
  if (!form.value.datasource_id) return;
  creating.value = true;
  error.value = "";
  try {
    const res = await runAutoCreate(inferredColumns.value);
    ddlDialogOpen.value = false;
    await applyCreatedTable(res);
    toast.success(t("template.tableCreated"));
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === "TABLE_EXISTS") {
      tableExists.value = true;
      const params = caught.params as { schema?: string; table?: string };
      existingTable.value = {
        schema: String(params.schema ?? ""),
        table: String(params.table ?? autoTableName.value),
      };
    } else {
      error.value = errorMessageWithDetail(caught);
    }
  } finally {
    creating.value = false;
  }
}

async function useExistingTable(): Promise<void> {
  if (!existingTable.value || !form.value.datasource_id) return;
  ddlDialogOpen.value = false;
  await applyExistingTable(existingTable.value.schema, existingTable.value.table);
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
