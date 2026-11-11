/** 用 ExcelJS 读 .xlsx，产出表头树和按表头路径索引的数据行。 */

import ExcelJS from "exceljs";

import { buildHeaderTree, type HeaderTree, type MergeRange } from "@/features/header/tree";

export interface ParsedSheet {
  name: string;
  header: HeaderTree;
  /** 每行以表头路径（用 \u0000 连接）为键。 */
  rows: Record<string, unknown>[];
  /** 与 rows 一一对应的 Excel 行号（从 1 起），空行被跳过时仍能对上原表。 */
  rowNumbers: number[];
  hiddenRows: number;
}

function cellText(value: ExcelJS.CellValue): string {
  if (value == null) return "";
  if (typeof value === "object") {
    if ("richText" in value) return value.richText.map((part) => part.text).join("");
    if ("result" in value) return cellText(value.result as ExcelJS.CellValue);
    if ("text" in value) return String(value.text);
    if (value instanceof Date) return value.toISOString().slice(0, 10);
  }
  return String(value);
}

export interface ParseOptions {
  sheet: string;
  /** 0 基。 */
  headerStartRow: number;
  headerRowCount: number;
}

/** 解析核心，只依赖 ArrayBuffer，主线程和 Worker 共用。 */
export async function parseBuffer(buffer: ArrayBuffer, options: ParseOptions): Promise<ParsedSheet> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const worksheet = workbook.getWorksheet(options.sheet) ?? workbook.worksheets[0];
  if (!worksheet) throw new Error("工作簿里没有工作表");

  const merges: MergeRange[] = [];
  const merged = (worksheet as unknown as { _merges?: Record<string, unknown> })._merges ?? {};
  for (const range of Object.values(merged)) {
    const model = (range as { model?: { top: number; left: number; bottom: number; right: number } }).model;
    if (model) {
      merges.push({
        top: model.top - 1,
        left: model.left - 1,
        bottom: model.bottom - 1,
        right: model.right - 1,
      });
    }
  }

  const headerCells = [];
  for (let row = options.headerStartRow; row < options.headerStartRow + options.headerRowCount; row += 1) {
    const sheetRow = worksheet.getRow(row + 1);
    const cells = [];
    for (let column = 1; column <= worksheet.columnCount; column += 1) {
      cells.push({ value: cellText(sheetRow.getCell(column).value) });
    }
    headerCells.push(cells);
  }
  const header = buildHeaderTree(headerCells, merges, options.headerStartRow);

  const rows: Record<string, unknown>[] = [];
  const rowNumbers: number[] = [];
  let hiddenRows = 0;
  const firstDataRow = options.headerStartRow + options.headerRowCount + 1;
  worksheet.eachRow({ includeEmpty: false }, (sheetRow, rowNumber) => {
    if (rowNumber < firstDataRow) return;
    if (sheetRow.hidden) hiddenRows += 1;
    const record: Record<string, unknown> = {};
    for (const leaf of header.leaves) {
      record[leaf.path.join("\u0000")] = cellText(sheetRow.getCell(leaf.column + 1).value);
    }
    rows.push(record);
    rowNumbers.push(rowNumber);
  });

  return { name: worksheet.name, header, rows, rowNumbers, hiddenRows };
}

/** 在主线程解析，适合模板编辑时的小样例文件。 */
export async function parseWorkbook(file: File, options: ParseOptions): Promise<ParsedSheet> {
  return parseBuffer(await file.arrayBuffer(), options);
}

type WorkerReply = { ok: true; result: ParsedSheet } | { ok: false; message: string };

/** 在 Worker 里解析，大文件不卡界面；浏览器不支持模块 Worker 时退回主线程。 */
export async function parseInWorker(file: File, options: ParseOptions): Promise<ParsedSheet> {
  const buffer = await file.arrayBuffer();
  let worker: Worker;
  try {
    worker = new Worker(new URL("../../workers/parse.worker.ts", import.meta.url), { type: "module" });
  } catch {
    return parseBuffer(buffer, options);
  }
  return new Promise<ParsedSheet>((resolve, reject) => {
    worker.onmessage = (event: MessageEvent<WorkerReply>) => {
      worker.terminate();
      if (event.data.ok) resolve(event.data.result);
      else reject(new Error(event.data.message));
    };
    worker.onerror = (event) => {
      worker.terminate();
      reject(new Error(event.message || "parse worker failed"));
    };
    worker.postMessage({ buffer, options }, [buffer]);
  });
}
