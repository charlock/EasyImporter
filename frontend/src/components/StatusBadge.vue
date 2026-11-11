<script setup lang="ts">
import { useI18n } from "vue-i18n";

import type { ImportStatus } from "@/lib/types";

defineProps<{ status: ImportStatus }>();
const { t } = useI18n();
</script>

<template>
  <span class="badge" :data-status="status">{{ t(`status.${status}`) }}</span>
</template>
