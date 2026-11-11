<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import { useSession } from "@/stores/session";
import type { Template } from "@/lib/types";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const session = useSession();

const templates = ref<Template[]>([]);

watch(
  () => props.workspaceId,
  async (id) => {
    templates.value = id == null ? [] : await api.get<Template[]>(`/workspaces/${id}/templates`);
  },
  { immediate: true },
);
</script>

<template>
  <div>
    <div class="page-head">
      <h1>{{ t("template.title") }}</h1>
      <RouterLink v-if="session.isAdmin && workspaceId != null" to="/templates/new">
        <button>{{ t("template.create") }}</button>
      </RouterLink>
    </div>
    <EmptyState v-if="!templates.length" :title="t('common.empty')" />
    <table v-else class="data">
      <thead>
        <tr>
          <th>{{ t("common.name") }}</th>
          <th>{{ t("template.target") }}</th>
          <th>{{ t("template.strategy") }}</th>
          <th>{{ t("common.status") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in templates" :key="item.id">
          <td><RouterLink :to="`/templates/${item.id}`">{{ item.name }}</RouterLink></td>
          <td>{{ item.target_schema }}.{{ item.target_table }}</td>
          <td>{{ t(`strategy.${item.strategy}`) }}</td>
          <td>{{ item.is_archived ? t("common.empty") : item.current_version }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
