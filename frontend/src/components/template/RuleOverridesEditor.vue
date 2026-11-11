<script setup lang="ts">
import { useI18n } from "vue-i18n";

import type { RuleOverride } from "@/lib/types";

/** 在目标表约束之上追加的校验规则。空字段表示沿用表结构推导的规则。 */
const props = defineProps<{ modelValue: RuleOverride[]; columns: string[] }>();
const emit = defineEmits<{ "update:modelValue": [value: RuleOverride[]] }>();
const { t } = useI18n();

function set(index: number, patch: Partial<RuleOverride>): void {
  emit("update:modelValue", props.modelValue.map((item, i) => (i === index ? { ...item, ...patch } : item)));
}

function setRequired(index: number, event: Event): void {
  const raw = (event.target as HTMLSelectElement).value;
  set(index, { required: raw === "" ? null : raw === "true" });
}

function setEnum(index: number, event: Event): void {
  const parts = (event.target as HTMLInputElement).value.split(/[,，]/).map((part) => part.trim()).filter(Boolean);
  set(index, { enum: parts.length ? parts : null });
}

function setText(index: number, field: "pattern" | "default", event: Event): void {
  const raw = (event.target as HTMLInputElement).value;
  set(index, { [field]: raw === "" ? null : raw });
}

function setMaxLength(index: number, event: Event): void {
  const raw = (event.target as HTMLInputElement).value;
  set(index, { max_length: raw === "" ? null : Number(raw) });
}
</script>

<template>
  <div class="card stack">
    <h2>{{ t("template.rules") }}</h2>
    <table v-if="modelValue.length" class="data">
      <thead>
        <tr>
          <th>{{ t("common.column") }}</th>
          <th>{{ t("template.ruleRequired") }}</th>
          <th>{{ t("template.ruleEnum") }}</th>
          <th>{{ t("template.rulePattern") }}</th>
          <th>{{ t("template.ruleDefault") }}</th>
          <th>{{ t("template.ruleMaxLength") }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in modelValue" :key="index">
          <td>
            <select :value="item.db_column" @change="set(index, { db_column: ($event.target as HTMLSelectElement).value })">
              <option value="">—</option>
              <option v-for="column in columns" :key="column" :value="column">{{ column }}</option>
            </select>
          </td>
          <td>
            <select :value="item.required == null ? '' : String(item.required)" @change="setRequired(index, $event)">
              <option value="">—</option>
              <option value="true">✓</option>
              <option value="false">✗</option>
            </select>
          </td>
          <td><input :value="item.enum?.join(', ') ?? ''" @change="setEnum(index, $event)" /></td>
          <td><input :value="item.pattern ?? ''" @change="setText(index, 'pattern', $event)" /></td>
          <td><input :value="item.default ?? ''" @change="setText(index, 'default', $event)" /></td>
          <td><input type="number" min="1" :value="item.max_length ?? ''" @change="setMaxLength(index, $event)" /></td>
          <td>
            <button class="ghost" @click="emit('update:modelValue', modelValue.filter((_, i) => i !== index))">
              {{ t("common.remove") }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <div>
      <button class="ghost" @click="emit('update:modelValue', [...modelValue, { db_column: '' }])">{{ t("common.add") }}</button>
    </div>
  </div>
</template>

<style scoped>
h2 { font-size: 16px; margin: 0; }
td input, td select { width: 100%; min-width: 80px; }
</style>
