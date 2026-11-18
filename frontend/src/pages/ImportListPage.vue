<!-- 导入记录主页：tasks 风格数据表（复选框 / 任务 / 状态 / 行数·错误数 / 时间 / 行操作）。
  表格骨架（头部 / 过滤 / 分页 / 已选行数）由 ListShell 提供，本页只定义列与数据源；
  复选框用于行选择（后续批量操作预留）；行操作：查看详情、删除（仅管理员，删除前
  AlertDialog 二次确认，删后刷新列表）。 -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { Eye, Plus, Trash2 } from "@lucide/vue";

import { api } from "@/api/client";
import ListShell from "@/components/list/ListShell.vue";
import {
  importStatusTone,
  type ListAction,
  type ListColumn,
} from "@/components/list/listTypes";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { errorMessage } from "@/lib/errors";
import { canDeleteImport } from "@/lib/importRecords";
import type { ImportStatus, ImportTask, Page, Template } from "@/lib/types";
import { useSession } from "@/stores/session";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const router = useRouter();
const session = useSession();

const STATUSES: ImportStatus[] = ["QUEUED", "RUNNING", "COMMITTING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"];

const tasks = ref<ImportTask[]>([]);
const templates = ref<Template[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const status = ref("all");
const templateId = ref("all");
const error = ref("");
const selected = ref(new Set<number>());
const deleteTarget = ref<ImportTask | null>(null);
const deleteOpen = ref(false);
const deleting = ref(false);

/** 列定义：kind 与单元格表达一一对应（同列一种渲染、一种交互）。 */
const columns = computed<ListColumn<ImportTask>[]>(() => {
  const base: ListColumn<ImportTask>[] = [
    {
      key: "details",
      header: t("import.details"),
      kind: "link",
      cell: (task) => ({
        type: "link",
        to: `/imports/${task.id}`,
        label: `#${task.id}`,
        sub: [task.file_name || "—", task.target_table],
      }),
    },
    {
      key: "status",
      header: t("common.status"),
      kind: "badge",
      cell: (task) => ({
        type: "badge",
        label: t(`status.${task.status}`),
        tone: importStatusTone(task.status),
      }),
    },
    {
      key: "counts",
      header: `${t("import.rows")} / ${t("import.errors")}`,
      kind: "count",
      cell: (task) => ({
        type: "count",
        primary: `${task.row_count} ${t("import.rows")}`,
        secondary: `${task.error_count} ${t("import.errors")}`,
        danger: task.error_count > 0,
      }),
    },
    {
      key: "operator",
      header: `${t("import.operator")} · ${t("import.createdAt")}`,
      kind: "meta",
      cell: (task) => ({
        type: "meta",
        primary: task.operator,
        secondary: task.created_at ? new Date(task.created_at).toLocaleString() : "",
      }),
    },
  ];
  if (session.isAdmin) base.push({ key: "actions", header: t("common.actions"), kind: "actions" });
  return base;
});

function rowActions(task: ImportTask): ListAction[] {
  return [
    {
      label: t("import.viewDetails"),
      icon: Eye,
      onClick: () => router.push(`/imports/${task.id}`),
    },
    {
      label: t("import.deleteTask"),
      icon: Trash2,
      danger: true,
      disabled: !canDeleteImport(task.status),
      title: canDeleteImport(task.status) ? undefined : t("import.notDeletable"),
      onClick: () => openDelete(task),
    },
  ];
}

async function load(): Promise<void> {
  if (props.workspaceId == null) return;
  error.value = "";
  try {
    const result = await api.get<Page<ImportTask>>(`/workspaces/${props.workspaceId}/imports`, {
      page: page.value,
      size: pageSize.value,
      // "all" 是哨兵值：不筛，传空串由 client 丢弃，与原来传 "" 等价。
      status: status.value === "all" ? "" : status.value,
      template_id: templateId.value === "all" ? "" : templateId.value,
    });
    tasks.value = result.items;
    total.value = result.total;
    selected.value = new Set([...selected.value].filter((id) => result.items.some((task) => task.id === id)));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

watch(
  () => props.workspaceId,
  async (id) => {
    templateId.value = "all";
    templates.value = id == null ? [] : await api.get<Template[]>(`/workspaces/${id}/templates`).catch(() => []);
  },
  { immediate: true },
);
// 改筛选条件回到第一页；page / pageSize 本身变化也触发加载。
watch([status, templateId], () => {
  if (page.value !== 1) page.value = 1;
  else void load();
});
watch(() => [props.workspaceId, page.value, pageSize.value], load, { immediate: true });

function openDelete(task: ImportTask): void {
  deleteTarget.value = task;
  deleteOpen.value = true;
}

async function removeTask(): Promise<void> {
  if (props.workspaceId == null || deleteTarget.value == null) return;
  const target = deleteTarget.value;
  deleting.value = true;
  error.value = "";
  try {
    await api.delete<{ ok: boolean }>(`/workspaces/${props.workspaceId}/imports/${target.id}`);
    deleteTarget.value = null;
    deleteOpen.value = false;
    selected.value = new Set([...selected.value].filter((id) => id !== target.id));
    await load();
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <ListShell
    v-model:page="page"
    v-model:page-size="pageSize"
    v-model:selected="selected"
    :title="t('import.history')"
    :columns="columns"
    :rows="tasks"
    :row-key="(task) => task.id"
    :total="total"
    :actions="session.isAdmin ? rowActions : undefined"
    :error="error"
  >
    <template #actions>
      <Button as-child>
        <RouterLink to="/import"><Plus />{{ t("import.newImport") }}</RouterLink>
      </Button>
    </template>
    <template #filters>
      <Select v-model="status">
        <SelectTrigger class="w-40" :aria-label="t('common.status')">
          <SelectValue :placeholder="`${t('common.status')}: ${t('common.all')}`" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{{ t("common.all") }}</SelectItem>
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
          <SelectItem value="all">{{ t("common.all") }}</SelectItem>
          <SelectItem v-for="item in templates" :key="item.id" :value="String(item.id)">
            {{ item.name }}
          </SelectItem>
        </SelectContent>
      </Select>
    </template>
  </ListShell>

  <!-- 删除二次确认（后端为硬删除：任务 + 日志 + 错误 + 磁盘文件） -->
  <AlertDialog v-model:open="deleteOpen">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{{ t("import.deleteTaskTitle") }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{
            deleteTarget
              ? t("import.deleteTaskConfirm", { id: deleteTarget.id, file: deleteTarget.file_name || "—" })
              : ""
          }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
        <AlertDialogAction :disabled="deleting" @click="removeTask">
          {{ t("common.delete") }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
