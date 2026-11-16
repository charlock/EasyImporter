<!-- 非模态右侧抽屉外壳：模板页与导入页共用。
  非模态（:modal="false"），以便开着抽屉时仍能在主区域点选；reka 在非模态下不渲染遮罩。
  注意：Sheet 默认 fixed inset-y-0 z-50，会盖住 AppShell 头部右侧与停靠栏右侧的按钮
  （保存/取消/配置等点不到）。这里用行内 top 把抽屉顶边推到停靠栏底边之下
  （3.5rem 头部 + 1.5rem 主区上内边距（md 下 p-6）+ 停靠栏高），z-index 降到 20
  （低于停靠栏的 30），height:auto 配 inset-y-0 的 bottom:0 使抽屉恰好撑满剩余高度。
  停靠栏高度由 dockBarHeightPx 传入，默认 53px：两页在 1440px 视口下均为单行，
  最高子元素都是实测 36px 高的 SelectTrigger（模板页是 size-9=36px 的图标按钮；
  导入页触发器 class 上写 h-8，但 shadcn-vue SelectTrigger 自带的默认 h-9 在层叠
  中胜出，实测也是 36px）：36 + py-2 上下 16 + border-b 1 = 53。若某页停靠栏
  在窄视口折成两行，顶边会相应偏上，需按实际行高传 dockBarHeightPx。
  pointer-down-outside / focus-outside 均 preventDefault：点抽屉外不关闭抽屉。 -->
<script setup lang="ts">
import { computed } from "vue";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

const open = defineModel<boolean>("open", { default: false });

const props = withDefaults(defineProps<{ dockBarHeightPx?: number }>(), { dockBarHeightPx: 53 });

const contentStyle = computed(
  () => `top: calc(3.5rem + 1.5rem + ${props.dockBarHeightPx}px); z-index: 20; height: auto`,
);
</script>

<template>
  <Sheet :modal="false" :open="open" @update:open="(value) => (open = value)">
    <SheetContent
      side="right"
      class="w-full overflow-y-auto p-5 sm:max-w-[640px]"
      :style="contentStyle"
      @pointer-down-outside="(event) => event.preventDefault()"
      @focus-outside="(event) => event.preventDefault()"
    >
      <SheetHeader class="border-b pb-4">
        <SheetTitle><slot name="title" /></SheetTitle>
      </SheetHeader>
      <slot />
    </SheetContent>
  </Sheet>
</template>
