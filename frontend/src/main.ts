import { createPinia } from "pinia";
import { createApp } from "vue";

import { i18n } from "@/locales";
import router from "@/router";
import { applyThemeClass, readStoredTheme } from "@/stores/theme";
import App from "@/App.vue";
import "@/styles/index.css";

// 开屏前先按保存的主题写好 .dark，避免闪烁。
applyThemeClass(readStoredTheme());

createApp(App).use(createPinia()).use(router).use(i18n).mount("#app");
