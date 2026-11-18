import type { LucideIcon } from "lucide-react";
import {
  Building2,
  Cable,
  Database,
  FolderTree,
  LayoutDashboard,
  MailCheck,
  SearchCheck,
  UserRoundSearch,
  UsersRound
} from "lucide-react";

export type AppRouteId =
  | "overview"
  | "users"
  | "userLookup"
  | "groups"
  | "orgUnits"
  | "delegations"
  | "connections"
  | "customers"
  | "organizations"
  | "platform";

export type NavigationGroup = "workspace" | "directory" | "gmail" | "settings" | "administration";
export type RouteAccess = "authenticated" | "tenant" | "tenant-operator" | "administration" | "platform";

export interface AppRouteDefinition {
  id: AppRouteId;
  path: string;
  title: string;
  shortTitle: string;
  description: string;
  breadcrumb: readonly string[];
  group: NavigationGroup;
  icon: LucideIcon;
  access: RouteAccess;
}

export const appRoutes = {
  overview: {
    id: "overview",
    path: "/overview",
    title: "Workspace overview",
    shortTitle: "Overview",
    description: "Manage your connected Google Workspace from one place.",
    breadcrumb: ["Workspace", "Overview"],
    group: "workspace",
    icon: LayoutDashboard,
    access: "authenticated"
  },
  users: {
    id: "users",
    path: "/directory/users",
    title: "User directory",
    shortTitle: "Users",
    description: "Browse the live Google Workspace user directory.",
    breadcrumb: ["Directory", "Users"],
    group: "directory",
    icon: UserRoundSearch,
    access: "tenant-operator"
  },
  userLookup: {
    id: "userLookup",
    path: "/directory/users/lookup",
    title: "Exact user lookup",
    shortTitle: "User lookup",
    description: "Find one user or alias without putting account data in the URL.",
    breadcrumb: ["Directory", "Users", "Lookup"],
    group: "directory",
    icon: SearchCheck,
    access: "tenant-operator"
  },
  groups: {
    id: "groups",
    path: "/directory/groups",
    title: "Groups",
    shortTitle: "Groups",
    description: "Inspect groups and manage memberships with existing safety controls.",
    breadcrumb: ["Directory", "Groups"],
    group: "directory",
    icon: UsersRound,
    access: "tenant-operator"
  },
  orgUnits: {
    id: "orgUnits",
    path: "/directory/org-units",
    title: "Organizational units",
    shortTitle: "Organizational units",
    description: "Review and administer the tenant organizational-unit hierarchy.",
    breadcrumb: ["Directory", "Organizational units"],
    group: "directory",
    icon: FolderTree,
    access: "tenant-operator"
  },
  delegations: {
    id: "delegations",
    path: "/gmail/delegations",
    title: "Gmail delegations",
    shortTitle: "Delegations",
    description: "Look up a mailbox and manage delegates through the guarded workflow.",
    breadcrumb: ["Gmail", "Delegations"],
    group: "gmail",
    icon: MailCheck,
    access: "tenant-operator"
  },
  connections: {
    id: "connections",
    path: "/settings/connections",
    title: "Connections",
    shortTitle: "Connections",
    description: "Review connector health and manage authorized Google Workspace credentials.",
    breadcrumb: ["Settings", "Connections"],
    group: "settings",
    icon: Cable,
    access: "tenant"
  },
  customers: {
    id: "customers",
    path: "/administration/customers",
    title: "Customers",
    shortTitle: "Customers",
    description: "Manage the customer contexts available to this platform.",
    breadcrumb: ["Administration", "Customers"],
    group: "administration",
    icon: Building2,
    access: "administration"
  },
  organizations: {
    id: "organizations",
    path: "/administration/organizations",
    title: "Organizations",
    shortTitle: "Organizations",
    description: "Manage organizations within the active customer context.",
    breadcrumb: ["Administration", "Organizations"],
    group: "administration",
    icon: Building2,
    access: "administration"
  },
  platform: {
    id: "platform",
    path: "/platform",
    title: "Platform administration",
    shortTitle: "Platform",
    description: "Read-only support and troubleshooting for authorized platform roles.",
    breadcrumb: ["Platform"],
    group: "administration",
    icon: Database,
    access: "platform"
  }
} satisfies Record<AppRouteId, AppRouteDefinition>;

export const routeList = Object.values(appRoutes);

export function findRoute(pathname: string): AppRouteDefinition | null {
  return routeList.find((route) => route.path === pathname) ?? null;
}

export const navigationGroupLabels: Record<NavigationGroup, string> = {
  workspace: "Workspace",
  directory: "Directory",
  gmail: "Gmail",
  settings: "Settings",
  administration: "Administration"
};
