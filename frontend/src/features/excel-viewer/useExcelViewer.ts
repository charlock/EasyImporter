/**
 * ExcelViewer 组合式函数：持有 viewer api / workbook 模型 / 当前表 / 选区，
 * 以及 loadFile / selectSheet / setSelection / scrollToCell / getRangeData /
 * exportXlsx / exportCsv / undo / redo。
 *
 * 注意：不要用 setSelection 程序化模拟整列选区——库会把 top=0 的单列 range
 * 归一化为全宽（Spike 已验证）；该方法只用于真实导航定位，选区推断以真实
 * 点击事件（onSelectionChange）为准。
 */
import { computed, ref, type ComputedRef, type Ref } from "vue";

import type {
  MergeRange,
  ReadOptions,
  ViewerApi,
  WorkbookModel,
  XlsxExportOptions,
} from "ooxml-excel-editor/core";

import { sheetNames } from "./modelAdapter";

export type SelectionKind = "row" | "column" | "cell" | "range";

export interface ViewerSelection {
  range: { top: number; left: number; bottom: number; right: number };
  active: { row: number; col: number };
  kind: SelectionKind;
}

export interface SelectionRange {
  top: number;
  left: number;
  bottom: number;
  right: number;
}

/**
 * 按 range 与当前表 dimension 推断选区种类（多选区只取第一个）。
 * row：left=0 且 right=cols-1 且 top=bottom；
 * column：top=0 且 bottom=rows-1 且 left=right；
 * cell：1x1；其余 range。
 */
export function inferSelectionKind(
  range: SelectionRange,
  dimension: { rows: number; cols: number },
): SelectionKind {
  const isSingleCell = range.top === range.bottom && range.left === range.right;
  if (isSingleCell) return "cell";
  if (range.left === 0 && range.right === dimension.cols - 1 && range.top === range.bottom) {
    return "row";
  }
  if (range.top === 0 && range.bottom === dimension.rows - 1 && range.left === range.right) {
    return "column";
  }
  return "range";
}

/** Worker 消息协议（与 parse.worker.ts 对应）。 */
type WorkerResponse =
  | { type: "progress"; id: string; progress: { stage: string; ratio?: number } | number }
  | { type: "done"; id: string; model: WorkbookModel }
  | { type: "error"; id: string; message: string };

const PARSE_TIMEOUT_MS = 60_000;

let workerSeq = 0;

export interface UseExcelViewerReturn {
  viewerApi: Ref<ViewerApi | null>;
  workbook: Ref<WorkbookModel | null>;
  sourceBuffer: Ref<ArrayBuffer | null>;
  activeSheetIndex: Ref<number>;
  sheetNamesList: ComputedRef<string[]>;
  selection: Ref<ViewerSelection | null>;
  parsing: Ref<boolean>;
  parseProgress: Ref<number | null>;
  canUndo: Ref<boolean>;
  canRedo: Ref<boolean>;
  loadFile: (file: File) => Promise<WorkbookModel>;
  selectSheet: (index: number) => void;
  setSelection: (range: MergeRange) => void;
  scrollToCell: (row: number, col: number, opts?: { select?: boolean }) => boolean;
  getRangeData: (sheetIndex: number, range: MergeRange, opts?: ReadOptions) => unknown[][];
  exportXlsx: (opts?: XlsxExportOptions) => Promise<Blob>;
  exportCsv: (opts?: { target?: number; format?: boolean }) => Promise<Blob>;
  undo: () => void;
  redo: () => void;
  setViewerApi: (api: ViewerApi | null) => void;
  onSelectionChange: (payload: {
    range: SelectionRange;
    active: { row: number; col: number };
  }) => void;
}

