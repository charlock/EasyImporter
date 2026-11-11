<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import { api } from "@/api/client";
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
    window.alert(t("auth.passwordChanged"));
    await router.push("/login");
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="stack">
    <div class="page-head"><h1>{{ t("auth.changePassword") }}</h1></div>
    <form class="card stack narrow" @submit.prevent="submit">
      <p v-if="session.me?.must_change_password" class="muted">{{ t("auth.mustChange") }}</p>
      <label class="field">
        <span>{{ t("auth.oldPassword") }}</span>
        <input v-model="oldPassword" type="password" autocomplete="current-password" required />
      </label>
      <label class="field">
        <span>{{ t("auth.newPassword") }}</span>
        <input v-model="newPassword" type="password" autocomplete="new-password" minlength="8" required />
      </label>
      <label class="field">
        <span>{{ t("auth.confirmPassword") }}</span>
        <input v-model="confirmPassword" type="password" autocomplete="new-password" required />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="row"><button type="submit" :disabled="submitting">{{ t("common.save") }}</button></div>
    </form>
  </div>
</template>

<style scoped>
.narrow { max-width: 420px; }
</style>
