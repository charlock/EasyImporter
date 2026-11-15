<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

import { Input } from "@/components/ui/input";
import type { ParsedSheet } from "@/features/excel/parse";
import { columnLetter } from "@/lib/utils";
import type { ColumnMapping } from "@/lib/types";

/**
 * 按 Excel 原样渲染样例工作表：列字母、行号、网格线、合并表头。
 * 数据来自 exceljs 的解析结果（ParsedSheet），exceljs 本身只有解析能力，没有展示组件。
 * 可选的映射行让每一列直接在表头下方选库字段。
 */
const props = defineProps<{
  sample: ParsedSheet;
  mappingColumns?: ColumnMapping[] | null;
  scores?: Map<string, number>;
}>();
const emit = defineEmits<{ "update:column": [index: number, dbColumn: string] }>();
const { t } = useI18n();

const PREVIEW_ROWS = 50;
const ROW_H = 28;

interface HeaderCell {
  label: string;
  colspan: number;
  rowspan: number;
}

/** 把叶子路径折成多级表头：同组相邻列合并 colspan，短路径的末级向下 rowspan。 */
const headerLevels = computed<HeaderCell[][]>(() => {
  const leaves = props.sample.header.leaves;
  const maxDepth = Math.max(0, ...leaves.map((leaf) => leaf.path.length));
  const levels: HeaderCell[][] = Array.from({ length: maxDepth }, () => []);
  leaves.forEach((leaf, index) => {
    for (let level = 0; level < maxDepth; level += 1) {
      if (level >= leaf.path.length) continue;
      const prefix = leaf.path.slice(0, level + 1).join("\u0000");
      const prev = leaves[index - 1];
      if (prev && prev.path.slice(0, level + 1).join("\u0000") === prefix) continue;
      let colspan = 0;
      for (let j = index; j < leaves.length; j += 1) {
        if (leaves[j].path.slice(0, level + 1).join("\u0000") === prefix) colspan += 1;
        else break;
      }
      const rowspan = level === leaf.path.length - 1 ? maxDepth - leaf.path.length + 1 : 1;
      levels[level].push({ label: leaf.path[level], colspan, rowspan });
    }
  });
  return levels;
});

const showMapping = computed(
  () => props.mappingColumns != null && props.mappingColumns.length === props.sample.header.leaves.length,
);
const mappingRow = computed<ColumnMapping[]>(() => (showMapping.value ? (props.mappingColumns ?? []) : []));
const previewRows = computed(() => props.sample.rows.slice(0, PREVIEW_ROWS));
const cellValue = (row: Record<string, unknown>, path: string[]): unknown =>
  row[path.join("\u0000")];
const scoreOf = (path: string[]): number | undefined => props.scores?.get(path.join("\u0000"));
</script>

<template>
  <div v-if="sample.header.leaves.length" class="space-y-2">
    <p class="text-sm text-muted-foreground">
      {{ t("template.sampleMeta", { sheet: sample.name, cols: sample.header.leaves.length, rows: sample.rows.length }) }}
      <span v-if="sample.hiddenRows">· {{ t("import.hiddenRows", { n: sample.hiddenRows }) }}</span>
    </p>
    <div class="max-h-[calc(100vh-16rem)] min-h-[280px] overflow-auto rounded-lg border">
      <table class="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <!-- 列字母行 -->
          <tr>
            <th class="sticky left-0 top-0 z-30 h-7 w-12 border-b border-r bg-muted px-1 text-center align-middle font-medium text-muted-foreground" />
            <th
              v-for="(_, index) in sample.header.leaves"
              :key="`letter-${index}`"
              class="sticky top-0 z-20 h-7 border-b border-r bg-muted px-2 text-center align-middle font-medium text-muted-foreground"
            >
              {{ columnLetter(index) }}
            </th>
          </tr>
          <!-- 多级表头 -->
          <tr v-for="(cells, level) in headerLevels" :key="level">
            <th
              class="sticky left-0 z-30 h-7 w-12 border-b border-r bg-muted px-1 text-center align-middle font-medium text-muted-foreground"
              :style="{ top: `${ROW_H * (level + 1)}px` }"
            >
              {{ level === 0 ? t("grid.rowNo") : "" }}
            </th>
            <th
              v-for="(cell, i) in cells"
              :key="i"
              :colspan="cell.colspan"
              :rowspan="cell.rowspan"
              class="sticky z-20 h-7 border-b border-r bg-muted/70 px-2 text-center align-middle font-medium"
              :style="{ top: `${ROW_H * (level + 1)}px` }"
            >
              {{ cell.label }}
            </th>
          </tr>
          <!-- 映射行 -->
          <tr v-if="showMapping">
            <th
              class="sticky left-0 z-30 border-b border-r bg-muted/30 px-1 text-center align-middle text-[11px] font-medium text-muted-foreground"
              :style="{ top: `${ROW_H * (headerLevels.length + 1)}px` }"
            >
              {{ t("template.mappingRow") }}
            </th>
            <th
              v-for="(column, index) in mappingRow"
              :key="`map-${index}`"
              class="sticky z-20 border-b border-r bg-muted/30 p-1 align-middle"
              :style="{ top: `${ROW_H * (headerLevels.length + 1)}px` }"
            >
              <Input
                class="h-7 min-w-28 text-xs"
                :model-value="column.db_column"
                list="db-columns"
                :placeholder="t('template.pickColumn')"
                @update:model-value="emit('update:column', index, String($event))"
              />
              <span v-if="scoreOf(column.excel_path) != null" class="mt-0.5 block text-[10px] leading-none text-muted-foreground">
                {{ scoreOf(column.excel_path) }} 分
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, r) in previewRows" :key="r">
            <td class="sticky left-0 z-10 w-12 border-b border-r bg-background px-1 py-1 text-center align-middle text-muted-foreground">
              {{ sample.rowNumbers[r] }}
            </td>
            <td
              v-for="leaf in sample.header.leaves"
              :key="leaf.column"
              class="whitespace-nowrap border-b border-r px-2 py-1 align-middle"
            >
              {{ cellValue(row, leaf.path) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="sample.rows.length > PREVIEW_ROWS" class="text-xs text-muted-foreground">
      {{ t("template.previewMore", { n: sample.rows.length - PREVIEW_ROWS }) }}
    </p>
  </div>
</template>
