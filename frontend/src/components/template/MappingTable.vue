<!-- 映射表（Excel 列 → 目标字段 + 分数）：从模板页“匹配数据列”Tab 抽出。
  模板页以可编辑模式使用（目标字段为 Input，改动经 update:dbColumn 发出，payload 为
  { index, value }，index 是该行在映射列数组中的下标）；导入页以只读模式在抽屉里
  展示当前模板的映射。分数无数据时显示“—”。
  datalist 由调用方提供（模板页在页面内已有一份 id="db-columns" 的 datalist），
  本组件只引用其 id，不再重复渲染，避免同一 id 出现两次。 -->
<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { Input } from "@/components/ui/input";

export interface MappingTableRow {
  /** v-for 的 key，一般取 excel_path 以 "\0" 连接。 */
  key: string;
  /** 该行在映射列数组中的下标，随 update:dbColumn 一起发出。 */
  index: number;
  /** 展示用的 Excel 列名（已由 pathLabel 处理过）。 */
  excelLabel: string;
  dbColumn: string;
  /** 建议分数；无数据时传 null/undefined，显示“—”。 */
  score?: number | null;
  /** 选中高亮（模板页：当前 Viewer 选区命中的列）。 */
  highlighted?: boolean;
}

const props = withDefaults(
  defineProps<{ rows: MappingTableRow[]; readOnly?: boolean; datalistId?: string }>(),
  { readOnly: false, datalistId: "db-columns" },
);

const emit = defineEmits<{ (e: "update:dbColumn", payload: { index: number; value: string }): void }>();

const { t } = useI18n();
</script>

<template>
  <table class="w-full text-sm">
    <thead>
      <tr class="border-b text-xs text-muted-foreground">
        <th class="pb-1.5 pr-2 text-left font-medium">{{ t("template.excelColumn") }}</th>
        <th class="pb-1.5 pr-2 text-left font-medium">{{ t("template.targetColumn") }}</th>
        <th class="pb-1.5 text-left font-medium">{{ t("template.score") }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in props.rows" :key="row.key" class="border-b" :class="row.highlighted ? 'bg-accent/60' : ''">
        <td class="py-1.5 pr-2">{{ row.excelLabel }}</td>
        <td class="py-1.5 pr-2">
          <Input
            v-if="!props.readOnly"
            class="h-7"
            :model-value="row.dbColumn"
            :list="props.datalistId"
            :placeholder="t('template.pickColumn')"
            @update:model-value="(value) => emit('update:dbColumn', { index: row.index, value: String(value) })"
          />
          <template v-else>{{ row.dbColumn || "—" }}</template>
        </td>
        <td class="py-1.5 text-muted-foreground">{{ row.score ?? "—" }}</td>
      </tr>
    </tbody>
  </table>
</template>
