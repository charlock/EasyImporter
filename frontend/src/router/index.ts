import { createRouter, createWebHistory } from "vue-router";

import { useSession } from "@/stores/session";

declare module "vue-router" {
  interface RouteMeta {
    /** 面包屑与侧边栏高亮用的 i18n key，如 nav.import */
    titleKey?: string;
    admin?: boolean;
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: () => import("@/pages/LoginPage.vue") },
    {
      path: "/",
      component: () => import("@/layouts/AppShell.vue"),
      children: [
        { path: "", redirect: "/dashboard" },
        { path: "dashboard", component: () => import("@/pages/DashboardPage.vue"), meta: { titleKey: "nav.dashboard" } },
        { path: "import", component: () => import("@/pages/ImportPage.vue"), meta: { titleKey: "nav.import" } },
        { path: "imports", component: () => import("@/pages/ImportListPage.vue"), meta: { titleKey: "nav.imports" } },
        { path: "imports/:id", component: () => import("@/pages/ImportDetailPage.vue"), meta: { titleKey: "nav.imports" } },
        { path: "templates", component: () => import("@/pages/TemplateListPage.vue"), meta: { titleKey: "nav.templates" } },
        { path: "templates/new", component: () => import("@/pages/TemplateEditorPage.vue"), meta: { admin: true, titleKey: "nav.templates" } },
        { path: "templates/:id", component: () => import("@/pages/TemplateEditorPage.vue"), meta: { admin: true, titleKey: "nav.templates" } },
        { path: "datasources", component: () => import("@/pages/DatasourcePage.vue"), meta: { admin: true, titleKey: "nav.datasources" } },
        { path: "users", component: () => import("@/pages/UsersPage.vue"), meta: { admin: true, titleKey: "nav.users" } },
        { path: "workspaces", component: () => import("@/pages/WorkspacesPage.vue"), meta: { admin: true, titleKey: "nav.workspaces" } },
        { path: "settings", component: () => import("@/pages/SettingsPage.vue"), meta: { titleKey: "nav.settings" } },
        { path: "password", component: () => import("@/pages/PasswordPage.vue"), meta: { titleKey: "nav.password" } },
        { path: "admin", redirect: "/users" },
        { path: ":pathMatch(.*)*", component: () => import("@/pages/NotFoundPage.vue") },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSession();
  if (!session.ready) await session.load();
  if (to.path === "/login") return session.me ? "/" : true;
  // 未登录时记住去向，登录成功后回原页面。
  if (!session.me) return { path: "/login", query: { redirect: to.fullPath } };
  // 后端不拦截首次登录未改密的用户，由前端强制先改密。
  if (session.me.must_change_password && to.path !== "/password") return "/password";
  if (to.meta.admin && !session.isAdmin) return "/";
  return true;
});

export default router;
