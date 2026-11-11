<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink, RouterView, useRouter } from "vue-router";

import WorkspaceSelect from "@/components/WorkspaceSelect.vue";
import { setLocale, type Locale } from "@/locales";
import { useSession } from "@/stores/session";

const session = useSession();
const router = useRouter();
const { t, locale } = useI18n();

const workspaceId = ref<number | null>(session.workspaces[0]?.id ?? null);
const theme = ref<"light" | "dark" | "system">(
  (localStorage.getItem("ei-theme") as "light" | "dark" | "system") ?? "system",
);

const links = computed(() => {
  const base = [
    { to: "/import", label: t("nav.import") },
    { to: "/imports", label: t("nav.imports") },
    { to: "/templates", label: t("nav.templates") },
  ];
  if (session.isAdmin) {
    base.push({ to: "/datasources", label: t("nav.datasources") });
    base.push({ to: "/admin", label: t("nav.admin") });
  }
  return base;
});

watchEffect(() => {
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("ei-theme", theme.value);
});

function changeLocale(event: Event): void {
  setLocale((event.target as HTMLSelectElement).value as Locale);
}

function changeTheme(event: Event): void {
  theme.value = (event.target as HTMLSelectElement).value as typeof theme.value;
}

async function logout(): Promise<void> {
  await session.logout();
  await router.push("/login");
}
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">{{ t("app.name") }}</RouterLink>
      <nav>
        <RouterLink v-for="link in links" :key="link.to" :to="link.to">{{ link.label }}</RouterLink>
      </nav>
      <div class="topbar-tools">
        <WorkspaceSelect v-model="workspaceId" :workspaces="session.workspaces" />
        <select :value="locale" aria-label="language" @change="changeLocale">
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
        <select :value="theme" aria-label="theme" @change="changeTheme">
          <option value="light">{{ t("theme.light") }}</option>
          <option value="dark">{{ t("theme.dark") }}</option>
          <option value="system">{{ t("theme.system") }}</option>
        </select>
        <RouterLink to="/password">{{ t("nav.password") }}</RouterLink>
        <button class="ghost" @click="logout">{{ t("nav.logout") }}</button>
      </div>
    </header>
    <main>
      <RouterView :workspace-id="workspaceId" />
    </main>
  </div>
</template>
