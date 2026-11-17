import { describe, expect, it } from "vitest";

import type { AdaptedSheet } from "@/features/excel-viewer/modelAdapter";
import type { ImportError, Mapping } from "@/lib/types";

import { buildErrorCells, canDeleteImport, errorCellPosition } from "./importRecords";

/** 只有 errorCellPosition 用到的两个字段，其余按 AdaptedSheet 断言补齐。 */
function fakeSheet(): AdaptedSheet {
  return {
    rowNumbers: [2, 3, 5],
    leafColumns: new Map([
      ["流水号", 0],
      ["金额", 2],
    ]),
  } as unknown as AdaptedSheet;
}

const MAPPING: Mapping = {
  columns: [
    { excel_path: ["流水号"], db_column: "serial_no" },
    { excel_path: ["金额"], db_column: "amount" },
  ],
  unpivot: null,
  constants: [],
};

function fakeError(row_no: number, column: string): ImportError {
  return { id: 1, row_no, column, code: "TYPE_MISMATCH", params: {} };
}

describe("canDeleteImport", () => {
  it("终态与排队中可删，执行中/提交中不可删", () => {
    expect(canDeleteImport("SUCCEEDED")).toBe(true);
    expect(canDeleteImport("FAILED")).toBe(true);
    expect(canDeleteImport("CANCELLED")).toBe(true);
    expect(canDeleteImport("UNKNOWN")).toBe(true);
    expect(canDeleteImport("QUEUED")).toBe(true);
    expect(canDeleteImport("RUNNING")).toBe(false);
    expect(canDeleteImport("COMMITTING")).toBe(false);
  });
});

describe("errorCellPosition", () => {
  it("行号在 rowNumbers 里时取对应 1 基行号再转 0 基", () => {
    expect(errorCellPosition(fakeError(3, "amount"), MAPPING, fakeSheet())).toEqual({
      row: 2,
      column: 2,
    });
  });

  it("行号不在 rowNumbers 里时退回 row_no - 1", () => {
    expect(errorCellPosition(fakeError(4, "serial_no"), MAPPING, fakeSheet())).toEqual({
      row: 3,
      column: 0,
    });
  });

  it("映射里没有该目标字段时不跳格", () => {
    expect(errorCellPosition(fakeError(2, "no_such_column"), MAPPING, fakeSheet())).toBeNull();
  });

  it("表头里没有该叶子列时不跳格", () => {
    const mapping: Mapping = {
      ...MAPPING,
      columns: [{ excel_path: ["不存在的列"], db_column: "amount" }],
    };
    expect(errorCellPosition(fakeError(2, "amount"), mapping, fakeSheet())).toBeNull();
  });

  it("没有适配好的表时不跳格", () => {
    expect(errorCellPosition(fakeError(2, "amount"), MAPPING, null)).toBeNull();
  });
});

describe("errorCellPosition（拆行度量列）", () => {
  /** 两组拆行：2024-01 的金额在第 2 列，2024-02 的金额在第 3 列。 */
  const UNPIVOT_MAPPING: Mapping = {
    columns: [{ excel_path: ["流水号"], db_column: "serial_no" }],
    unpivot: {
      dimension_column: "month",
      groups: [
        { dimension_value: "2024-01", match_prefix: ["2024-01"] },
        { dimension_value: "2024-02", match_prefix: ["2024-02"] },
      ],
      measures: [{ excel_leaf: "金额", db_column: "amount" }],
      skip_empty_measures: true,
    },
    constants: [],
  };

  function unpivotSheet(rows: Record<string, unknown>[]): AdaptedSheet {
    return {
      rowNumbers: [2, 3, 5],
      rows,
      leafColumns: new Map([
        ["流水号", 0],
        ["2024-01\u0000金额", 2],
        ["2024-02\u0000金额", 3],
      ]),
    } as unknown as AdaptedSheet;
  }

  it("度量列定位到有文本坏值的分组", () => {
    const sheet = unpivotSheet([
      {},
      { "2024-01\u0000金额": 100, "2024-02\u0000金额": "待定" },
      {},
    ]);
    expect(errorCellPosition(fakeError(3, "amount"), UNPIVOT_MAPPING, sheet)).toEqual({
      row: 2,
      column: 3,
    });
  });

  it("度量列只有数字值时定位到有值的分组", () => {
    const sheet = unpivotSheet([
      {},
      { "2024-01\u0000金额": 100, "2024-02\u0000金额": null },
      {},
    ]);
    expect(errorCellPosition(fakeError(3, "amount"), UNPIVOT_MAPPING, sheet)).toEqual({
      row: 2,
      column: 2,
    });
  });

  it("度量列全空时（必填缺失）仍落到首个分组", () => {
    const sheet = unpivotSheet([{}, {}, {}]);
    expect(errorCellPosition(fakeError(3, "amount"), UNPIVOT_MAPPING, sheet)).toEqual({
      row: 2,
      column: 2,
    });
  });

  it("度量列行号不在 rowNumbers 里时落到首个分组、行号退回 row_no - 1", () => {
    const sheet = unpivotSheet([{}, {}, {}]);
    expect(errorCellPosition(fakeError(4, "amount"), UNPIVOT_MAPPING, sheet)).toEqual({
      row: 3,
      column: 2,
    });
  });

  it("映射里没有该度量列时不跳格", () => {
    const sheet = unpivotSheet([
      {},
      { "2024-01\u0000金额": "待定", "2024-02\u0000金额": "待定" },
      {},
    ]);
    expect(errorCellPosition(fakeError(3, "no_such_column"), UNPIVOT_MAPPING, sheet)).toBeNull();
  });

  it("度量列的叶子都不在表头里时不跳格", () => {
    const sheet = unpivotSheet([
      {},
      { "2024-01\u0000金额": "待定" },
      {},
    ]) as unknown as AdaptedSheet;
    sheet.leafColumns = new Map([["流水号", 0]]);
    expect(errorCellPosition(fakeError(3, "amount"), UNPIVOT_MAPPING, sheet)).toBeNull();
  });

  it("度量列错误也进标红格集合", () => {
    const sheet = unpivotSheet([
      {},
      { "2024-01\u0000金额": 100, "2024-02\u0000金额": "待定" },
      {},
    ]);
    const cells = buildErrorCells(
      [fakeError(3, "amount"), fakeError(2, "serial_no")],
      UNPIVOT_MAPPING,
      sheet,
    );
    expect([...cells].sort()).toEqual(["1:0", "2:3"]);
  });
});

describe("buildErrorCells", () => {
  it("只收录能定位的错误并去重", () => {
    const cells = buildErrorCells(
      [fakeError(2, "amount"), fakeError(2, "amount"), fakeError(3, "no_such_column")],
      MAPPING,
      fakeSheet(),
    );
    expect([...cells]).toEqual(["1:2"]);
  });
});
