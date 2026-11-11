<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

import { errorMessage } from "@/lib/errors";
import { useSession } from "@/stores/session";

const session = useSession();
const router = useRouter();
const { t } = useI18n();

const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function submit(): Promise<void> {
  error.value = "";
  submitting.value = true;
  try {
    const me = await session.login(username.value.trim(), password.value);
    await router.push(me.must_change_password ? "/password" : "/");
  } catch (caught) {
    error.value = errorMessage(caught);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login">
    <form class="card" @submit.prevent="submit">
      <h1>{{ t("app.name") }}</h1>
      <p class="muted">{{ t("app.tagline") }}</p>
      <label class="field">
        <span>{{ t("auth.username") }}</span>
        <input v-model="username" autocomplete="username" required />
      </label>
      <label class="field">
        <span>{{ t("auth.password") }}</span>
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit" :disabled="submitting">{{ t("auth.submit") }}</button>
    </form>
  </div>
</template>

<style scoped>
.login { min-height: 100vh; display: grid; place-items: center; }
form { width: 360px; }
h1 { margin-bottom: 4px; }
</style>