export function useExcelViewer(): UseExcelViewerReturn {
  const viewerApi = ref<ViewerApi | null>(null);
  const workbook = ref<WorkbookModel | null>(null);
  const sourceBuffer = ref<ArrayBuffer | null>(null);
  const activeSheetIndex = ref(0);
  const sheetNamesList = computed(() => sheetNames(workbook.value));
  const selection = ref<ViewerSelection | null>(null);
  const parsing = ref(false);
  const parseProgress = ref<number | null>(null);
  const canUndo = ref(false);
  const canRedo = ref(false);

  function refreshUndoRedo(): void {
    try {
      canUndo.value = viewerApi.value?.canUndo?.() ?? false;
      canRedo.value = viewerApi.value?.canRedo?.() ?? false;
    } catch {
      canUndo.value = false;
      canRedo.value = false;
    }
  }

  function setViewerApi(api: ViewerApi | null): void {
    viewerApi.value = api;
    refreshUndoRedo();
  }

  /** 主线程回退：Worker 构造失败时用库的 parseWorkbook 直接解析。 */
  async function parseOnMainThread(buffer: ArrayBuffer): Promise<WorkbookModel> {
    const { parseWorkbook } = await import("ooxml-excel-editor/core");
    return parseWorkbook(buffer, (progress) => {
      parseProgress.value = typeof progress.ratio === "number" ? progress.ratio : null;
    });
  }

  /** Worker 内解析：单次请求一个 Worker，完成后 terminate。 */
  function parseInWorker(buffer: ArrayBuffer): Promise<WorkbookModel> {
    const worker = new Worker(new URL("./parse.worker.ts", import.meta.url), { type: "module" });
    const id = `w${++workerSeq}`;
    return new Promise<WorkbookModel>((resolve, reject) => {
      const timer = setTimeout(() => {
        worker.terminate();
        reject(new Error("解析超时（60s）"));
      }, PARSE_TIMEOUT_MS);
      const done = (fn: () => void) => {
        clearTimeout(timer);
        worker.terminate();
        fn();
      };
      worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
        const data = event.data;
        if (data.id !== id) return;
        if (data.type === "progress") {
          const progress = data.progress;
          parseProgress.value =
            typeof progress === "number"
              ? progress
              : typeof progress.ratio === "number"
                ? progress.ratio
                : null;
          return;
        }
        if (data.type === "done") done(() => resolve(data.model));
        else done(() => reject(new Error(data.message || "解析失败")));
      };
      worker.onerror = (event) => {
        done(() => reject(new Error(event.message || "解析 Worker 加载/运行失败")));
      };
      worker.postMessage({ id, buffer }, [buffer]);
    });
  }

  async function loadFile(file: File): Promise<WorkbookModel> {
    parsing.value = true;
    parseProgress.value = null;
    selection.value = null;
    try {
      const buffer = await file.arrayBuffer();
      // 保留原件用于 overlay 导出；发给 Worker 的那份用 transfer 传递（会 detach）。
      sourceBuffer.value = buffer.slice(0);
      let model: WorkbookModel;
      try {
        model = await parseInWorker(buffer);
      } catch (error) {
        // 只有 Worker 不可用（构造/加载失败）才回退主线程；
        // 解析超时与解析错误直接抛出，不回退。
        if (error instanceof Error && /Worker/.test(error.message)) {
          model = await parseOnMainThread(sourceBuffer.value.slice(0));
        } else {
          throw error;
        }
      }
      workbook.value = model;
      activeSheetIndex.value = model.activeSheet ?? 0;
      return model;
    } finally {
      parsing.value = false;
      parseProgress.value = null;
    }
  }

  function selectSheet(index: number): void {
    const model = workbook.value;
    if (model && (index < 0 || index >= model.sheets.length)) return;
    activeSheetIndex.value = index;
    viewerApi.value?.setActiveSheet(index);
  }

  function setSelection(range: MergeRange): void {
    viewerApi.value?.setSelection(range);
  }

  function scrollToCell(row: number, col: number, opts?: { select?: boolean }): boolean {
    return viewerApi.value?.scrollToCell(row, col, opts) ?? false;
  }

  function getRangeData(
    sheetIndex: number,
    range: MergeRange,
    opts?: ReadOptions,
  ): unknown[][] {
    const api = viewerApi.value;
    if (!api) return [];
    return api.getRangeData(range, opts, sheetIndex) as unknown[][];
  }

  async function exportXlsx(opts?: XlsxExportOptions): Promise<Blob> {
    const api = viewerApi.value;
    if (!api) throw new Error("Viewer 未就绪，无法导出");
    // 默认 overlay（有原件时叠加编辑，保留条件格式/数据验证等未建模部件；
    // 无原件时库自动回退 rebuild）。调用方可在 opts 里覆盖 fidelity。
    return api.exportXlsx({
      fidelity: "overlay",
      ...(sourceBuffer.value ? { sourceBuffer: sourceBuffer.value } : {}),
      ...opts,
    });
  }

  async function exportCsv(opts?: { target?: number; format?: boolean }): Promise<Blob> {
    const api = viewerApi.value;
    if (!api) throw new Error("Viewer 未就绪，无法导出");
    // 注意：库的 exportCsv 同步返回 string（非 Blob），这里按约定包成带 BOM 的 Blob。
    const text = api.exportCsv(opts);
    return new Blob(["\uFEFF", text], { type: "text/csv;charset=utf-8" });
  }

  function undo(): void {
    viewerApi.value?.undo();
    refreshUndoRedo();
  }

  function redo(): void {
    viewerApi.value?.redo();
    refreshUndoRedo();
  }

  /** 由宿主调用：按当前 model 的 dimension 推断 kind 后写 selection ref。 */
  function onSelectionChange(payload: {
    range: SelectionRange;
    active: { row: number; col: number };
  }): void {
    const model = workbook.value;
    if (!model) return;
    const sheet = model.sheets[activeSheetIndex.value];
    if (!sheet) return;
    selection.value = {
      range: { ...payload.range },
      active: { ...payload.active },
      kind: inferSelectionKind(payload.range, sheet.dimension),
    };
  }

  return {
    viewerApi,
    workbook,
    sourceBuffer,
    activeSheetIndex,
    sheetNamesList,
    selection,
    parsing,
    parseProgress,
    canUndo,
    canRedo,
    loadFile,
    selectSheet,
    setSelection,
    scrollToCell,
    getRangeData,
    exportXlsx,
    exportCsv,
    undo,
    redo,
    setViewerApi,
    onSelectionChange,
  };
}
