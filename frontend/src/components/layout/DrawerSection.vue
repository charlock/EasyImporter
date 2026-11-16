<!-- 抽屉 section 外壳：h3.mb-3 + 内容，与模板页设定窗内的 section 间距一致。 -->
<script setup lang="ts">
defineProps<{ title: string }>();
</script>

<template>
  <section>
    <h3 class="mb-3 text-sm font-medium">{{ title }}</h3>
    <slot />
  </section>
</template>
