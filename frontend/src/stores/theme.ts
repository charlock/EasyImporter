import { defineStore } from "pinia";
import { ref } from "vue";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "ei-theme";

/** 解析实际生效的明暗模式：system 跟随操作系统偏好。 */
export function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** 开屏前同步调用一次，避免主题闪烁。 */
export function applyThemeClass(theme: Theme): void {
  document.documentElement.classList.toggle("dark", resolveTheme(theme) === "dark");
}

export function readStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

export const useTheme = defineStore("theme", () => {
  const theme = ref<Theme>(readStoredTheme());

  function apply(): void {
    applyThemeClass(theme.value);
    localStorage.setItem(STORAGE_KEY, theme.value);
  }

  function set(next: Theme): void {
    theme.value = next;
    apply();
  }

  // system 模式下跟随操作系统切换。
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (theme.value === "system") apply();
    });

  apply();
  return { theme, set, apply };
});
