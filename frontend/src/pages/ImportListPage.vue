<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { errorMessage } from "@/lib/errors";
import type { ImportStatus, ImportTask, Page, Template } from "@/lib/types";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();

const PAGE_SIZE = 20;
const STATUSES: ImportStatus[] = ["QUEUED", "RUNNING", "COMMITTING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"];

const tasks = ref<ImportTask[]>([]);
const templates = ref<Template[]>([]);
const total = ref(0);
const page = ref(1);
const status = ref("");
const templateId = ref("");
const error = ref("");

async function load(): Promise<void> {
  if (props.workspaceId == null) return;
  error.value = "";
  try {
    const result = await api.get<Page<ImportTask>>(`/workspaces/${props.workspaceId}/imports`, {
      page: page.value,
      size: PAGE_SIZE,
      status: status.value,
      template_id: templateId.value,
    });
    tasks.value = result.items;
    total.value = result.total;
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

watch(
  () => props.workspaceId,
  async (id) => {
    templateId.value = "";
    templates.value = id == null ? [] : await api.get<Template[]>(`/workspaces/${id}/templates`).catch(() => []);
  },
  { immediate: true },
);
// 改筛选条件回到第一页；page 本身变化也触发加载。
watch([status, templateId], () => {
  if (page.value !== 1) page.value = 1;
  else void load();
});
watch(() => [props.workspaceId, page.value], load, { immediate: true });
</script>

<template>
  <div>
    <div class="page-head">
      <h1>{{ t("import.history") }}</h1>
      <div class="row filters">
        <select v-model="status" :aria-label="t('common.status')">
          <option value="">{{ t("common.status") }}: {{ t("common.all") }}</option>
          <option v-for="item in STATUSES" :key="item" :value="item">{{ t(`status.${item}`) }}</option>
        </select>
        <select v-model="templateId" :aria-label="t('import.template')">
          <option value="">{{ t("import.template") }}: {{ t("common.all") }}</option>
          <option v-for="item in templates" :key="item.id" :value="String(item.id)">{{ item.name }}</option>
        </select>
      </div>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <EmptyState v-if="!tasks.length" :title="t('common.empty')" />
    <table v-else class="data">
      <thead>
        <tr>
          <th>#</th>
          <th>{{ t("template.target") }}</th>
          <th>{{ t("common.status") }}</th>
          <th>{{ t("import.rows") }}</th>
          <th>{{ t("import.errors") }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.id">
          <td><RouterLink :to="`/imports/${task.id}`">{{ task.id }}</RouterLink></td>
          <td>{{ task.target_table }}</td>
          <td><StatusBadge :status="task.status" /></td>
          <td>{{ task.row_count }}</td>
          <td>{{ task.error_count }}</td>
          <td class="muted">{{ task.operator }} · {{ task.created_at ? new Date(task.created_at).toLocaleString() : "" }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="total > PAGE_SIZE" class="row" style="margin-top: 12px">
      <button class="ghost" :disabled="page === 1" @click="page -= 1">{{ t("common.prev") }}</button>
      <span class="muted">{{ page }}</span>
      <button class="ghost" :disabled="page * PAGE_SIZE >= total" @click="page += 1">{{ t("common.next") }}</button>
    </div>
  </div>
</template>

<style scoped>
.filters { margin-left: auto; }
</style>
