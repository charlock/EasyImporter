<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { ChevronsUpDown, KeyRound, LogOut, Settings } from "@lucide/vue";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { useSession } from "@/stores/session";

import { brandIcon, navGroups } from "./sidebar-data";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const { isMobile } = useSidebar();

const groups = computed(() =>
  navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !item.admin || session.isAdmin),
    }))
    .filter((group) => group.items.length > 0),
);

function isActive(to: string): boolean {
  if (to === "/dashboard") return route.path === "/dashboard" || route.path === "/";
  return route.path === to || route.path.startsWith(`${to}/`);
}

async function logout(): Promise<void> {
  await session.logout();
  await router.push("/login");
}
</script>

<template>
  <Sidebar collapsible="icon" class="z-50">
    <SidebarHeader class="h-14 border-b py-1 group-data-[collapsible=icon]:justify-center">
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" as-child>
            <RouterLink to="/">
              <div
                class="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground"
              >
                <component :is="brandIcon" class="size-4" />
              </div>
              <div class="grid flex-1 text-left text-sm leading-tight">
                <span class="truncate font-semibold">EasyImporter</span>
                <span class="truncate text-xs">{{ t("app.subtitle") }}</span>
              </div>
            </RouterLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <SidebarGroup v-for="group in groups" :key="group.labelKey">
        <SidebarGroupLabel>{{ t(group.labelKey) }}</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem v-for="item in group.items" :key="item.to">
              <SidebarMenuButton as-child :is-active="isActive(item.to)" :tooltip="t(item.titleKey)">
                <RouterLink :to="item.to">
                  <component :is="item.icon" />
                  <span>{{ t(item.titleKey) }}</span>
                </RouterLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter class="border-t py-1 group-data-[collapsible=icon]:justify-center">
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton
                size="lg"
                class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
              >
                <Avatar class="size-8 rounded-lg">
                  <AvatarFallback class="rounded-lg">
                    {{ (session.me?.username ?? "?").slice(0, 2).toUpperCase() }}
                  </AvatarFallback>
                </Avatar>
                <div class="grid flex-1 text-left text-sm leading-tight">
                  <span class="truncate font-semibold">{{ session.me?.username }}</span>
                  <span class="truncate text-xs">{{
                    session.me ? t(`role.${session.me.role}`) : ""
                  }}</span>
                </div>
                <ChevronsUpDown class="ml-auto size-4" />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="min-w-56 rounded-lg"
              :side="isMobile ? 'bottom' : 'right'"
              align="start"
              :side-offset="4"
            >
              <DropdownMenuItem @click="router.push('/password')">
                <KeyRound />
                {{ t("nav.password") }}
              </DropdownMenuItem>
              <DropdownMenuItem @click="router.push('/settings')">
                <Settings />
                {{ t("nav.settings") }}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem @click="logout">
                <LogOut />
                {{ t("nav.logout") }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>

    <SidebarRail />
  </Sidebar>
</template>
