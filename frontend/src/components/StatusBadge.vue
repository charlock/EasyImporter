<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { Badge } from "@/components/ui/badge";
import { badgeToneClass, importStatusTone } from "@/components/list/listTypes";
import type { ImportStatus } from "@/lib/types";

defineProps<{ status: ImportStatus }>();
const { t } = useI18n();
</script>

<template>
  <Badge variant="outline" :class="badgeToneClass[importStatusTone(status)]">{{ t(`status.${status}`) }}</Badge>
</template>
