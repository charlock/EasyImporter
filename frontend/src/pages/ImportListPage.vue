<!-- 导入记录主页：tasks 风格数据表（复选框 / 任务 / 状态 / 行数·错误数 / 时间 / 行操作）。
  复选框用于行选择（后续批量操作预留）；行操作：查看详情、删除（仅管理员，删除前
  AlertDialog 二次确认，删后刷新列表）。 -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { Eye, MoreHorizontal, Trash2 } from "@lucide/vue";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { canDeleteImport } from "@/lib/importRecords";
import type { ImportStatus, ImportTask, Page, Template } from "@/lib/types";
import { useSession } from "@/stores/session";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const router = useRouter();
const session = useSession();

const PAGE_SIZE = 20;
const STATUSES: ImportStatus[] = ["QUEUED", "RUNNING", "COMMITTING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"];

const tasks = ref<ImportTask[]>([]);
const templates = ref<Template[]>([]);
const total = ref(0);
const page = ref(1);
const status = ref("all");
const templateId = ref("all");
const error = ref("");
const selected = ref(new Set<number>());
const deleteTarget = ref<ImportTask | null>(null);
const deleteOpen = ref(false);
const deleting = ref(false);

const allSelected = computed(() => tasks.value.length > 0 && tasks.value.every((task) => selected.value.has(task.id)));
const someSelected = computed(() => tasks.value.some((task) => selected.value.has(task.id)));

async function load(): Promise<void> {
  if (props.workspaceId == null) return;
  error.value = "";
  try {
    const result = await api.get<Page<ImportTask>>(`/workspaces/${props.workspaceId}/imports`, {
      page: page.value,
      size: PAGE_SIZE,
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
// 改筛选条件回到第一页；page 本身变化也触发加载。
watch([status, templateId], () => {
  if (page.value !== 1) page.value = 1;
  else void load();
});
watch(() => [props.workspaceId, page.value], load, { immediate: true });

function toggleAll(checked: boolean | "indeterminate"): void {
  selected.value = checked === true
    ? new Set(tasks.value.map((task) => task.id))
    : new Set();
}

function toggleOne(id: number, checked: boolean | "indeterminate"): void {
  const next = new Set(selected.value);
  if (checked === true) next.add(id);
  else next.delete(id);
  selected.value = next;
}

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
  <div class="space-y-6">
    <PageHeader :title="t('import.history')">
      <template #actions>
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
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <p v-if="selected.size" class="text-sm text-muted-foreground">
      {{ t("import.selectedCount", { n: selected.size }) }}
    </p>

    <EmptyState v-if="!tasks.length" :title="t('common.empty')" />
    <template v-else>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead class="w-10">
              <Checkbox
                :checked="allSelected ? true : someSelected ? 'indeterminate' : false"
                :aria-label="t('import.selectedCount', { n: selected.size })"
                @update:checked="toggleAll"
              />
            </TableHead>
            <TableHead>{{ t("import.details") }}</TableHead>
            <TableHead>{{ t("common.status") }}</TableHead>
            <TableHead>{{ t("import.rows") }} / {{ t("import.errors") }}</TableHead>
            <TableHead>{{ t("import.operator") }} · {{ t("import.createdAt") }}</TableHead>
            <TableHead v-if="session.isAdmin" class="w-[70px] text-right">{{ t("common.actions") }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="task in tasks" :key="task.id" :data-state="selected.has(task.id) ? 'selected' : undefined">
            <TableCell>
              <Checkbox
                :checked="selected.has(task.id)"
                :aria-label="`#${task.id}`"
                @update:checked="(checked: boolean | 'indeterminate') => toggleOne(task.id, checked)"
              />
            </TableCell>
            <TableCell>
              <RouterLink :to="`/imports/${task.id}`" class="font-medium hover:underline">
                #{{ task.id }}
              </RouterLink>
              <p class="truncate text-sm text-muted-foreground" :title="task.file_name || undefined">
                {{ task.file_name || "—" }}
              </p>
              <p class="text-xs text-muted-foreground">{{ task.target_table }}</p>
            </TableCell>
            <TableCell><StatusBadge :status="task.status" /></TableCell>
            <TableCell>
              {{ task.row_count }} {{ t("import.rows") }}
              <span :class="task.error_count ? 'text-destructive' : 'text-muted-foreground'">
                · {{ task.error_count }} {{ t("import.errors") }}
              </span>
            </TableCell>
            <TableCell class="text-muted-foreground">
              {{ task.operator }}
              <span class="block text-xs">
                {{ task.created_at ? new Date(task.created_at).toLocaleString() : "" }}
              </span>
            </TableCell>
            <TableCell v-if="session.isAdmin" class="text-right">
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button variant="ghost" size="icon" class="h-8 w-8">
                    <MoreHorizontal class="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem @click="router.push(`/imports/${task.id}`)">
                    <Eye class="mr-2 h-4 w-4" />{{ t("import.viewDetails") }}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    class="text-destructive"
                    :disabled="!canDeleteImport(task.status)"
                    :title="canDeleteImport(task.status) ? undefined : t('import.notDeletable')"
                    @click="openDelete(task)"
                  >
                    <Trash2 class="mr-2 h-4 w-4" />{{ t("import.deleteTask") }}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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
  </div>
</template>
