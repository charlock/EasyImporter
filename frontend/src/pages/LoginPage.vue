<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { resolveLoginRedirect } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { useSession } from "@/stores/session";

const session = useSession();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

/** 从其它页面因会话过期跳过来时，提示重新登录。 */
const sessionExpired = computed(() => route.query.expired === "1");

async function submit(): Promise<void> {
  error.value = "";
  submitting.value = true;
  try {
    const me = await session.login(username.value.trim(), password.value);
    await router.push(
      me.must_change_password ? "/password" : resolveLoginRedirect(route.query.redirect),
    );
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4">
    <Card class="w-full max-w-sm">
      <CardHeader>
        <CardTitle class="text-2xl">{{ t("app.name") }}</CardTitle>
        <CardDescription>{{ t("app.tagline") }}</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-4" @submit.prevent="submit">
          <div class="space-y-2">
            <Label for="username">{{ t("auth.username") }}</Label>
            <Input id="username" v-model="username" autocomplete="username" required />
          </div>
          <div class="space-y-2">
            <Label for="password">{{ t("auth.password") }}</Label>
            <Input
              id="password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
            />
          </div>
          <Alert v-if="sessionExpired">
            <AlertDescription>{{ t("auth.sessionExpired") }}</AlertDescription>
          </Alert>
          <Alert v-if="error" variant="destructive">
            <AlertDescription>{{ error }}</AlertDescription>
          </Alert>
          <Button type="submit" class="w-full" :disabled="submitting">
            {{ t("auth.submit") }}
          </Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
