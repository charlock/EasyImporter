<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

function toggle(checked: boolean | "indeterminate"): void {
  emit("update:modelValue", checked === true ? { ...EMPTY } : null);
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
</script>

<template>
  <Card>
    <CardContent class="space-y-4 pt-6">
      <label class="flex cursor-pointer items-center gap-2 text-sm">
        <Checkbox :model-value="!!modelValue" @update:model-value="toggle" />
        <span>{{ t("template.enableUnpivot") }}</span>
      </label>
      <template v-if="modelValue">
        <div class="space-y-2">
          <Label>{{ t("template.dimensionColumn") }}</Label>
          <Input
            :model-value="modelValue.dimension_column"
            list="db-columns"
            @update:model-value="update({ dimension_column: String($event) })"
          />
        </div>

        <div class="space-y-2">
          <strong class="text-sm">{{ t("template.groups") }}</strong>
          <div v-for="(group, index) in modelValue.groups" :key="`g${index}`" class="flex gap-2">
            <Input
              :model-value="group.dimension_value"
              :placeholder="t('template.dimensionValue')"
              @update:model-value="setGroup(index, { dimension_value: String($event) })"
            />
            <Input
              :model-value="group.match_prefix.join(' / ')"
              :placeholder="t('template.matchPrefix')"
              @change="setGroup(index, { match_prefix: splitPrefix(($event.target as HTMLInputElement).value) })"
            />
            <Button
              variant="outline"
              :disabled="modelValue.groups.length === 1"
              @click="update({ groups: modelValue.groups.filter((_, i) => i !== index) })"
            >{{ t("common.remove") }}</Button>
          </div>
          <Button variant="outline" @click="update({ groups: [...modelValue.groups, { dimension_value: '', match_prefix: [] }] })">
            {{ t("common.add") }}
          </Button>
        </div>

        <div class="space-y-2">
          <strong class="text-sm">{{ t("template.measures") }}</strong>
          <div v-for="(measure, index) in modelValue.measures" :key="`m${index}`" class="flex gap-2">
            <Input
              :model-value="measure.excel_leaf"
              :placeholder="t('template.excelLeaf')"
              @update:model-value="setMeasure(index, { excel_leaf: String($event) })"
            />
            <Input
              :model-value="measure.db_column"
              list="db-columns"
              :placeholder="t('template.pickColumn')"
              @update:model-value="setMeasure(index, { db_column: String($event) })"
            />
            <Button
              variant="outline"
              :disabled="modelValue.measures.length === 1"
              @click="update({ measures: modelValue.measures.filter((_, i) => i !== index) })"
            >{{ t("common.remove") }}</Button>
          </div>
          <Button variant="outline" @click="update({ measures: [...modelValue.measures, { excel_leaf: '', db_column: '' }] })">
            {{ t("common.add") }}
          </Button>
        </div>

        <label class="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox
            :model-value="modelValue.skip_empty_measures"
            @update:model-value="update({ skip_empty_measures: $event === true })"
          />
          <span>{{ t("template.skipEmpty") }}</span>
        </label>
      </template>
    </CardContent>
  </Card>
</template>
