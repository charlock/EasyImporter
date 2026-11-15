<script setup lang="ts">
import { Inbox } from "@lucide/vue";

defineProps<{ title: string; hint?: string }>();
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12 text-center">
    <Inbox class="size-8 text-muted-foreground" />
    <p class="font-medium">{{ title }}</p>
    <p v-if="hint" class="text-sm text-muted-foreground">{{ hint }}</p>
    <slot />
  </div>
</template>
