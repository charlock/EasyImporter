/**
 * 解析 Worker：把库的 parseWorkbook 包在 module Worker 里跑，
 * 主线程只收发消息，绝不直接 import 库的 core。
 * 注意：库发布包自带的 parseInWorker 是主线程解析（构建期被 stub 替换），
 * 所以这里必须自己包 Worker。
 *
 * 消息协议：
 *   入：{ id: string, buffer: ArrayBuffer }（buffer 用 transfer 传递）
 *   出：{ type: 'progress', id, progress }（progress 为库的 ParseProgress）
 *      / { type: 'done', id, model }
 *      / { type: 'error', id, message }
 */
import { parseWorkbook } from "ooxml-excel-editor/core";

self.onmessage = async (event: MessageEvent<{ id: string; buffer: ArrayBuffer }>) => {
  const { id, buffer } = event.data;
  try {
    const model = await parseWorkbook(buffer, (progress) => {
      // 开头的分号防 ASI 陷阱：上一行以 ) 结尾时不能被解析为函数调用延续。
      ;(self as unknown as { postMessage: (message: unknown) => void }).postMessage({
        type: "progress",
        id,
        progress,
      });
    });
    ;(self as unknown as { postMessage: (message: unknown) => void }).postMessage({
      type: "done",
      id,
      model,
    });
  } catch (error: unknown) {
    ;(self as unknown as { postMessage: (message: unknown) => void }).postMessage({
      type: "error",
      id,
      message: String((error as Error)?.stack || (error as Error)?.message || error),
    });
  }
};
