<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import { errorMessage } from "@/lib/errors";
import EmptyState from "@/components/EmptyState.vue";
import type { Datasource, DbType } from "@/lib/types";

defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();

const datasources = ref<Datasource[]>([]);
const creating = ref(false);
const message = ref("");
const error = ref("");

const form = ref({
  name: "",
  db_type: "postgres" as DbType,
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
});

// 数据源是全局资源，由管理员维护，不属于某个工作区。
async function load(): Promise<void> {
  datasources.value = await api.get<Datasource[]>("/datasources");
}

onMounted(load);

async function create(): Promise<void> {
  error.value = "";
  try {
    await api.post("/datasources", form.value);
    creating.value = false;
    await load();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function test(id: number): Promise<void> {
  message.value = "";
  error.value = "";
  try {
    await api.post(`/datasources/${id}/test`);
    message.value = t("datasource.testOk");
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function remove(id: number): Promise<void> {
  await api.delete(`/datasources/${id}`);
  await load();
}
</script>

<template>
  <div class="stack">
    <div class="page-head">
      <h1>{{ t("datasource.title") }}</h1>
      <button @click="creating = !creating">{{ t("datasource.create") }}</button>
    </div>
    <p v-if="message" class="muted">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>

    <form v-if="creating" class="card stack" @submit.prevent="create">
      <label class="field"><span>{{ t("common.name") }}</span><input v-model="form.name" required /></label>
      <label class="field">
        <span>{{ t("datasource.title") }}</span>
        <select v-model="form.db_type">
          <option value="postgres">PostgreSQL</option>
          <option value="mysql">MySQL</option>
          <option value="dameng">达梦</option>
        </select>
      </label>
      <div class="row">
        <label class="field"><span>{{ t("datasource.host") }}</span><input v-model="form.host" required /></label>
        <label class="field"><span>{{ t("datasource.port") }}</span><input v-model.number="form.port" type="number" /></label>
      </div>
      <label class="field"><span>{{ t("datasource.database") }}</span><input v-model="form.database" required /></label>
      <label class="field"><span>{{ t("datasource.username") }}</span><input v-model="form.username" required /></label>
      <label class="field"><span>{{ t("datasource.password") }}</span><input v-model="form.password" type="password" required /></label>
      <div class="row">
        <button type="submit">{{ t("common.save") }}</button>
        <button type="button" class="ghost" @click="creating = false">{{ t("common.cancel") }}</button>
      </div>
    </form>

    <EmptyState v-if="!datasources.length" :title="t('common.empty')" />
    <table v-else class="data">
      <tbody>
        <tr v-for="item in datasources" :key="item.id">
          <td>{{ item.name }}</td>
          <td class="muted">{{ item.db_type }} · {{ item.host }}:{{ item.port }}/{{ item.database }}</td>
          <td class="row">
            <button class="ghost" @click="test(item.id)">{{ t("datasource.test") }}</button>
            <button class="ghost" @click="remove(item.id)">{{ t("common.delete") }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
