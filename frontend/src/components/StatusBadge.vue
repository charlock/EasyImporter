<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { Badge } from "@/components/ui/badge";
import type { ImportStatus } from "@/lib/types";

defineProps<{ status: ImportStatus }>();
const { t } = useI18n();

const tone: Record<ImportStatus, string> = {
  SUCCEEDED: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  FAILED: "border-destructive/30 bg-destructive/15 text-destructive",
  UNKNOWN: "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-400",
  QUEUED: "border-transparent bg-secondary text-secondary-foreground",
  RUNNING: "border-sky-500/30 bg-sky-500/15 text-sky-700 dark:text-sky-400",
  COMMITTING: "border-sky-500/30 bg-sky-500/15 text-sky-700 dark:text-sky-400",
  CANCELLED: "border-transparent bg-secondary text-secondary-foreground",
};
</script>

<template>
  <Badge variant="outline" :class="tone[status]">{{ t(`status.${status}`) }}</Badge>
</template>
