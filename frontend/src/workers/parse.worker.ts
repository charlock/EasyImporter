/// <reference lib="webworker" />
/** 在 Worker 里解析 .xlsx，避免大文件阻塞界面。 */

import { parseBuffer, type ParseOptions } from "@/features/excel/parse";

self.onmessage = async (event: MessageEvent<{ buffer: ArrayBuffer; options: ParseOptions }>) => {
  try {
    const result = await parseBuffer(event.data.buffer, event.data.options);
    self.postMessage({ ok: true, result });
  } catch (caught) {
    self.postMessage({ ok: false, message: caught instanceof Error ? caught.message : String(caught) });
  }
};
