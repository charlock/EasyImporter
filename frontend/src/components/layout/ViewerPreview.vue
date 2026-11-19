<!-- excel-viewer 预览卡片：详情设定页右侧的预览区（invoice 页的 Preview 卡片位置）。
  只用 ExcelViewerHost 的公开接口；放大走全屏 API（同一 viewer 实例不重建），
  全屏不可用或被拒绝时退到 fixed 覆盖层；退出时恢复。
  高度：卡片本身是 flex 列，maxHeight 把整张卡（含标题栏）约束在内容区高度内，
  预览区 flex-1 min-h-0 收缩——一屏内能看到 Excel 全貌，包括底部 Sheet 标签；
  高度不写死像素，由调用方按粘住位置传 calc 值。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Maximize2, Minimize2 } from "@lucide/vue";
import type {
  CellChangePayload,
  ExcelPlugin,
  MergeRange,
  StructChangePayload,
  ViewerApi,
  WorkbookModel,
} from "ooxml-excel-editor/core";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ExcelViewerHost from "@/features/excel-viewer/ExcelViewerHost.vue";

const props = withDefaults(
  defineProps<{
    workbook: WorkbookModel | null;
    editable: boolean;
    plugins?: ExcelPlugin[];
    errorCells?: ReadonlySet<string>;
    title: string;
    /** 未放大时预览区的高度类名（不传 maxHeight 时的旧行为：固定视口高度）。 */
    containerClass?: string;
    /** 未放大时整张卡的最大高度（CSS 值，如 calc(100vh - 粘住偏移 - 底边距)）；
     * 传了它，卡片取该高度、预览区改为 flex-1 min-h-0 收缩，整张卡不超内容区
     * 高度（高度必须定死，flex 链才有确定尺寸可分，否则 viewer 会塌到 0）。 */
    maxHeight?: string;
  }>(),
  { containerClass: "h-[calc(100vh-13rem)] min-h-[480px]" },
);

const viewerContainerClass = computed(() =>
  props.maxHeight
    ? "min-h-0 flex-1 overflow-hidden rounded-lg border"
    : `${props.containerClass} overflow-hidden rounded-lg border`,
);

const emit = defineEmits<{
  "selection-change": [payload: { range: MergeRange; active: { row: number; col: number } }];
  "cell-change": [payload: CellChangePayload];
  "struct-change": [payload: StructChangePayload];
  "sheet-change": [payload: { index: number; name: string }];
  rendered: [workbook: WorkbookModel];
  error: [message: string];
  "viewer-ready": [api: ViewerApi];
}>();

const { t } = useI18n();

const container = ref<HTMLElement | null>(null);
const expanded = ref(false);
const fallback = ref(false);

function onFullscreenChange(): void {
  if (!document.fullscreenElement) {
    expanded.value = false;
    fallback.value = false;
  }
}

async function toggleExpand(): Promise<void> {
  if (expanded.value) {
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch {
        // 退出失败也直接收起覆盖层，不阻塞页面。
      }
    }
    fallback.value = false;
    expanded.value = false;
    return;
  }
  const el = container.value;
  if (!el) return;
  if (typeof el.requestFullscreen === "function") {
    try {
      await el.requestFullscreen();
      expanded.value = true;
      return;
    } catch {
      // 全屏被拒时退到覆盖层。
    }
  }
  fallback.value = true;
  expanded.value = true;
}

onMounted(() => document.addEventListener("fullscreenchange", onFullscreenChange));
onBeforeUnmount(() => document.removeEventListener("fullscreenchange", onFullscreenChange));
</script>

<template>
  <div
    ref="container"
    :class="expanded && fallback ? 'fixed inset-0 z-50 overflow-auto bg-background p-4' : ''"
  >
    <Card :class="expanded ? 'h-full' : 'flex min-h-0 flex-col'" :style="!expanded && props.maxHeight ? { height: props.maxHeight, maxHeight: props.maxHeight } : undefined">
      <CardHeader class="shrink-0">
        <CardTitle class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate">{{ title }}</span>
          <span class="flex shrink-0 items-center gap-2">
            <slot name="headerActions" />
            <Button
              variant="outline"
              size="sm"
              :title="expanded ? t('detail.exitExpand') : t('detail.expand')"
              @click="toggleExpand"
            >
              <Minimize2 v-if="expanded" class="mr-1 h-4 w-4" />
              <Maximize2 v-else class="mr-1 h-4 w-4" />
              {{ expanded ? t("detail.exitExpand") : t("detail.expand") }}
            </Button>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent class="flex min-h-0 flex-1 flex-col gap-3">
        <slot name="above" />
        <div :class="expanded ? 'h-[calc(100vh-10rem)] min-h-[480px] overflow-hidden rounded-lg border' : viewerContainerClass">
          <ExcelViewerHost
            v-if="workbook"
            :workbook="workbook"
            :editable="editable"
            :plugins="plugins"
            :error-cells="errorCells"
            height="100%"
            @selection-change="(payload) => emit('selection-change', payload)"
            @cell-change="(payload) => emit('cell-change', payload)"
            @struct-change="(payload) => emit('struct-change', payload)"
            @sheet-change="(payload) => emit('sheet-change', payload)"
            @rendered="(model) => emit('rendered', model)"
            @viewer-ready="(api) => emit('viewer-ready', api)"
            @error="(message) => emit('error', message)"
          />
          <div v-else class="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
            <slot name="empty">{{ t("common.loading") }}</slot>
          </div>
        </div>
        <p v-if="$slots.hint" class="text-xs text-muted-foreground"><slot name="hint" /></p>
      </CardContent>
    </Card>
  </div>
</template>
