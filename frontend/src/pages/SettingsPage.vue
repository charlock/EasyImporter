<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Check, CircleCheck, CircleX, Monitor, Moon, Sun } from "@lucide/vue";

import { api } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { setLocale, type Locale } from "@/locales";
import { useTheme, type Theme } from "@/stores/theme";

const { t, locale } = useI18n();
const themeStore = useTheme();
const healthOk = ref<boolean | null>(null);

const themeOptions: { value: Theme; labelKey: string; icon: typeof Sun }[] = [
  { value: "light", labelKey: "theme.light", icon: Sun },
  { value: "dark", labelKey: "theme.dark", icon: Moon },
  { value: "system", labelKey: "theme.system", icon: Monitor },
];

const localeOptions: { value: Locale; label: string }[] = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

onMounted(async () => {
  healthOk.value = (await api.get<{ status: string }>("/health").catch(() => null))?.status === "ok";
});
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('settings.title')" :description="t('settings.description')" />

    <Card class="max-w-2xl">
      <CardHeader>
        <CardTitle>{{ t("settings.appearance") }}</CardTitle>
        <CardDescription>{{ t("settings.appearanceDesc") }}</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-2">
        <Button
          v-for="option in themeOptions"
          :key="option.value"
          :variant="themeStore.theme === option.value ? 'default' : 'outline'"
          @click="themeStore.set(option.value)"
        >
          <component :is="option.icon" class="size-4" />
          {{ t(option.labelKey) }}
          <Check v-if="themeStore.theme === option.value" class="size-4" />
        </Button>
      </CardContent>
    </Card>

    <Card class="max-w-2xl">
      <CardHeader>
        <CardTitle>{{ t("settings.language") }}</CardTitle>
        <CardDescription>{{ t("settings.languageDesc") }}</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-2">
        <Button
          v-for="option in localeOptions"
          :key="option.value"
          :variant="locale === option.value ? 'default' : 'outline'"
          @click="setLocale(option.value)"
        >
          {{ option.label }}
          <Check v-if="locale === option.value" class="size-4" />
        </Button>
      </CardContent>
    </Card>

    <Card class="max-w-2xl">
      <CardHeader>
        <CardTitle>{{ t("settings.about") }}</CardTitle>
      </CardHeader>
      <CardContent class="space-y-2 text-sm">
        <p class="flex justify-between gap-4">
          <span class="text-muted-foreground">{{ t("settings.version") }}</span>
          <span class="font-medium">v0.1.0</span>
        </p>
        <p class="flex justify-between gap-4">
          <span class="text-muted-foreground">{{ t("settings.repo") }}</span>
          <a
            class="font-medium text-primary hover:underline"
            href="https://github.com/charlock/EasyImporter"
            target="_blank"
            rel="noreferrer"
          >charlock/EasyImporter</a>
        </p>
        <p class="flex justify-between gap-4">
          <span class="text-muted-foreground">{{ t("settings.health") }}</span>
          <span class="flex items-center gap-1.5 font-medium">
            <template v-if="healthOk == null">…</template>
            <template v-else-if="healthOk">
              <CircleCheck class="size-4 text-emerald-600" />{{ t("settings.healthOk") }}
            </template>
            <template v-else>
              <CircleX class="size-4 text-destructive" />{{ t("settings.healthFail") }}
            </template>
          </span>
        </p>
      </CardContent>
    </Card>
  </div>
</template>
