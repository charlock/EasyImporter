<!--
  ExcelViewer 唯一挂载点。两页（模板页 / 导入页）共用，差异由 props 传入。
  - Ribbon / 操作工具栏 / 顶栏是三个不同的东西，分别处理：
    Ribbon 用 :ribbon="false"，工具栏用 :toolbar="false"，顶栏用 #header slot
    放真实隐藏节点（空 slot 会回退默认顶栏，见 Spike 报告）。
  - cellStyle 由 quickImportPlugin 负责，本组件不传 :cell-style。
  - plugins 必须用稳定引用（computed），禁止在模板里写内联数组字面量，
    否则每次渲染新建数组会反复触发插件初始化（曾致 OOM）。
  - 公式栏没有 prop：挂载后（rendered 后）调 toggleFormulaBar() 藏一次。
  - viewer api 的捕获优先走插件 setup（quickImportPlugin 的 onViewerReady），
    本组件以组件 ref 作回退，并同样发出 viewer-ready。
-->
<template>
  <ExcelViewer
    v-if="workbook"
    ref="viewerRef"
    :workbook="workbook"
    :ribbon="ribbonOff"
    :toolbar="false"
    :editable="editable"
    :theme="theme"
    :plugins="stablePlugins"
    :style="{ height: height ?? '100%' }"
    @rendered="onRendered"
    @selection-change="onSelectionChange"
    @cell-change="onCellChange"
    @struct-change="onStructChange"
    @sheet-change="onSheetChange"
    @error="onError"
  >
    <template #header><div style="display:none" aria-hidden="true"></div></template>
    <template #statusbar><div></div></template>
    <template #overlay="slotProps"><slot name="overlay" v-bind="slotProps" /></template>
  </ExcelViewer>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { ExcelViewer } from "ooxml-excel-editor";
import "ooxml-excel-editor/style.css";
import type {
  CellChangePayload,
  ExcelPlugin,
  MergeRange,
  StructChangePayload,
  ViewerApi,
  ViewerTheme,
  WorkbookModel,
} from "ooxml-excel-editor/core";

const props = defineProps<{
  workbook: WorkbookModel | null;
  editable: boolean;
  theme?: ViewerTheme;
  plugins?: ExcelPlugin[];
  /**
   * 错误格集合（key 为 `${row}:${col}`，0 基）。
   * 标红由 quickImportPlugin 的 cellStyle 钩子负责，本组件只声明该 prop
   * 以保持宿主接口完整，不在这里消费。
   */
  errorCells?: ReadonlySet<string>;
  /** 挂载高度；默认 100%，由外层容器定高。 */
  height?: string;
}>();

const emit = defineEmits<{
  "selection-change": [payload: { range: MergeRange; active: { row: number; col: number } }];
  "cell-change": [payload: CellChangePayload];
  /** 行列结构变更（插/删行列及其撤销/重做）：宿主只转发，是否重取数据由页面决定。 */
  "struct-change": [payload: StructChangePayload];
  "sheet-change": [payload: { index: number; name: string }];
  rendered: [workbook: WorkbookModel];
  error: [message: string];
  "viewer-ready": [api: ViewerApi];
}>();

const viewerRef = ref<InstanceType<typeof ExcelViewer> | null>(null);

/**
 * Ribbon 关闭值。d.ts 把 ribbon 定成 RibbonConfig（不接受 false），但运行时
 * prop 定义为任意类型，传 false 即关闭（Spike 已验证：DOM 无 ribbon 残留）。
 * 这里用断言绕过 d.ts，运行时行为与方案约定的 :ribbon="false" 完全一致；
 * 类型取自组件自身的 props 定义，不依赖库未导出的 RibbonConfig。
 */
type RibbonProp = InstanceType<typeof ExcelViewer>["$props"]["ribbon"];
const ribbonOff = false as unknown as RibbonProp;

/** plugins 用稳定引用：props.plugins 不变时不产生新数组。 */
const stablePlugins = computed<ExcelPlugin[]>(() => props.plugins ?? []);

let formulaBarHidden = false;
let viewerReadyEmitted = false;

/** 从组件 ref 回退捕获 viewer api（优先走插件 setup，本函数只作回退）。 */
function resolveViewerApi(): ViewerApi | null {
  const node = viewerRef.value as unknown as Record<string, unknown> | null;
  if (!node) return null;
  if (typeof node.toggleFormulaBar === "function") return node as unknown as ViewerApi;
  const api = node.api as Record<string, unknown> | undefined;
  if (api && typeof api.toggleFormulaBar === "function") return api as unknown as ViewerApi;
  const inner = node.viewer as Record<string, unknown> | undefined;
  if (inner && typeof inner.toggleFormulaBar === "function") return inner as unknown as ViewerApi;
  if (typeof node.getViewerApi === "function") {
    const got = (node.getViewerApi as () => unknown)();
    const record = got as Record<string, unknown> | null;
    if (record && typeof record.toggleFormulaBar === "function") {
      return record as unknown as ViewerApi;
    }
  }
  return null;
}

function captureViewerApi(): void {
  const api = resolveViewerApi();
  if (!api) return;
  if (!formulaBarHidden) {
    formulaBarHidden = true;
    try {
      if (api.isFormulaBarVisible?.() === true) api.toggleFormulaBar();
    } catch {
      // 公式栏隐藏失败不阻塞挂载；页面仍可正常使用。
    }
  }
  if (!viewerReadyEmitted) {
    viewerReadyEmitted = true;
    emit("viewer-ready", api);
  }
}

function onRendered(workbook: WorkbookModel): void {
  captureViewerApi();
  emit("rendered", workbook);
}

function onSelectionChange(payload: {
  range: MergeRange;
  active: { row: number; col: number };
}): void {
  emit("selection-change", payload);
}

function onCellChange(payload: CellChangePayload): void {
  emit("cell-change", payload);
}

function onStructChange(payload: StructChangePayload): void {
  emit("struct-change", payload);
}

function onSheetChange(payload: { index: number; name: string }): void {
  emit("sheet-change", payload);
}

function onError(message: string): void {
  emit("error", message);
}
</script>
