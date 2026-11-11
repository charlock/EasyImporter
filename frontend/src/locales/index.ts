import { createI18n } from "vue-i18n";

import en from "./en";
import zh from "./zh";

export type Locale = "zh" | "en";

const stored = localStorage.getItem("ei-locale");
const locale: Locale = stored === "en" ? "en" : "zh";

export const i18n = createI18n({
  legacy: false,
  locale,
  fallbackLocale: "zh",
  messages: { zh, en },
});

export function setLocale(next: Locale): void {
  i18n.global.locale.value = next;
  localStorage.setItem("ei-locale", next);
  document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
}
