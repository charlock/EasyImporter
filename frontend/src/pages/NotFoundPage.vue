<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import { Button } from "@/components/ui/button";

const { t } = useI18n();
const router = useRouter();
</script>

<template>
  <div class="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
    <p class="text-6xl font-bold text-muted-foreground">404</p>
    <p class="text-lg font-medium">{{ t("common.empty") }}</p>
    <div class="flex gap-2">
      <Button @click="router.push('/')">{{ t("nav.dashboard") }}</Button>
      <Button variant="outline" @click="router.back()">{{ t("common.back") }}</Button>
    </div>
  </div>
</template>
