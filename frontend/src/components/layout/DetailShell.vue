<!-- 详情设定页壳：参考 studio-admin invoice 页。
  头部（标题+描述+右上操作）/ 两栏：左侧设定分组（groups 插槽，可滚动），
  右侧预览（preview 插槽，窄屏时落到下方；宽屏时粘在视口内）。
  showHeader=false 时只留两栏（模板页用 DockBar 当头部）。 -->
<script setup lang="ts">
import PageHeader from "@/components/PageHeader.vue";

withDefaults(
  defineProps<{
    title?: string;
    description?: string;
    showHeader?: boolean;
    /** 预览栏粘住时离视口顶部的距离；模板页要越过 DockBar，传 calc(3.5rem + 53px + 1.5rem)。 */
    previewStickyTop?: string;
  }>(),
  { showHeader: true, previewStickyTop: "calc(3.5rem + 1.5rem)" },
);
</script>

<template>
  <div class="space-y-6">
    <PageHeader v-if="showHeader" :title="title ?? ''" :description="description">
      <template #actions><slot name="actions" /></template>
    </PageHeader>
    <div class="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <div class="min-w-0 space-y-6"><slot name="groups" /></div>
      <div
        class="min-w-0 lg:sticky lg:self-start"
        :style="{ top: previewStickyTop }"
      >
        <slot name="preview" />
      </div>
    </div>
  </div>
</template>
