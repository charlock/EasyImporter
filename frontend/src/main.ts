import { createPinia } from "pinia";
import { createApp } from "vue";

import { setSessionExpiredHandler } from "@/api/client";
import { i18n } from "@/locales";
import router from "@/router";
import { useSession } from "@/stores/session";
import { applyThemeClass, readStoredTheme } from "@/stores/theme";
import App from "@/App.vue";
import "@/styles/index.css";

// 开屏前先按保存的主题写好 .dark，避免闪烁。
applyThemeClass(readStoredTheme());

const app = createApp(App).use(createPinia()).use(router).use(i18n);

/**
 * 会话过期时自动回登录页：只跳转一次；登录成功后回到过期前的页面，
 * 并在登录页提示会话已过期。已在 /login 时不再带 redirect，避免循环。
 */
setSessionExpiredHandler(() => {
  const session = useSession();
  const redirect = router.currentRoute.value.fullPath;
  session.reset();
  void router.push({
    path: "/login",
    query: {
      ...(redirect && redirect !== "/login" && !redirect.startsWith("/login?")
        ? { redirect }
        : {}),
      expired: "1",
    },
  });
});

app.mount("#app");
