import {
  BadgeCheck,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
  Menu,
  PanelLeftClose,
  ShieldCheck,
  X
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";

import {
  navigationGroupLabels,
  type AppRouteDefinition,
  type NavigationGroup
} from "../../app/routes";
import type { Customer, Organization, User } from "../../types";

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
      if (event.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen]);

  return (
    <div className="workspace-switcher" ref={panelRef}>
      <button
        type="button"
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
        <ChevronDown aria-hidden="true" />
      </button>
      {isOpen && (
        <div id="workspace-switcher-panel" className="workspace-switcher-panel">
          <label>
            Customer
            <select
              value={selectedCustomerId}
              onChange={(event) => onCustomerChange(event.target.value)}
              disabled={isLoading}
            >
              <option value="">Select customer</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Organization
            <select
              value={selectedOrganizationId}
              onChange={(event) => {
                onOrganizationChange(event.target.value);
                setIsOpen(false);
              }}
              disabled={isLoading || organizations.length === 0}
            >
              <option value="">Select organization</option>
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
                </option>
              ))}
            </select>
          </label>
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
  onLogout: () => void;
  children: ReactNode;
}

export function AppShell({
  currentUser,
  currentRoute,
  navigationRoutes,
  isConnected,
  onLogout,
  children,
  ...workspaceSwitcherProps
}: AppShellProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setIsMobileOpen(false);
  }, [currentRoute.id]);

  useEffect(() => {
    if (!isMobileOpen) return;
    mobileCloseRef.current?.focus();
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setIsMobileOpen(false);
      mobileToggleRef.current?.focus();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [isMobileOpen]);

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
          onClick={() => setIsMobileOpen(false)}
        />
      )}
      <aside
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
          <button
            ref={mobileCloseRef}
            type="button"
            className="mobile-sidebar-close"
            aria-label="Close navigation"
            onClick={() => {
              setIsMobileOpen(false);
              mobileToggleRef.current?.focus();
            }}
          >
            <X aria-hidden="true" />
          </button>
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
          <button
            type="button"
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
          </button>
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
          <button
            ref={mobileToggleRef}
            type="button"
            className="mobile-menu-trigger"
            onClick={() => setIsMobileOpen(true)}
            aria-expanded={isMobileOpen}
            aria-label="Open navigation"
          >
            <Menu aria-hidden="true" />
          </button>
          <WorkspaceSwitcher {...workspaceSwitcherProps} />
          <div className={`connection-pill ${isConnected ? "connected" : ""}`}>
            <span aria-hidden="true" /> {isConnected ? "Connected" : "Setup required"}
          </div>
          <div className="header-spacer" />
          <div className="account-summary">
            <span>{currentUser.full_name}</span>
            <small>{currentUser.role.replace(/_/g, " ")}</small>
          </div>
          <button type="button" className="header-logout" onClick={onLogout}>
            <LogOut aria-hidden="true" /><span>Logout</span>
          </button>
        </header>

        <div className="premium-content">
          <header className="route-heading">
            <nav aria-label="Breadcrumb">
              {currentRoute.breadcrumb.map((item, index) => (
                <span key={item}>{index > 0 && <em>/</em>}{item}</span>
              ))}
            </nav>
            <h1>{currentRoute.title}</h1>
            <p>{currentRoute.description}</p>
          </header>
          {children}
        </div>
      </section>
    </main>
  );
}

export function RouteUnavailable({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="route-unavailable" role="status">
      <PanelLeftClose aria-hidden="true" />
      <h2>{title}</h2>
      <p>{children}</p>
    </section>
  );
}
