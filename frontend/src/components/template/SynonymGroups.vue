<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/errors";
import type { SynonymGroup } from "@/lib/types";

/** 工作区级同义词组，自动匹配表头时使用。 */
const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();

const groups = ref<SynonymGroup[]>([]);
const draft = ref("");
const error = ref("");
const deleteTarget = ref<SynonymGroup | null>(null);

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

const remove = () => run(async () => {
  if (deleteTarget.value == null) return;
  await api.delete(`${base()}/${deleteTarget.value.id}`);
  groups.value = groups.value.filter((item) => item.id !== deleteTarget.value?.id);
  deleteTarget.value = null;
});

watch(() => props.workspaceId, load, { immediate: true });
</script>

<template>
  <Card>
    <CardHeader><CardTitle>{{ t("template.synonyms") }}</CardTitle></CardHeader>
    <CardContent class="space-y-2">
      <p class="text-sm text-muted-foreground">{{ t("template.synonymHint") }}</p>
      <div v-for="group in groups" :key="group.id" class="flex gap-2">
        <Input
          class="flex-1"
          :model-value="group.terms.join(', ')"
          @change="save(group, ($event.target as HTMLInputElement).value)"
        />
        <Button variant="outline" @click="deleteTarget = group">{{ t("common.delete") }}</Button>
      </div>
      <div class="flex gap-2">
        <Input
          v-model="draft"
          class="flex-1"
          placeholder="水单号, 流水号, serial_no"
          @keydown.enter="add"
        />
        <Button variant="outline" @click="add">{{ t("common.add") }}</Button>
      </div>
      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
    </CardContent>
  </Card>

  <AlertDialog :open="deleteTarget !== null" @update:open="(open) => { if (!open) deleteTarget = null; }">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ t("common.confirmDelete") }}</AlertDialogTitle>
        <AlertDialogDescription>{{ deleteTarget?.terms.join(", ") }}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
        <AlertDialogAction @click="remove">{{ t("common.delete") }}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
