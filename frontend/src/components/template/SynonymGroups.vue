<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import { errorMessage } from "@/lib/errors";
import type { SynonymGroup } from "@/lib/types";

/** 工作区级同义词组，自动匹配表头时使用。 */
const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();

const groups = ref<SynonymGroup[]>([]);
const draft = ref("");
const error = ref("");

const base = () => `/workspaces/${props.workspaceId}/synonym-groups`;
const splitTerms = (text: string): string[] =>
  [...new Set(text.split(/[,，]/).map((term) => term.trim()).filter(Boolean))];

async function load(): Promise<void> {
  if (props.workspaceId == null) return;
  try {
    groups.value = await api.get<SynonymGroup[]>(base());
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function run(action: () => Promise<void>): Promise<void> {
  error.value = "";
  try {
    await action();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

const add = () => run(async () => {
  const terms = splitTerms(draft.value);
  if (terms.length < 2) return;
  const created = await api.post<SynonymGroup>(base(), { terms });
  groups.value = [...groups.value, created];
  draft.value = "";
});

const save = (group: SynonymGroup, text: string) => run(async () => {
  const terms = splitTerms(text);
  if (!terms.length) return;
  const updated = await api.put<SynonymGroup>(`${base()}/${group.id}`, { terms });
  groups.value = groups.value.map((item) => (item.id === group.id ? updated : item));
});

const remove = (group: SynonymGroup) => run(async () => {
  if (!window.confirm(t("common.confirmDelete"))) return;
  await api.delete(`${base()}/${group.id}`);
  groups.value = groups.value.filter((item) => item.id !== group.id);
});

watch(() => props.workspaceId, load, { immediate: true });
</script>

<template>
  <div class="card stack">
    <h2>{{ t("template.synonyms") }}</h2>
    <p class="muted">{{ t("template.synonymHint") }}</p>
    <div v-for="group in groups" :key="group.id" class="row">
      <input
        class="grow"
        :value="group.terms.join(', ')"
        @change="save(group, ($event.target as HTMLInputElement).value)"
      />
      <button class="ghost" @click="remove(group)">{{ t("common.delete") }}</button>
    </div>
    <div class="row">
      <input v-model="draft" class="grow" placeholder="水单号, 流水号, serial_no" @keydown.enter="add" />
      <button class="ghost" @click="add">{{ t("common.add") }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
h2 { font-size: 16px; margin: 0; }
.grow { flex: 1; }
</style>
