import { createPinia } from "pinia";
import { createApp } from "vue";

import { i18n } from "@/locales";
import router from "@/router";
import App from "@/App.vue";
import "@/styles/base.css";

createApp(App).use(createPinia()).use(router).use(i18n).mount("#app");
