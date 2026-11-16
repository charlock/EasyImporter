/**
 * 快速导入插件：订阅 selection-change 写选区、cellStyle 按错误集标红、
 * setup 里把 viewer api 交给宿主。
 *
 * 不贡献 toolbar（快速导入按钮在页面停靠栏）；cellStyle 以外的样式与
 * overlay 提示不在本插件内。
 */
import { definePlugin, type CellStyleOverride, type ExcelPlugin, type ViewerApi } from "ooxml-excel-editor/core";

import { inferSelectionKind, type ViewerSelection } from "./useExcelViewer";

export interface QuickImportPluginOptions {
  onSelectionChange: (selection: ViewerSelection) => void;
  getErrorCells: () => ReadonlySet<string>;
  getDimension: () => { rows: number; cols: number } | null;
  onViewerReady?: (api: ViewerApi) => void;
}

/** 错误格覆盖样式（与 Spike 验证一致）：红底 #FECACA，四边 thin #DC2626。 */
export function errorCellStyle(): CellStyleOverride {
  return {
    fill: { type: "solid", fgColor: "#FECACA" },
    borders: {
      top: { style: "thin", color: "#DC2626" },
      bottom: { style: "thin", color: "#DC2626" },
      left: { style: "thin", color: "#DC2626" },
      right: { style: "thin", color: "#DC2626" },
    },
  };
}

export function createQuickImportPlugin(options: QuickImportPluginOptions): ExcelPlugin {
  return definePlugin({
    name: "easyimporter-quick-import",
    events: {
      "selection-change": (payload: {
        range: { top: number; left: number; bottom: number; right: number };
        active: { row: number; col: number };
      }) => {
        const dimension = options.getDimension();
        if (!dimension) return;
        options.onSelectionChange({
          range: { ...payload.range },
          active: { ...payload.active },
          kind: inferSelectionKind(payload.range, dimension),
        });
      },
    },
    cellStyle: (_cell, pos) => {
      if (options.getErrorCells().has(`${pos.row}:${pos.col}`)) return errorCellStyle();
      return undefined;
    },
    setup: (ctx) => {
      options.onViewerReady?.(ctx.viewer);
    },
  });
}
