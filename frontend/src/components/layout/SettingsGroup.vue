<!-- 设定分组：invoice 页左侧表单的分组样式（标题 + 可选说明 + 内容）。
  与抽屉里的 DrawerSection 同款标题字号，区别是多了 description，用于详情设定页。 -->
<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>

<template>
  <section>
    <h3 class="mb-1 text-sm font-medium">{{ title }}</h3>
    <p v-if="description" class="mb-3 text-sm text-muted-foreground">{{ description }}</p>
    <slot />
  </section>
</template>
