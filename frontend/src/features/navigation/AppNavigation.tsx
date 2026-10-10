import {
  Activity,
  Building2,
  ClipboardList,
  Database,
  FileText,
  ShieldCheck,
  Users
} from "lucide-react";

export type ActiveSection =
  | "dashboard"
  | "customers"
  | "organizations"
  | "assessment"
  | "google-workspace"
  | "platform-admin"
  | "reports";

interface AppNavigationProps {
  activeSection: ActiveSection;
  canViewPlatformAdmin: boolean;
  showDemoFeatures: boolean;
  onNavigate: (section: ActiveSection) => void;
}

const standardItems = [
  { section: "dashboard", label: "Dashboard", icon: Activity },
  { section: "customers", label: "Customer Context", icon: Users },
  { section: "organizations", label: "Organizations", icon: Building2 },
  { section: "google-workspace", label: "Google Workspace", icon: ShieldCheck }
] satisfies Array<{
  section: ActiveSection;
  label: string;
  icon: typeof Activity;
}>;

const demoItems = [
  { section: "assessment", label: "Assessment Workspace", icon: ClipboardList },
  { section: "reports", label: "Reports", icon: FileText }
] satisfies Array<{
  section: ActiveSection;
  label: string;
  icon: typeof Activity;
}>;

export function AppNavigation({
  activeSection,
  canViewPlatformAdmin,
  showDemoFeatures,
  onNavigate
}: AppNavigationProps) {
  const items = showDemoFeatures ? [...standardItems, ...demoItems] : standardItems;

  return (
    <nav className="sidebar-nav" aria-label="Primary">
      {items.map(({ section, label, icon: Icon }) => (
        <button
          type="button"
          className={activeSection === section ? "active" : ""}
          onClick={() => onNavigate(section)}
          key={section}
        >
          <Icon aria-hidden="true" />
          {label}
        </button>
      ))}
      {canViewPlatformAdmin && (
        <button
          type="button"
          className={activeSection === "platform-admin" ? "active" : ""}
          onClick={() => onNavigate("platform-admin")}
        >
          <Database aria-hidden="true" />
          Platform Admin
        </button>
      )}
    </nav>
  );
}
