<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink } from "vue-router";
import { Activity, CircleCheck, CircleX, Database, FileUp, FolderCog, LayoutTemplate, Plus } from "@lucide/vue";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/errors";
import type { Datasource, ImportTask, Page, Template } from "@/lib/types";
import { useSession } from "@/stores/session";

const props = defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();
const session = useSession();

const templates = ref<Template[]>([]);
const datasources = ref<Datasource[]>([]);
const recent = ref<ImportTask[]>([]);
const total = ref(0);
const healthOk = ref<boolean | null>(null);
const loading = ref(true);
const error = ref("");

const succeeded = computed(() => recent.value.filter((item) => item.status === "SUCCEEDED").length);
const failed = computed(() => recent.value.filter((item) => item.status === "FAILED").length);
const finished = computed(() => succeeded.value + failed.value);
const successRate = computed(() =>
  finished.value === 0 ? "—" : `${Math.round((succeeded.value / finished.value) * 100)}%`,
);

/** 最近 7 天每天的导入条数（按 created_at 归组）。 */
const trend = computed(() => {
  const days: { label: string; count: number }[] = [];
  const now = new Date();
  for (let i = 6; i >= 0; i--) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    const key = day.toDateString();
    days.push({
      label: `${day.getMonth() + 1}-${day.getDate()}`,
      count: recent.value.filter(
        (item) => item.created_at && new Date(item.created_at).toDateString() === key,
      ).length,
    });
  }
  return days;
});
const trendMax = computed(() => Math.max(1, ...trend.value.map((day) => day.count)));

async function load(): Promise<void> {
  templates.value = [];
  datasources.value = [];
  recent.value = [];
  total.value = 0;
  healthOk.value = null;
  if (props.workspaceId == null) {
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const [tpls, page] = await Promise.all([
      api.get<Template[]>(`/workspaces/${props.workspaceId}/templates`),
      api.get<Page<ImportTask>>(`/workspaces/${props.workspaceId}/imports`, { page: 1, size: 100 }),
    ]);
    templates.value = tpls;
    recent.value = page.items;
    total.value = page.total;
    if (session.isAdmin) {
      datasources.value = await api.get<Datasource[]>("/datasources").catch(() => []);
    }
    healthOk.value =
      (await api.get<{ status: string }>("/health").catch(() => null))?.status === "ok";
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    loading.value = false;
  }
}

watch(() => props.workspaceId, load, { immediate: true });
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('dashboard.title')" :description="t('dashboard.description')">
      <template #actions>
        <Button as-child>
          <RouterLink to="/import"><FileUp />{{ t("dashboard.newImport") }}</RouterLink>
        </Button>
        <Button v-if="session.isAdmin" variant="outline" as-child>
          <RouterLink to="/templates/new"><Plus />{{ t("dashboard.newTemplate") }}</RouterLink>
        </Button>
      </template>
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <EmptyState
      v-if="!loading && props.workspaceId == null"
      :title="t('common.empty')"
      :hint="t('dashboard.needWorkspace')"
    />

    <template v-else>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{ t("dashboard.workspaces") }}</CardTitle>
            <FolderCog class="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <Skeleton v-if="loading" class="h-8 w-16" />
            <div v-else class="text-2xl font-bold">{{ session.workspaces.length }}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{ t("dashboard.templates") }}</CardTitle>
            <LayoutTemplate class="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <Skeleton v-if="loading" class="h-8 w-16" />
            <div v-else class="text-2xl font-bold">{{ templates.length }}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{ t("dashboard.datasources") }}</CardTitle>
            <Database class="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <Skeleton v-if="loading" class="h-8 w-16" />
            <div v-else class="text-2xl font-bold">{{ session.isAdmin ? datasources.length : "—" }}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{ t("dashboard.imports") }}</CardTitle>
            <Activity class="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <Skeleton v-if="loading" class="h-8 w-16" />
            <div v-else class="text-2xl font-bold">{{ total }}</div>
            <p class="text-xs text-muted-foreground">
              {{ t("dashboard.succeeded") }} {{ succeeded }} · {{ t("dashboard.failed") }} {{ failed }} ·
              {{ t("dashboard.successRate") }} {{ successRate }}
            </p>
          </CardContent>
        </Card>
      </div>

      <div class="grid gap-4 lg:grid-cols-3">
        <Card class="lg:col-span-2">
          <CardHeader class="flex flex-row items-center justify-between">
            <div>
              <CardTitle>{{ t("dashboard.recent") }}</CardTitle>
              <CardDescription v-if="total > 100">{{ t("import.rows") }} {{ total }}</CardDescription>
            </div>
            <Button variant="ghost" size="sm" as-child>
              <RouterLink to="/imports">{{ t("dashboard.viewAll") }}</RouterLink>
            </Button>
          </CardHeader>
          <CardContent>
            <div v-if="loading" class="space-y-2">
              <Skeleton class="h-8 w-full" />
              <Skeleton class="h-8 w-full" />
              <Skeleton class="h-8 w-full" />
            </div>
            <EmptyState v-else-if="!recent.length" :title="t('dashboard.noImports')" />
            <Table v-else>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>{{ t("template.target") }}</TableHead>
                  <TableHead>{{ t("common.status") }}</TableHead>
                  <TableHead>{{ t("import.rows") }}</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="task in recent.slice(0, 8)" :key="task.id">
                  <TableCell>
                    <RouterLink :to="`/imports/${task.id}`" class="font-medium hover:underline">
                      {{ task.id }}
                    </RouterLink>
                  </TableCell>
                  <TableCell>{{ task.target_table }}</TableCell>
                  <TableCell><StatusBadge :status="task.status" /></TableCell>
                  <TableCell>{{ task.row_count }}</TableCell>
                  <TableCell class="text-muted-foreground">
                    {{ task.operator }} ·
                    {{ task.created_at ? new Date(task.created_at).toLocaleString() : "" }}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div class="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{{ t("dashboard.health") }}</CardTitle>
            </CardHeader>
            <CardContent>
              <Skeleton v-if="loading" class="h-6 w-32" />
              <p v-else class="flex items-center gap-2 text-sm">
                <CircleCheck v-if="healthOk" class="size-4 text-emerald-600" />
                <CircleX v-else class="size-4 text-destructive" />
                {{ healthOk ? t("dashboard.healthOk") : t("dashboard.healthFail") }}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{{ t("dashboard.trend") }}</CardTitle>
            </CardHeader>
            <CardContent>
              <div v-if="loading" class="space-y-2">
                <Skeleton class="h-16 w-full" />
              </div>
              <p v-else-if="trend.every((day) => day.count === 0)" class="text-sm text-muted-foreground">
                {{ t("dashboard.trendEmpty") }}
              </p>
              <div v-else class="flex h-24 items-end gap-2">
                <div
                  v-for="day in trend"
                  :key="day.label"
                  class="flex flex-1 flex-col items-center gap-1"
                >
                  <span class="text-xs font-medium">{{ day.count }}</span>
                  <div
                    class="w-full rounded-sm bg-primary/80"
                    :style="{ height: `${Math.max(day.count / trendMax, 0.06) * 64}px` }"
                  />
                  <span class="text-xs text-muted-foreground">{{ day.label }}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </template>
  </div>
</template>
