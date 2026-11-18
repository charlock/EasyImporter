<!-- excel-viewer 预览卡片：详情设定页右侧的预览区（invoice 页的 Preview 卡片位置）。
  只用 ExcelViewerHost 的公开接口；放大走全屏 API（同一 viewer 实例不重建），
  全屏不可用或被拒绝时退到 fixed 覆盖层；退出时恢复。 -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
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
    /** 未放大时的容器高度类名（默认与两页现有的 viewer 高度一致）。 */
    containerClass?: string;
  }>(),
  { containerClass: "h-[calc(100vh-13rem)] min-h-[480px]" },
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
    <Card :class="expanded ? 'h-full' : ''">
      <CardHeader>
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
      <CardContent class="space-y-3">
        <slot name="above" />
        <div :class="expanded ? 'h-[calc(100vh-10rem)] min-h-[480px] overflow-hidden rounded-lg border' : `${props.containerClass} overflow-hidden rounded-lg border`">
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
