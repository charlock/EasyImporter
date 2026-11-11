import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { api, setCsrfToken } from "@/api/client";
import type { Me, Workspace } from "@/lib/types";

export const useSession = defineStore("session", () => {
  const me = ref<Me | null>(null);
  const workspaces = ref<Workspace[]>([]);
  const ready = ref(false);

  const isAdmin = computed(() => me.value?.role === "admin");

  async function load(): Promise<void> {
    try {
      me.value = await api.get<Me>("/auth/me");
      setCsrfToken(me.value.csrf_token);
      workspaces.value = await api.get<Workspace[]>("/workspaces");
    } catch {
      me.value = null;
      workspaces.value = [];
    } finally {
      ready.value = true;
    }
  }

  async function login(username: string, password: string): Promise<Me> {
    me.value = await api.post<Me>("/auth/login", { username, password });
    setCsrfToken(me.value.csrf_token);
    workspaces.value = await api.get<Workspace[]>("/workspaces");
    return me.value;
  }

  /** 只清本地状态。改密后后端已删掉全部会话，不能再调 logout。 */
  function reset(): void {
    me.value = null;
    workspaces.value = [];
    setCsrfToken("");
  }

  async function logout(): Promise<void> {
    try {
      await api.post("/auth/logout");
    } finally {
      reset();
    }
  }

  return { me, workspaces, ready, isAdmin, load, login, logout, reset };
});
