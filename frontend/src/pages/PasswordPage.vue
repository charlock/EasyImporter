<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { toast } from "vue-sonner";

import { api } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/errors";
import { useSession } from "@/stores/session";

const session = useSession();
const router = useRouter();
const { t } = useI18n();

const oldPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const error = ref("");
const submitting = ref(false);

async function submit(): Promise<void> {
  error.value = "";
  if (newPassword.value.length < 8) {
    error.value = t("auth.passwordTooShort");
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = t("auth.passwordMismatch");
    return;
  }
  submitting.value = true;
  try {
    await api.post("/auth/password", { old_password: oldPassword.value, new_password: newPassword.value });
    // 后端改密后删除该用户全部会话，本地状态随之作废。
    session.reset();
    toast.success(t("auth.passwordChanged"));
    await router.push("/login");
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('auth.changePassword')" />
    <Card class="max-w-md">
      <CardContent class="pt-6">
        <form class="space-y-4" @submit.prevent="submit">
          <p v-if="session.me?.must_change_password" class="text-sm text-muted-foreground">
            {{ t("auth.mustChange") }}
          </p>
          <div class="space-y-2">
            <Label for="old-password">{{ t("auth.oldPassword") }}</Label>
            <Input
              id="old-password"
              v-model="oldPassword"
              type="password"
              autocomplete="current-password"
              required
            />
          </div>
          <div class="space-y-2">
            <Label for="new-password">{{ t("auth.newPassword") }}</Label>
            <Input
              id="new-password"
              v-model="newPassword"
              type="password"
              autocomplete="new-password"
              minlength="8"
              required
            />
          </div>
          <div class="space-y-2">
            <Label for="confirm-password">{{ t("auth.confirmPassword") }}</Label>
            <Input
              id="confirm-password"
              v-model="confirmPassword"
              type="password"
              autocomplete="new-password"
              required
            />
          </div>
          <Alert v-if="error" variant="destructive">
            <AlertDescription>{{ error }}</AlertDescription>
          </Alert>
          <Button type="submit" :disabled="submitting">{{ t("common.save") }}</Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
