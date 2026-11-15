<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Workspace } from "@/lib/types";

const props = defineProps<{ workspaces: Workspace[]; modelValue: number | null }>();
const emit = defineEmits<{ "update:modelValue": [number] }>();
const { t } = useI18n();

const value = computed<string | undefined>({
  get: () => (props.modelValue == null ? undefined : String(props.modelValue)),
  set: (next) => {
    if (next != null) emit("update:modelValue", Number(next));
  },
});
</script>

<template>
  <Select v-model="value">
    <SelectTrigger class="w-44" :aria-label="t('workspace.label')">
      <SelectValue :placeholder="t('workspace.none')" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="workspace in workspaces" :key="workspace.id" :value="String(workspace.id)">
        {{ workspace.name }}
      </SelectItem>
    </SelectContent>
  </Select>
</template>
