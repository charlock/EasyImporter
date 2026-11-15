<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>

<template>
  <header class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">{{ title }}</h1>
      <p v-if="description" class="text-muted-foreground">{{ description }}</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
