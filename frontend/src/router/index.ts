import { createRouter, createWebHistory } from "vue-router";

import { useSession } from "@/stores/session";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: () => import("@/pages/LoginPage.vue") },
    {
      path: "/",
      component: () => import("@/layouts/AppShell.vue"),
      children: [
        { path: "", redirect: "/import" },
        { path: "import", component: () => import("@/pages/ImportPage.vue") },
        { path: "imports", component: () => import("@/pages/ImportListPage.vue") },
        { path: "imports/:id", component: () => import("@/pages/ImportDetailPage.vue") },
        { path: "templates", component: () => import("@/pages/TemplateListPage.vue") },
        { path: "templates/new", component: () => import("@/pages/TemplateEditorPage.vue"), meta: { admin: true } },
        { path: "templates/:id", component: () => import("@/pages/TemplateEditorPage.vue"), meta: { admin: true } },
        { path: "datasources", component: () => import("@/pages/DatasourcePage.vue"), meta: { admin: true } },
        { path: "admin", component: () => import("@/pages/AdminPage.vue"), meta: { admin: true } },
        { path: "password", component: () => import("@/pages/PasswordPage.vue") },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSession();
  if (!session.ready) await session.load();
  if (to.path === "/login") return session.me ? "/" : true;
  if (!session.me) return "/login";
  // 后端不拦截首次登录未改密的用户，由前端强制先改密。
  if (session.me.must_change_password && to.path !== "/password") return "/password";
  if (to.meta.admin && !session.isAdmin) return "/";
  return true;
});

export default router;
