<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { api } from "@/api/client";
import { errorMessage } from "@/lib/errors";
import type { Role, User, Workspace } from "@/lib/types";
import { useSession } from "@/stores/session";

const { t } = useI18n();
const session = useSession();

const users = ref<User[]>([]);
const error = ref("");
const form = ref({ username: "", password: "", role: "importer" as Role });
const memberWorkspaceId = ref<number | null>(session.workspaces[0]?.id ?? null);
const memberIds = ref<Set<number>>(new Set());

const importers = computed(() => users.value.filter((user) => user.role !== "admin"));

async function run(action: () => Promise<void>): Promise<void> {
  error.value = "";
  try {
    await action();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

const load = () => run(async () => {
  users.value = await api.get<User[]>("/users");
});

const createUser = () => run(async () => {
  await api.post("/users", form.value);
  form.value = { username: "", password: "", role: "importer" };
  await load();
});

const updateUser = (user: User, patch: { role?: Role; is_active?: boolean; password?: string }) => run(async () => {
  const updated = await api.put<User>(`/users/${user.id}`, patch);
  users.value = users.value.map((item) => (item.id === user.id ? updated : item));
});

function resetPassword(user: User): void {
  const password = window.prompt(t("admin.resetPrompt", { name: user.username }));
  if (!password) return;
  if (password.length < 8) {
    error.value = t("auth.passwordTooShort");
    return;
  }
  void updateUser(user, { password });
}

const createWorkspace = () => run(async () => {
  const name = window.prompt(t("common.name"))?.trim();
  if (!name) return;
  const workspace = await api.post<Workspace>("/workspaces", { name, description: "" });
  session.workspaces = [...session.workspaces, workspace];
  memberWorkspaceId.value ??= workspace.id;
});

watch(
  memberWorkspaceId,
  (id) => run(async () => {
    memberIds.value = new Set();
    if (id == null) return;
    const members = await api.get<User[]>(`/workspaces/${id}/members`);
    memberIds.value = new Set(members.map((user) => user.id));
  }),
  { immediate: true },
);

function toggleMember(id: number, checked: boolean): void {
  const next = new Set(memberIds.value);
  if (checked) next.add(id);
  else next.delete(id);
  memberIds.value = next;
}

const saveMembers = () => run(async () => {
  if (memberWorkspaceId.value == null) return;
  const members = await api.put<User[]>(`/workspaces/${memberWorkspaceId.value}/members`, {
    user_ids: [...memberIds.value],
  });
  memberIds.value = new Set(members.map((user) => user.id));
  session.workspaces = session.workspaces.map((item) =>
    item.id === memberWorkspaceId.value ? { ...item, member_count: members.length } : item,
  );
  window.alert(t("common.saved"));
});

void load();
</script>

<template>
  <div class="stack">
    <div class="page-head">
      <h1>{{ t("admin.title") }}</h1>
      <button class="ghost" @click="createWorkspace">{{ t("admin.createWorkspace") }}</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <h2>{{ t("admin.users") }}</h2>
    <form class="card row" @submit.prevent="createUser">
      <input v-model="form.username" :placeholder="t('auth.username')" required />
      <input v-model="form.password" type="password" minlength="8" :placeholder="t('auth.password')" required />
      <select v-model="form.role">
        <option value="importer">{{ t("role.importer") }}</option>
        <option value="admin">{{ t("role.admin") }}</option>
      </select>
      <button type="submit">{{ t("common.create") }}</button>
    </form>

    <table class="data">
      <thead>
        <tr>
          <th>{{ t("auth.username") }}</th>
          <th>{{ t("admin.role") }}</th>
          <th>{{ t("admin.active") }}</th>
          <th>{{ t("common.actions") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in users" :key="user.id">
          <td>{{ user.username }}</td>
          <td>
            <select
              :value="user.role"
              :disabled="user.id === session.me?.id"
              @change="updateUser(user, { role: ($event.target as HTMLSelectElement).value as Role })"
            >
              <option value="importer">{{ t("role.importer") }}</option>
              <option value="admin">{{ t("role.admin") }}</option>
            </select>
          </td>
          <td>{{ user.is_active ? "✓" : "–" }}</td>
          <td class="row">
            <button
              class="ghost"
              :disabled="user.id === session.me?.id"
              @click="updateUser(user, { is_active: !user.is_active })"
            >{{ user.is_active ? t("admin.disable") : t("admin.enable") }}</button>
            <button class="ghost" @click="resetPassword(user)">{{ t("admin.resetPassword") }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <h2>{{ t("admin.members") }}</h2>
    <div class="card stack">
      <label class="field">
        <span>{{ t("admin.workspaces") }}</span>
        <select v-model="memberWorkspaceId">
          <option v-for="item in session.workspaces" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
      <div v-if="memberWorkspaceId != null" class="checks">
        <label v-for="user in importers" :key="user.id" class="field inline">
          <input
            type="checkbox"
            :checked="memberIds.has(user.id)"
            @change="toggleMember(user.id, ($event.target as HTMLInputElement).checked)"
          />
          <span>{{ user.username }}</span>
        </label>
      </div>
      <div><button :disabled="memberWorkspaceId == null" @click="saveMembers">{{ t("admin.saveMembers") }}</button></div>
    </div>
  </div>
</template>

<style scoped>
h2 { font-size: 16px; margin: 8px 0 0; }
.checks { display: flex; flex-wrap: wrap; gap: 8px 16px; }
</style>
