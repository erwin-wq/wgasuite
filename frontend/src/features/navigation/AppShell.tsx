import {
  BadgeCheck,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Menu,
  PanelLeftClose,
  ShieldCheck,
  X
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";

import {
  navigationGroupLabels,
  type AppRouteDefinition,
  type NavigationGroup
} from "../../app/routes";
import { Button, IconButton } from "../../components/ui/Button";
import { Badge, EmptyState } from "../../components/ui/Feedback";
import { Select } from "../../components/ui/FormControls";
import { PageHeader } from "../../components/ui/PageHeader";
import type { DensityId, ThemeId } from "../../theme/theme";
import type { Customer, Organization, User } from "../../types";
import { AccountThemeMenu } from "./AccountThemeMenu";

interface WorkspaceSwitcherProps {
  customers: Customer[];
  organizations: Organization[];
  selectedCustomerId: string;
  selectedOrganizationId: string;
  isLoading: boolean;
  onCustomerChange: (customerId: string) => void;
  onOrganizationChange: (organizationId: string) => void;
}

function WorkspaceSwitcher({
  customers,
  organizations,
  selectedCustomerId,
  selectedOrganizationId,
  isLoading,
  onCustomerChange,
  onOrganizationChange
}: WorkspaceSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedCustomer = customers.find((customer) => customer.id === selectedCustomerId);
  const selectedOrganization = organizations.find(
    (organization) => organization.id === selectedOrganizationId
  );

  useEffect(() => {
    if (!isOpen) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (!panelRef.current?.contains(event.target as Node)) setIsOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setIsOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen]);

  return (
    <div className="workspace-switcher" ref={panelRef} data-state={isOpen ? "open" : "closed"}>
      <Button
        ref={triggerRef}
        variant="ghost"
        className="workspace-switcher-trigger"
        onClick={() => setIsOpen((current) => !current)}
        aria-expanded={isOpen}
        aria-controls="workspace-switcher-panel"
      >
        <span>
          <small>Active workspace</small>
          <strong>
            {isLoading
              ? "Loading workspace"
              : selectedOrganization?.name ?? "Select organization"}
          </strong>
          <em>{selectedCustomer?.name ?? "No customer selected"}</em>
        </span>
        <ChevronDown className="workspace-switcher-chevron" aria-hidden="true" />
      </Button>
      {isOpen && (
        <div id="workspace-switcher-panel" className="workspace-switcher-panel" data-state="open">
          <Select
            label="Customer"
            value={selectedCustomerId}
            onChange={(event) => onCustomerChange(event.target.value)}
            disabled={isLoading}
            options={[
              { value: "", label: "Select customer" },
              ...customers.map((customer) => ({ value: customer.id, label: customer.name }))
            ]}
          />
          <Select
            label="Organization"
            value={selectedOrganizationId}
            onChange={(event) => {
              onOrganizationChange(event.target.value);
              setIsOpen(false);
              triggerRef.current?.focus();
            }}
            disabled={isLoading || organizations.length === 0}
            options={[
              { value: "", label: "Select organization" },
              ...organizations.map((organization) => ({ value: organization.id, label: organization.name }))
            ]}
          />
        </div>
      )}
    </div>
  );
}

interface AppShellProps extends WorkspaceSwitcherProps {
  currentUser: User;
  currentRoute: AppRouteDefinition;
  navigationRoutes: AppRouteDefinition[];
  isConnected: boolean;
  theme: ThemeId;
  density: DensityId;
  onThemeChange: (theme: ThemeId) => void;
  onDensityChange: (density: DensityId) => void;
  onLogout: () => void;
  children: ReactNode;
}

export function AppShell({
  currentUser,
  currentRoute,
  navigationRoutes,
  isConnected,
  theme,
  density,
  onThemeChange,
  onDensityChange,
  onLogout,
  children,
  ...workspaceSwitcherProps
}: AppShellProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const mobileDrawerRef = useRef<HTMLElement>(null);

  const closeMobileNavigation = useCallback((restoreFocus = true) => {
    setIsMobileOpen(false);
    if (restoreFocus) mobileToggleRef.current?.focus();
  }, []);

  useEffect(() => {
    setIsMobileOpen(false);
  }, [currentRoute.id]);

  useEffect(() => {
    if (!isMobileOpen) return;
    mobileCloseRef.current?.focus();
    function handleDrawerKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeMobileNavigation();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        mobileDrawerRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        ) ?? []
      ).filter((element) => !element.hidden);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleDrawerKeyDown);
    return () => document.removeEventListener("keydown", handleDrawerKeyDown);
  }, [closeMobileNavigation, isMobileOpen]);

  const groupedRoutes = navigationRoutes.reduce(
    (groups, route) => {
      (groups[route.group] ??= []).push(route);
      return groups;
    },
    {} as Partial<Record<NavigationGroup, AppRouteDefinition[]>>
  );

  return (
    <main className={`premium-app-shell ${isCollapsed ? "sidebar-collapsed" : ""}`}>
      {isMobileOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => closeMobileNavigation()}
        />
      )}
      <aside
        ref={mobileDrawerRef}
        className={`premium-sidebar ${isMobileOpen ? "mobile-open" : ""}`}
        aria-label="Primary navigation"
      >
        <div className="premium-brand">
          <span className="brand-mark">
            <ShieldCheck aria-hidden="true" />
          </span>
          <span className="brand-copy">
            <strong>WGASuite</strong>
            <small>Workspace administration</small>
          </span>
          <IconButton
            ref={mobileCloseRef}
            className="mobile-sidebar-close"
            label="Close navigation"
            icon={<X aria-hidden="true" />}
            onClick={() => closeMobileNavigation()}
          />
        </div>

        <nav className="premium-navigation" aria-label="Workspace administration">
          {(Object.keys(groupedRoutes) as NavigationGroup[]).map((group) => (
            <div className="navigation-group" key={group}>
              <span className="navigation-group-label">{navigationGroupLabels[group]}</span>
              {groupedRoutes[group]?.map((route) => {
                const Icon = route.icon;
                return (
                  <NavLink
                    key={route.id}
                    to={route.path}
                    className={({ isActive }) => (isActive ? "active" : undefined)}
                    title={isCollapsed ? route.shortTitle : undefined}
                    onClick={() => {
                      if (isMobileOpen) closeMobileNavigation();
                    }}
                  >
                    <Icon aria-hidden="true" />
                    <span>{route.shortTitle}</span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <Button
            variant="ghost"
            size="sm"
            className="sidebar-collapse"
            onClick={() => setIsCollapsed((current) => !current)}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!isCollapsed}
          >
            {isCollapsed ? (
              <ChevronsRight aria-hidden="true" />
            ) : (
              <ChevronsLeft aria-hidden="true" />
            )}
            <span>{isCollapsed ? "Expand" : "Collapse sidebar"}</span>
          </Button>
          <div className="sidebar-security-note">
            <BadgeCheck aria-hidden="true" />
            <span>
              <strong>Protected operations</strong>
              <small>Confirmation and audit controls active</small>
            </span>
          </div>
        </div>
      </aside>

      <section className="premium-main">
        <header className="premium-header">
          <IconButton
            ref={mobileToggleRef}
            className="mobile-menu-trigger"
            label="Open navigation"
            icon={<Menu aria-hidden="true" />}
            onClick={() => setIsMobileOpen(true)}
            aria-expanded={isMobileOpen}
          />
          <WorkspaceSwitcher {...workspaceSwitcherProps} />
          <Badge variant={isConnected ? "success" : "neutral"} className={`connection-pill ${isConnected ? "connected" : ""}`}>
            <span aria-hidden="true" /> {isConnected ? "Connected" : "Setup required"}
          </Badge>
          <div className="header-spacer" />
          <AccountThemeMenu
            fullName={currentUser.full_name}
            role={currentUser.role}
            theme={theme}
            density={density}
            onThemeChange={onThemeChange}
            onDensityChange={onDensityChange}
            onLogout={onLogout}
          />
        </header>

        <div className="premium-content">
          <PageHeader
            className="route-heading"
            breadcrumbs={currentRoute.breadcrumb}
            title={currentRoute.title}
            description={currentRoute.description}
          />
          {children}
        </div>
      </section>
    </main>
  );
}

export function RouteUnavailable({ title, children }: { title: string; children: ReactNode }) {
  return (
    <EmptyState className="route-unavailable" title={title} icon={<PanelLeftClose aria-hidden="true" />}>
      {children}
    </EmptyState>
  );
}
