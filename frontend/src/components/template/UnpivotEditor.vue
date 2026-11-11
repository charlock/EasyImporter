<script setup lang="ts">
import { useI18n } from "vue-i18n";

import type { Unpivot } from "@/lib/types";

/** 长表拆行配置。每次修改都产出新对象，由父组件替换。 */
const props = defineProps<{ modelValue: Unpivot | null; columns: string[] }>();
const emit = defineEmits<{ "update:modelValue": [value: Unpivot | null] }>();
const { t } = useI18n();

const EMPTY: Unpivot = {
  dimension_column: "",
  groups: [{ dimension_value: "", match_prefix: [] }],
  measures: [{ excel_leaf: "", db_column: "" }],
  skip_empty_measures: true,
};

function update(patch: Partial<Unpivot>): void {
  if (props.modelValue) emit("update:modelValue", { ...props.modelValue, ...patch });
}

function toggle(event: Event): void {
  emit("update:modelValue", (event.target as HTMLInputElement).checked ? { ...EMPTY } : null);
}

const splitPrefix = (text: string): string[] =>
  text.split("/").map((part) => part.trim()).filter(Boolean);

function setGroup(index: number, patch: { dimension_value?: string; match_prefix?: string[] }): void {
  if (!props.modelValue) return;
  update({ groups: props.modelValue.groups.map((group, i) => (i === index ? { ...group, ...patch } : group)) });
}

function setMeasure(index: number, patch: { excel_leaf?: string; db_column?: string }): void {
  if (!props.modelValue) return;
  update({ measures: props.modelValue.measures.map((item, i) => (i === index ? { ...item, ...patch } : item)) });
}

const value = (event: Event): string => (event.target as HTMLInputElement).value;
</script>

<template>
  <div class="card stack">
    <label class="field inline">
      <input type="checkbox" :checked="!!modelValue" @change="toggle" />
      <span>{{ t("template.enableUnpivot") }}</span>
    </label>
    <template v-if="modelValue">
      <label class="field">
        <span>{{ t("template.dimensionColumn") }}</span>
        <input
          :value="modelValue.dimension_column"
          list="db-columns"
          @input="update({ dimension_column: value($event) })"
        />
      </label>

      <strong>{{ t("template.groups") }}</strong>
      <div v-for="(group, index) in modelValue.groups" :key="`g${index}`" class="row">
        <input
          :value="group.dimension_value"
          :placeholder="t('template.dimensionValue')"
          @input="setGroup(index, { dimension_value: value($event) })"
        />
        <input
          :value="group.match_prefix.join(' / ')"
          :placeholder="t('template.matchPrefix')"
          @change="setGroup(index, { match_prefix: splitPrefix(value($event)) })"
        />
        <button
          class="ghost"
          :disabled="modelValue.groups.length === 1"
          @click="update({ groups: modelValue.groups.filter((_, i) => i !== index) })"
        >{{ t("common.remove") }}</button>
      </div>
      <div>
        <button class="ghost" @click="update({ groups: [...modelValue.groups, { dimension_value: '', match_prefix: [] }] })">
          {{ t("common.add") }}
        </button>
      </div>

      <strong>{{ t("template.measures") }}</strong>
      <div v-for="(measure, index) in modelValue.measures" :key="`m${index}`" class="row">
        <input
          :value="measure.excel_leaf"
          :placeholder="t('template.excelLeaf')"
          @input="setMeasure(index, { excel_leaf: value($event) })"
        />
        <input
          :value="measure.db_column"
          list="db-columns"
          :placeholder="t('template.pickColumn')"
          @input="setMeasure(index, { db_column: value($event) })"
        />
        <button
          class="ghost"
          :disabled="modelValue.measures.length === 1"
          @click="update({ measures: modelValue.measures.filter((_, i) => i !== index) })"
        >{{ t("common.remove") }}</button>
      </div>
      <div>
        <button class="ghost" @click="update({ measures: [...modelValue.measures, { excel_leaf: '', db_column: '' }] })">
          {{ t("common.add") }}
        </button>
      </div>

      <label class="field inline">
        <input
          type="checkbox"
          :checked="modelValue.skip_empty_measures"
          @change="update({ skip_empty_measures: ($event.target as HTMLInputElement).checked })"
        />
        <span>{{ t("template.skipEmpty") }}</span>
      </label>
    </template>
  </div>
</template>
