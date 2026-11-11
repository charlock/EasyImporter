<script setup lang="ts">
import { useI18n } from "vue-i18n";

import type { Workspace } from "@/lib/types";

defineProps<{ workspaces: Workspace[]; modelValue: number | null }>();
const emit = defineEmits<{ "update:modelValue": [number] }>();
const { t } = useI18n();

function onChange(event: Event): void {
  emit("update:modelValue", Number((event.target as HTMLSelectElement).value));
}
</script>

<template>
  <label class="field inline">
    <span>{{ t("workspace.label") }}</span>
    <select :value="modelValue ?? ''" @change="onChange">
      <option value="" disabled>{{ t("workspace.none") }}</option>
      <option v-for="workspace in workspaces" :key="workspace.id" :value="workspace.id">
        {{ workspace.name }}
      </option>
    </select>
  </label>
</template>
