<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Plus } from "@lucide/vue";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  <div class="space-y-6">
    <PageHeader :title="t('template.title')">
      <template #actions>
        <Button v-if="session.isAdmin && workspaceId != null" as-child>
          <RouterLink to="/templates/new"><Plus />{{ t("template.create") }}</RouterLink>
        </Button>
      </template>
    </PageHeader>

    <EmptyState v-if="!templates.length" :title="t('common.empty')" />
    <Table v-else>
      <TableHeader>
        <TableRow>
          <TableHead>{{ t("common.name") }}</TableHead>
          <TableHead>{{ t("template.target") }}</TableHead>
          <TableHead>{{ t("template.strategy") }}</TableHead>
          <TableHead>{{ t("common.status") }}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow v-for="item in templates" :key="item.id">
          <TableCell>
            <RouterLink :to="`/templates/${item.id}`" class="font-medium hover:underline">
              {{ item.name }}
            </RouterLink>
          </TableCell>
          <TableCell>{{ item.target_schema }}.{{ item.target_table }}</TableCell>
          <TableCell>{{ t(`strategy.${item.strategy}`) }}</TableCell>
          <TableCell>
            <Badge v-if="item.is_archived" variant="secondary">{{ t("template.archived") }}</Badge>
            <span v-else class="text-muted-foreground">v{{ item.current_version }}</span>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </div>
</template>
