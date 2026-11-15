<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { RouterView, useRoute } from "vue-router";
import { Check, Languages, Monitor, Moon, Sun } from "@lucide/vue";

import AppSidebar from "@/components/app-sidebar/AppSidebar.vue";
import WorkspaceSelect from "@/components/WorkspaceSelect.vue";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { setLocale, type Locale } from "@/locales";
import { useSession } from "@/stores/session";
import { useTheme, type Theme } from "@/stores/theme";

const session = useSession();
const themeStore = useTheme();
const route = useRoute();
const { t, locale } = useI18n();

const workspaceId = ref<number | null>(session.workspaces[0]?.id ?? null);

// 工作区列表是异步加载的，加载完成后再默认选中第一个。
watch(
  () => session.workspaces,
  (items) => {
    if (workspaceId.value == null && items.length > 0) workspaceId.value = items[0].id;
    if (workspaceId.value != null && !items.some((item) => item.id === workspaceId.value)) {
      workspaceId.value = items[0]?.id ?? null;
    }
  },
  { immediate: true },
);

const crumbs = computed(() => {
  const items = route.matched
    .filter((record) => typeof record.meta.titleKey === "string")
    .map((record) => ({
      label: t(record.meta.titleKey as string),
      to: record.path.replace(/:id/g, String(route.params.id ?? "")),
    }));
  if (route.params.id != null && items.length > 0) {
    items.push({ label: `#${route.params.id}`, to: "" });
  }
  return items;
});

const themeIcon = computed(() => {
  if (themeStore.theme === "dark") return Moon;
  if (themeStore.theme === "system") return Monitor;
  return Sun;
});

const themeOptions: { value: Theme; labelKey: string; icon: typeof Sun }[] = [
  { value: "light", labelKey: "theme.light", icon: Sun },
  { value: "dark", labelKey: "theme.dark", icon: Moon },
  { value: "system", labelKey: "theme.system", icon: Monitor },
];

const localeOptions: { value: Locale; label: string }[] = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset class="min-w-0 max-w-full">
      <header
        class="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-2 border-b bg-background px-4"
      >
        <SidebarTrigger class="-ml-1" />
        <Separator orientation="vertical" class="mr-2 h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            <template v-for="(crumb, index) in crumbs" :key="index">
              <BreadcrumbItem>
                <BreadcrumbLink v-if="crumb.to && index < crumbs.length - 1" :href="crumb.to">
                  {{ crumb.label }}
                </BreadcrumbLink>
                <BreadcrumbPage v-else>{{ crumb.label }}</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator v-if="index < crumbs.length - 1" />
            </template>
          </BreadcrumbList>
        </Breadcrumb>
        <div class="flex-1" />
        <WorkspaceSelect v-model="workspaceId" :workspaces="session.workspaces" />
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="icon" :aria-label="t('theme.title')">
              <component :is="themeIcon" class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              v-for="option in themeOptions"
              :key="option.value"
              @click="themeStore.set(option.value)"
            >
              <component :is="option.icon" class="size-4" />
              {{ t(option.labelKey) }}
              <Check v-if="themeStore.theme === option.value" class="ml-auto size-4" />
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="icon" aria-label="language">
              <Languages class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              v-for="option in localeOptions"
              :key="option.value"
              @click="setLocale(option.value)"
            >
              {{ option.label }}
              <Check v-if="locale === option.value" class="ml-auto size-4" />
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <main class="grow p-4 md:p-6">
        <RouterView :workspace-id="workspaceId" />
      </main>
    </SidebarInset>
  </SidebarProvider>
</template>
