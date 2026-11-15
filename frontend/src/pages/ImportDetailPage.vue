<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import { api, download } from "@/api/client";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { codeText, errorMessage, logText } from "@/lib/errors";
import type { ImportError, ImportLog, ImportStatus, ImportTask, Page } from "@/lib/types";
import { useSession } from "@/stores/session";

const props = defineProps<{ workspaceId: number | null }>();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { t } = useI18n();

const TERMINAL: ImportStatus[] = ["SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"];
const POLL_MS = 2000;
const ERROR_PAGE_SIZE = 50;

const task = ref<ImportTask | null>(null);
const logs = ref<ImportLog[]>([]);
const errors = ref<ImportError[]>([]);
const errorPage = ref(1);
const error = ref("");
const busy = ref(false);
const pendingOutcome = ref<"CONFIRMED_WRITTEN" | "CONFIRMED_NOT_WRITTEN" | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

const base = computed(() => `/workspaces/${props.workspaceId}/imports/${route.params.id}`);
const terminal = computed(() => task.value != null && TERMINAL.includes(task.value.status));
const canCancel = computed(() => task.value?.status === "QUEUED" || task.value?.status === "RUNNING");
const canRetry = computed(() => task.value?.status === "FAILED" || task.value?.status === "CANCELLED");
const canResolve = computed(() => session.isAdmin && task.value?.status === "UNKNOWN");

async function loadLogs(): Promise<void> {
  const lastId = logs.value.at(-1)?.id ?? 0;
  const fresh = await api.get<ImportLog[]>(`${base.value}/logs`, { after_id: lastId });
  if (fresh.length) logs.value = [...logs.value, ...fresh];
}

async function loadErrors(): Promise<void> {
  if (!task.value?.error_count) {
    errors.value = [];
    return;
  }
  const page = await api.get<Page<ImportError>>(`${base.value}/errors`, {
    page: errorPage.value,
    size: ERROR_PAGE_SIZE,
  });
  errors.value = page.items;
}

