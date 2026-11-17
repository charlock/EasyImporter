<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { Copy, MoreHorizontal, Pencil, Plus, Trash2 } from "@lucide/vue";
import { toast } from "vue-sonner";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessageWithDetail } from "@/lib/errors";
import { useSession } from "@/stores/session";
import type { Datasource, Template } from "@/lib/types";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const router = useRouter();
const session = useSession();

const templates = ref<Template[]>([]);
const datasources = ref<Datasource[]>([]);
const error = ref("");
const deleteTarget = ref<Template | null>(null);
const deleteOpen = ref(false);

/** 数据源 id → 名称；模板没有数据源或数据源已被删时显示“—”。 */
const datasourceName = computed(() => {
  const byId = new Map(datasources.value.map((source) => [source.id, source.name]));
  return (id: number | null) => (id == null ? "—" : (byId.get(id) ?? "—"));
});

async function loadAll(id: number): Promise<void> {
  error.value = "";
  try {
    const [list, sources] = await Promise.all([
      // 列表页要展示已归档行（带“已归档”徽章），显式传参；模板下拉等其他调用方默认不含归档。
      api.get<Template[]>(`/workspaces/${id}/templates`, { include_archived: true }),
      api.get<Datasource[]>("/datasources"),
    ]);
    templates.value = list;
    datasources.value = sources;
  } catch (caught) {
    error.value = errorMessageWithDetail(caught);
  }
}

watch(
  () => props.workspaceId,
  async (id) => {
    if (id == null) {
      templates.value = [];
      datasources.value = [];
      return;
    }
    await loadAll(id);
  },
  { immediate: true },
);

function openDelete(item: Template): void {
  deleteTarget.value = item;
  deleteOpen.value = true;
}

async function cloneTemplate(item: Template): Promise<void> {
  if (props.workspaceId == null) return;
  try {
    const clone = await api.post<Template>(
      `/workspaces/${props.workspaceId}/templates/${item.id}/clone`,
    );
    toast.success(t("template.cloned", { name: clone.name }));
    await loadAll(props.workspaceId);
  } catch (caught) {
    error.value = errorMessageWithDetail(caught);
  }
}

async function removeTemplate(): Promise<void> {
  if (props.workspaceId == null || deleteTarget.value == null) return;
  try {
    await api.delete<{ ok: boolean }>(
      `/workspaces/${props.workspaceId}/templates/${deleteTarget.value.id}`,
    );
    toast.success(t("template.deleted"));
    deleteTarget.value = null;
    await loadAll(props.workspaceId);
  } catch (caught) {
    error.value = errorMessageWithDetail(caught);
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('template.title')" :description="t('template.listDescription')">
      <template #actions>
        <Button v-if="session.isAdmin && workspaceId != null" as-child>
          <RouterLink to="/templates/new"><Plus />{{ t("template.create") }}</RouterLink>
        </Button>
      </template>
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <EmptyState v-if="!templates.length" :title="t('common.empty')" />
    <Table v-else>
      <TableHeader>
        <TableRow>
          <TableHead>{{ t("common.name") }}</TableHead>
          <TableHead>{{ t("template.datasourceColumn") }}</TableHead>
          <TableHead>{{ t("template.target") }}</TableHead>
          <TableHead>{{ t("template.strategy") }}</TableHead>
          <TableHead>{{ t("template.businessKeys") }}</TableHead>
          <TableHead>{{ t("common.status") }}</TableHead>
          <TableHead v-if="session.isAdmin" class="w-[70px] text-right">{{ t("common.actions") }}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow v-for="item in templates" :key="item.id">
          <TableCell>
            <RouterLink :to="`/templates/${item.id}`" class="font-medium hover:underline">
              {{ item.name }}
            </RouterLink>
          </TableCell>
          <TableCell>{{ datasourceName(item.datasource_id) }}</TableCell>
          <TableCell>{{ item.target_schema }}.{{ item.target_table }}</TableCell>
          <TableCell>{{ t(`strategy.${item.strategy}`) }}</TableCell>
          <TableCell>
            {{ item.business_keys.length ? item.business_keys.join("、") : "—" }}
          </TableCell>
          <TableCell>
            <Badge v-if="item.is_archived" variant="secondary">{{ t("template.archived") }}</Badge>
            <span v-else class="text-muted-foreground">v{{ item.current_version }}</span>
          </TableCell>
          <TableCell v-if="session.isAdmin" class="text-right">
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="ghost" size="icon" class="h-8 w-8">
                  <MoreHorizontal class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem @click="router.push(`/templates/${item.id}`)">
                  <Pencil class="mr-2 h-4 w-4" />{{ t("common.edit") }}
                </DropdownMenuItem>
                <DropdownMenuItem @click="cloneTemplate(item)">
                  <Copy class="mr-2 h-4 w-4" />{{ t("template.clone") }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  v-if="!item.is_archived"
                  class="text-destructive"
                  @click="openDelete(item)"
                >
                  <Trash2 class="mr-2 h-4 w-4" />{{ t("common.delete") }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <!-- 删除二次确认（后端为软删除：is_archived = true） -->
    <AlertDialog v-model:open="deleteOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ t("template.deleteConfirmTitle") }}</AlertDialogTitle>
          <AlertDialogDescription>
            {{ deleteTarget ? t("template.deleteConfirm", { name: deleteTarget.name }) : "" }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction @click="removeTemplate">{{ t("common.delete") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
