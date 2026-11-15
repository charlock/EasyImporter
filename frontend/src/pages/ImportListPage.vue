<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  <div class="space-y-6">
    <PageHeader :title="t('import.history')">
      <template #actions>
        <Select v-model="status">
          <SelectTrigger class="w-40" :aria-label="t('common.status')">
            <SelectValue :placeholder="`${t('common.status')}: ${t('common.all')}`" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">{{ t("common.all") }}</SelectItem>
            <SelectItem v-for="item in STATUSES" :key="item" :value="item">
              {{ t(`status.${item}`) }}
            </SelectItem>
          </SelectContent>
        </Select>
        <Select v-model="templateId">
          <SelectTrigger class="w-48" :aria-label="t('import.template')">
            <SelectValue :placeholder="`${t('import.template')}: ${t('common.all')}`" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">{{ t("common.all") }}</SelectItem>
            <SelectItem v-for="item in templates" :key="item.id" :value="String(item.id)">
              {{ item.name }}
            </SelectItem>
          </SelectContent>
        </Select>
      </template>
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <EmptyState v-if="!tasks.length" :title="t('common.empty')" />
    <template v-else>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>{{ t("template.target") }}</TableHead>
            <TableHead>{{ t("common.status") }}</TableHead>
            <TableHead>{{ t("import.rows") }}</TableHead>
            <TableHead>{{ t("import.errors") }}</TableHead>
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="task in tasks" :key="task.id">
            <TableCell>
              <RouterLink :to="`/imports/${task.id}`" class="font-medium hover:underline">
                {{ task.id }}
              </RouterLink>
            </TableCell>
            <TableCell>{{ task.target_table }}</TableCell>
            <TableCell><StatusBadge :status="task.status" /></TableCell>
            <TableCell>{{ task.row_count }}</TableCell>
            <TableCell>{{ task.error_count }}</TableCell>
            <TableCell class="text-muted-foreground">
              {{ task.operator }} · {{ task.created_at ? new Date(task.created_at).toLocaleString() : "" }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
      <div v-if="total > PAGE_SIZE" class="flex items-center gap-2">
        <Button variant="outline" size="sm" :disabled="page === 1" @click="page -= 1">
          {{ t("common.prev") }}
        </Button>
        <span class="text-sm text-muted-foreground">{{ page }}</span>
        <Button
          variant="outline"
          size="sm"
          :disabled="page * PAGE_SIZE >= total"
          @click="page += 1"
        >
          {{ t("common.next") }}
        </Button>
      </div>
    </template>
  </div>
</template>
