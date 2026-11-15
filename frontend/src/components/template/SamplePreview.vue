<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

import type { ParsedSheet } from "@/features/excel/parse";

/** 样例文件的缩略图式预览：多级表头按合并关系折叠，前 5 行数据。 */
const props = defineProps<{ sample: ParsedSheet }>();
const { t } = useI18n();

const PREVIEW_ROWS = 5;

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

const previewRows = computed(() => props.sample.rows.slice(0, PREVIEW_ROWS));
const cellValue = (row: Record<string, unknown>, path: string[]): unknown =>
  row[path.join("\u0000")];
</script>

<template>
  <div v-if="sample.header.leaves.length" class="space-y-2">
    <p class="text-sm text-muted-foreground">
      {{ t("template.sampleMeta", { sheet: sample.name, cols: sample.header.leaves.length, rows: sample.rows.length }) }}
      <span v-if="sample.hiddenRows">· {{ t("import.hiddenRows", { n: sample.hiddenRows }) }}</span>
    </p>
    <div class="overflow-auto rounded-md border">
      <table class="w-full caption-bottom text-xs">
        <thead>
          <tr v-for="(cells, level) in headerLevels" :key="level" class="border-b bg-muted/50">
            <th
              v-if="level === 0"
              :rowspan="headerLevels.length"
              class="w-10 px-2 py-1 text-left align-middle font-medium text-muted-foreground"
            >
              {{ t("grid.rowNo") }}
            </th>
            <th
              v-for="(cell, i) in cells"
              :key="i"
              :colspan="cell.colspan"
              :rowspan="cell.rowspan"
              class="border-l px-2 py-1 text-left align-middle font-medium first:border-l-0"
            >
              {{ cell.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, r) in previewRows" :key="r" class="border-b last:border-0">
            <td class="px-2 py-1 text-muted-foreground">{{ sample.rowNumbers[r] }}</td>
            <td
              v-for="leaf in sample.header.leaves"
              :key="leaf.column"
              class="whitespace-nowrap px-2 py-1"
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
