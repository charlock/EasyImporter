<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import { api, download } from "@/api/client";
import StatusBadge from "@/components/StatusBadge.vue";
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

const resolve = (outcome: "CONFIRMED_WRITTEN" | "CONFIRMED_NOT_WRITTEN") => run(async () => {
  const label = outcome === "CONFIRMED_WRITTEN" ? t("import.resolveWritten") : t("import.resolveNotWritten");
  if (!window.confirm(t("import.resolveConfirm", { outcome: label }))) return;
  task.value = await api.post<ImportTask>(`${base.value}/resolve`, { outcome });
  await loadLogs();
});

const downloadFile = () => run(() => download(`${base.value}/file`, `import-${route.params.id}.xlsx`));
const exportErrors = () =>
  run(() => download(`${base.value}/error-report`, `import-${route.params.id}-errors.xlsx`));
</script>

<template>
  <div class="stack">
    <p v-if="error" class="error">{{ error }}</p>
    <template v-if="task">
      <div class="page-head">
        <h1>#{{ task.id }}</h1>
        <StatusBadge :status="task.status" />
        <div class="row actions">
          <button v-if="canCancel" class="ghost" :disabled="busy" @click="cancel">{{ t("import.cancel") }}</button>
          <button v-if="canRetry" :disabled="busy" @click="retry">{{ t("import.retry") }}</button>
          <template v-if="canResolve">
            <button class="ghost" :disabled="busy" @click="resolve('CONFIRMED_WRITTEN')">
              {{ t("import.resolveWritten") }}
            </button>
            <button class="ghost" :disabled="busy" @click="resolve('CONFIRMED_NOT_WRITTEN')">
              {{ t("import.resolveNotWritten") }}
            </button>
          </template>
          <button class="ghost" :disabled="busy" @click="downloadFile">{{ t("import.downloadFile") }}</button>
        </div>
      </div>
      <div class="card stack">
        <p>{{ task.target_table }} · {{ task.strategy ? t(`strategy.${task.strategy}`) : "" }} · {{ task.operator }}</p>
        <p v-if="!terminal" class="muted">
          {{ t("import.progress", { processed: task.processed, total: task.row_count }) }}
        </p>
        <p class="muted">
          {{ t("import.counts", { inserted: task.inserted, updated: task.updated, deleted: task.deleted }) }}
          <span v-if="!task.counts_exact">{{ t("import.countsApprox") }}</span>
        </p>
        <p v-if="task.failure_code" class="error">{{ codeText(task.failure_code, task.failure_message) }}</p>
        <p v-if="task.failure_message && task.failure_message !== codeText(task.failure_code)" class="muted">
          {{ task.failure_message }}
        </p>
      </div>
      <div v-if="task.error_count && errors.length" class="card">
        <div class="row" style="justify-content: space-between">
          <strong>{{ task.error_count }} {{ t("import.errors") }}</strong>
          <button class="ghost" :disabled="busy" @click="exportErrors">{{ t("import.exportErrors") }}</button>
        </div>
        <table class="data">
          <thead>
            <tr><th>{{ t("grid.rowNo") }}</th><th>{{ t("common.column") }}</th><th>{{ t("import.errors") }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in errors" :key="item.id">
              <td>{{ item.row_no }}</td>
              <td>{{ item.column }}</td>
              <td>{{ codeText(item.code) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="task.error_count > ERROR_PAGE_SIZE" class="row" style="margin-top: 12px">
          <button class="ghost" :disabled="errorPage === 1" @click="errorPage -= 1">{{ t("common.prev") }}</button>
          <span class="muted">{{ errorPage }}</span>
          <button class="ghost" :disabled="errorPage * ERROR_PAGE_SIZE >= task.error_count" @click="errorPage += 1">
            {{ t("common.next") }}
          </button>
        </div>
      </div>
      <div class="card">
        <h2>{{ t("import.logs") }}</h2>
        <p v-for="log in logs" :key="log.id" :class="log.level === 'INFO' ? 'muted' : 'error'">
          {{ new Date(log.ts).toLocaleString() }} · {{ logText(log) }}
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.actions { margin-left: auto; }
h2 { font-size: 16px; margin: 0 0 12px; }
</style>
