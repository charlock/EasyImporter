import {
  Database,
  FileSpreadsheet,
  FileUp,
  FolderCog,
  History,
  LayoutDashboard,
  LayoutTemplate,
  Settings,
  Users,
  type LucideIcon,
} from "@lucide/vue";

export interface NavItem {
  to: string;
  titleKey: string;
  icon: LucideIcon;
  /** 仅管理员可见 */
  admin?: boolean;
}

export interface NavGroup {
  labelKey: string;
  items: NavItem[];
}

export const brandIcon = FileSpreadsheet;

export const navGroups: NavGroup[] = [
  {
    labelKey: "nav.groupMain",
    items: [
      { to: "/dashboard", titleKey: "nav.dashboard", icon: LayoutDashboard },
      { to: "/import", titleKey: "nav.import", icon: FileUp },
      { to: "/imports", titleKey: "nav.imports", icon: History },
      { to: "/templates", titleKey: "nav.templates", icon: LayoutTemplate },
    ],
  },
  {
    labelKey: "nav.groupAdmin",
    items: [
      { to: "/datasources", titleKey: "nav.datasources", icon: Database, admin: true },
      { to: "/users", titleKey: "nav.users", icon: Users, admin: true },
      { to: "/workspaces", titleKey: "nav.workspaces", icon: FolderCog, admin: true },
    ],
  },
  {
    labelKey: "nav.groupSystem",
    items: [
      { to: "/settings", titleKey: "nav.settings", icon: Settings },
    ],
  },
];