async function refresh(): Promise<void> {
  clearTimeout(timer);
  if (props.workspaceId == null) return;
  try {
    task.value = await api.get<ImportTask>(base.value);
    await loadLogs();
    if (terminal.value) await loadErrors();
    else timer = setTimeout(refresh, POLL_MS);
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

watch(
  () => [props.workspaceId, route.params.id],
  () => {
    logs.value = [];
    errors.value = [];
    errorPage.value = 1;
    error.value = "";
    void refresh();
  },
  { immediate: true },
);
watch(errorPage, () => void loadErrors().catch((caught) => (error.value = errorMessage(caught))));
onBeforeUnmount(() => clearTimeout(timer));

async function run(action: () => Promise<void>): Promise<void> {
  error.value = "";
  busy.value = true;
  try {
    await action();
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    busy.value = false;
  }
}

const cancel = () => run(async () => {
  await api.post(`${base.value}/cancel`);
  await refresh();
});

const retry = () => run(async () => {
  const next = await api.post<ImportTask>(`${base.value}/retry`);
  await router.push(`/imports/${next.id}`);
});

const resolve = () => run(async () => {
  if (pendingOutcome.value == null) return;
  task.value = await api.post<ImportTask>(`${base.value}/resolve`, { outcome: pendingOutcome.value });
  pendingOutcome.value = null;
  await loadLogs();
});

const downloadFile = () => run(() => download(`${base.value}/file`, `import-${route.params.id}.xlsx`));
const exportErrors = () =>
  run(() => download(`${base.value}/error-report`, `import-${route.params.id}-errors.xlsx`));
</script>

<template>
  <div class="space-y-6">
    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <template v-if="task">
      <PageHeader :title="`#${task.id}`">
        <template #actions>
          <StatusBadge :status="task.status" />
          <Button v-if="canCancel" variant="outline" :disabled="busy" @click="cancel">
            {{ t("import.cancel") }}
          </Button>
          <Button v-if="canRetry" :disabled="busy" @click="retry">
            {{ t("import.retry") }}
          </Button>
          <template v-if="canResolve">
            <Button
              variant="outline"
              :disabled="busy"
              @click="pendingOutcome = 'CONFIRMED_WRITTEN'"
            >
              {{ t("import.resolveWritten") }}
            </Button>
            <Button
              variant="outline"
              :disabled="busy"
              @click="pendingOutcome = 'CONFIRMED_NOT_WRITTEN'"
            >
              {{ t("import.resolveNotWritten") }}
            </Button>
          </template>
          <Button variant="outline" :disabled="busy" @click="downloadFile">
            {{ t("import.downloadFile") }}
          </Button>
        </template>
      </PageHeader>

      <Card>
        <CardContent class="space-y-2 pt-6 text-sm">
          <p>{{ task.target_table }} · {{ task.strategy ? t(`strategy.${task.strategy}`) : "" }} · {{ task.operator }}</p>
          <p v-if="!terminal" class="text-muted-foreground">
            {{ t("import.progress", { processed: task.processed, total: task.row_count }) }}
          </p>
          <p class="text-muted-foreground">
            {{ t("import.counts", { inserted: task.inserted, updated: task.updated, deleted: task.deleted }) }}
            <span v-if="!task.counts_exact">{{ t("import.countsApprox") }}</span>
          </p>
          <p v-if="task.failure_code" class="text-destructive">
            {{ codeText(task.failure_code, task.failure_message) }}
          </p>
          <p v-if="task.failure_message && task.failure_message !== codeText(task.failure_code)" class="text-muted-foreground">
            {{ task.failure_message }}
          </p>
        </CardContent>
      </Card>

      <Card v-if="task.error_count && errors.length">
        <CardHeader>
          <CardTitle class="flex items-center justify-between">
            <span>{{ task.error_count }} {{ t("import.errors") }}</span>
            <Button variant="outline" size="sm" :disabled="busy" @click="exportErrors">
              {{ t("import.exportErrors") }}
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{{ t("grid.rowNo") }}</TableHead>
                <TableHead>{{ t("common.column") }}</TableHead>
                <TableHead>{{ t("import.errors") }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="item in errors" :key="item.id">
                <TableCell>{{ item.row_no }}</TableCell>
                <TableCell>{{ item.column }}</TableCell>
                <TableCell>{{ codeText(item.code) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <div v-if="task.error_count > ERROR_PAGE_SIZE" class="mt-4 flex items-center gap-2">
            <Button variant="outline" size="sm" :disabled="errorPage === 1" @click="errorPage -= 1">
              {{ t("common.prev") }}
            </Button>
            <span class="text-sm text-muted-foreground">{{ errorPage }}</span>
            <Button
              variant="outline"
              size="sm"
              :disabled="errorPage * ERROR_PAGE_SIZE >= task.error_count"
              @click="errorPage += 1"
            >
              {{ t("common.next") }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{{ t("import.logs") }}</CardTitle></CardHeader>
        <CardContent>
          <ScrollArea class="h-64">
            <p
              v-for="log in logs"
              :key="log.id"
              :class="log.level === 'INFO' ? 'text-sm text-muted-foreground' : 'text-sm text-destructive'"
            >
              {{ new Date(log.ts).toLocaleString() }} · {{ logText(log) }}
            </p>
          </ScrollArea>
        </CardContent>
      </Card>
    </template>

    <AlertDialog :open="pendingOutcome !== null" @update:open="(open) => { if (!open) pendingOutcome = null; }">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {{ pendingOutcome === "CONFIRMED_WRITTEN" ? t("import.resolveWritten") : t("import.resolveNotWritten") }}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {{ t("import.resolveConfirm", { outcome: pendingOutcome === "CONFIRMED_WRITTEN" ? t("import.resolveWritten") : t("import.resolveNotWritten") }) }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction :disabled="busy" @click="resolve">{{ t("common.confirm") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
