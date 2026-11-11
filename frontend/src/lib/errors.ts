/** 把后端错误码翻译成当前语言；没有翻译时退回后端给的中文说明。 */

import { ApiError } from "@/api/client";
import { i18n } from "@/locales";

export function codeText(code: string, fallback = ""): string {
  const key = `errors.${code}`;
  if (code && i18n.global.te(key)) return i18n.global.t(key);
  return fallback || code;
}

export function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) return codeText(caught.code, caught.message);
  if (caught instanceof TypeError) return codeText("NETWORK", caught.message);
  return caught instanceof Error ? caught.message : String(caught);
}

/** 不带参数的日志码；其余日志码缺参数（旧数据）时退回后端写入的原文。 */
const PARAMLESS_LOGS = new Set(["TASK_CANCELLED"]);

export function logText(log: { code: string; params: Record<string, unknown>; message: string }): string {
  const key = `logs.${log.code}`;
  if (i18n.global.te(key)) {
    if (PARAMLESS_LOGS.has(log.code)) return i18n.global.t(key);
    if (log.params && Object.keys(log.params).length) return i18n.global.t(key, log.params);
    return log.message;
  }
  return codeText(log.code, log.message);
}
