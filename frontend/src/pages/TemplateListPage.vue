<!-- 模板列表页：与导入记录页共用 ListShell（同一套头部 / 过滤 / 表格 / 分页），
  只在列定义与数据源上差异化。本页数据源为全量模板（后端一次性返回），
  搜索与归档过滤、分页都在客户端完成。 -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { Copy, Pencil, Plus, Trash2 } from "@lucide/vue";
import { toast } from "vue-sonner";

import { api } from "@/api/client";
import ListShell from "@/components/list/ListShell.vue";
import {
  applyTextFilter,
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
const search = ref("");
/** 状态过滤默认“未归档”：删除是软删除（行变已归档），默认视图下删完行即
 * 消失；已归档的模板仍可在“已归档”过滤下找到，导入记录不受影响。 */
const archivedFilter = ref("active");
const page = ref(1);
const pageSize = ref(20);
const selected = ref(new Set<number>());

/** 数据源 id → 名称；模板没有数据源或数据源已被删时显示“—”。 */
const datasourceName = computed(() => {
  const byId = new Map(datasources.value.map((source) => [source.id, source.name]));
  return (id: number | null) => (id == null ? "—" : (byId.get(id) ?? "—"));
});

/** 先按名称/目标表搜索，再按归档状态过滤；改过滤条件回到第一页。 */
const filtered = computed(() => {
  const searched = applyTextFilter(templates.value, search.value, (item) => [
    item.name,
    `${item.target_schema}.${item.target_table}`,
  ]);
  if (archivedFilter.value === "archived") return searched.filter((item) => item.is_archived);
  if (archivedFilter.value === "active") return searched.filter((item) => !item.is_archived);
  return searched;
});
const paged = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value),
);

/** 列定义：kind 与单元格表达一一对应（同列一种渲染、一种交互）。 */
const columns = computed<ListColumn<Template>[]>(() => {
  const base: ListColumn<Template>[] = [
    {
      key: "name",
      header: t("common.name"),
      kind: "link",
      cell: (item) => ({ type: "link", to: `/templates/${item.id}`, label: item.name }),
    },
    {
      key: "datasource",
      header: t("template.datasourceColumn"),
      kind: "text",
      cell: (item) => ({ type: "text", text: datasourceName.value(item.datasource_id) }),
    },
    {
      key: "target",
      header: t("template.target"),
      kind: "text",
      cell: (item) => ({ type: "text", text: `${item.target_schema}.${item.target_table}` }),
    },
    {
      key: "strategy",
      header: t("template.strategy"),
      kind: "text",
      cell: (item) => ({ type: "text", text: t(`strategy.${item.strategy}`) }),
    },
    {
      key: "businessKeys",
      header: t("template.businessKeys"),
      kind: "text",
      cell: (item) => ({
        type: "text",
        text: item.business_keys.length ? item.business_keys.join("、") : "—",
      }),
    },
    {
      key: "status",
      header: t("common.status"),
      kind: "badge",
      cell: (item) =>
        item.is_archived
          ? { type: "badge", label: t("template.archived"), tone: "muted" }
          : { type: "badge", label: `v${item.current_version}`, tone: "success" },
    },
  ];
  if (session.isAdmin) base.push({ key: "actions", header: t("common.actions"), kind: "actions" });
  return base;
});

function rowActions(item: Template): ListAction[] {
  const actions: ListAction[] = [
    {
      label: t("common.edit"),
      icon: Pencil,
      onClick: () => router.push(`/templates/${item.id}`),
    },
    {
      label: t("template.clone"),
      icon: Copy,
      onClick: () => cloneTemplate(item),
    },
  ];
  if (!item.is_archived) {
    actions.push({
      label: t("common.delete"),
      icon: Trash2,
      danger: true,
      onClick: () => openDelete(item),
    });
  }
  return actions;
}

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
watch([search, archivedFilter], () => {
  page.value = 1;
});

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
  <ListShell
    v-model:page="page"
    v-model:page-size="pageSize"
    v-model:search="search"
    v-model:selected="selected"
    :title="t('template.title')"
    :description="t('template.listDescription')"
    :columns="columns"
    :rows="paged"
    :row-key="(item) => item.id"
    :total="filtered.length"
    :actions="session.isAdmin ? rowActions : undefined"
    :error="error"
    show-search
  >
    <template #actions>
      <Button variant="outline" as-child>
        <RouterLink to="/import"><Plus />{{ t("import.newImport") }}</RouterLink>
      </Button>
      <Button v-if="session.isAdmin && workspaceId != null" as-child>
        <RouterLink to="/templates/new"><Plus />{{ t("template.create") }}</RouterLink>
      </Button>
    </template>
    <template #filters>
      <Select v-model="archivedFilter">
        <SelectTrigger class="w-40" :aria-label="t('common.status')">
          <SelectValue :placeholder="`${t('common.status')}: ${t('common.all')}`" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{{ t("common.all") }}</SelectItem>
          <SelectItem value="active">{{ t("template.notArchived") }}</SelectItem>
          <SelectItem value="archived">{{ t("template.archived") }}</SelectItem>
        </SelectContent>
      </Select>
    </template>
  </ListShell>

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
</template>
