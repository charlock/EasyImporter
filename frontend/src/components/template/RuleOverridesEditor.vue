<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { RuleOverride } from "@/lib/types";

/** 在目标表约束之上追加的校验规则。空字段表示沿用表结构推导的规则。 */
const props = defineProps<{ modelValue: RuleOverride[]; columns: string[] }>();
const emit = defineEmits<{ "update:modelValue": [value: RuleOverride[]] }>();
const { t } = useI18n();

function set(index: number, patch: Partial<RuleOverride>): void {
  emit("update:modelValue", props.modelValue.map((item, i) => (i === index ? { ...item, ...patch } : item)));
}

function setRequired(index: number, raw: string): void {
  set(index, { required: raw === "" ? null : raw === "true" });
}

function setEnum(index: number, raw: string): void {
  const parts = raw.split(/[,，]/).map((part) => part.trim()).filter(Boolean);
  set(index, { enum: parts.length ? parts : null });
}

function setText(index: number, field: "pattern" | "default", raw: string): void {
  set(index, { [field]: raw === "" ? null : raw });
}

function setMaxLength(index: number, raw: string | number): void {
  const text = String(raw);
  set(index, { max_length: text === "" ? null : Number(text) });
}
</script>

<template>
  <Card>
    <CardHeader><CardTitle>{{ t("template.rules") }}</CardTitle></CardHeader>
    <CardContent class="space-y-2">
      <table v-if="modelValue.length" class="w-full caption-bottom text-sm">
        <thead>
          <tr class="border-b">
            <th class="h-9 px-2 text-left align-middle font-medium text-muted-foreground">{{ t("common.column") }}</th>
            <th class="h-9 px-2 text-left align-middle font-medium text-muted-foreground">{{ t("template.ruleRequired") }}</th>
            <th class="h-9 px-2 text-left align-middle font-medium text-muted-foreground">{{ t("template.ruleEnum") }}</th>
            <th class="h-9 px-2 text-left align-middle font-medium text-muted-foreground">{{ t("template.rulePattern") }}</th>
            <th class="h-9 px-2 text-left align-middle font-medium text-muted-foreground">{{ t("template.ruleDefault") }}</th>
            <th class="h-9 px-2 text-left align-middle font-medium text-muted-foreground">{{ t("template.ruleMaxLength") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in modelValue" :key="index" class="border-b last:border-0">
            <td class="px-2 py-1 align-middle">
              <Select :model-value="item.db_column" @update:model-value="set(index, { db_column: String($event) })">
                <SelectTrigger class="min-w-24">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">—</SelectItem>
                  <SelectItem v-for="column in columns" :key="column" :value="column">{{ column }}</SelectItem>
                </SelectContent>
              </Select>
            </td>
            <td class="px-2 py-1 align-middle">
              <Select :model-value="item.required == null ? '' : String(item.required)" @update:model-value="setRequired(index, String($event))">
                <SelectTrigger class="min-w-16">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">—</SelectItem>
                  <SelectItem value="true">✓</SelectItem>
                  <SelectItem value="false">✗</SelectItem>
                </SelectContent>
              </Select>
            </td>
            <td class="px-2 py-1 align-middle">
              <Input class="min-w-20" :model-value="item.enum?.join(', ') ?? ''" @update:model-value="setEnum(index, String($event))" />
            </td>
            <td class="px-2 py-1 align-middle">
              <Input class="min-w-20" :model-value="item.pattern ?? ''" @update:model-value="setText(index, 'pattern', String($event))" />
            </td>
            <td class="px-2 py-1 align-middle">
              <Input class="min-w-20" :model-value="item.default ?? ''" @update:model-value="setText(index, 'default', String($event))" />
            </td>
            <td class="px-2 py-1 align-middle">
              <Input class="min-w-20" type="number" min="1" :model-value="item.max_length ?? ''" @update:model-value="setMaxLength(index, $event)" />
            </td>
            <td class="px-2 py-1 align-middle">
              <Button variant="outline" size="sm" @click="emit('update:modelValue', modelValue.filter((_, i) => i !== index))">
                {{ t("common.remove") }}
              </Button>
            </td>
          </tr>
        </tbody>
      </table>
      <Button variant="outline" @click="emit('update:modelValue', [...modelValue, { db_column: '' }])">
        {{ t("common.add") }}
      </Button>
    </CardContent>
  </Card>
</template>
