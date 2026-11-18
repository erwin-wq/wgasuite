import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  FolderTree,
  MailCheck,
  Search,
  Settings2,
  UsersRound,
  WifiOff
} from "lucide-react";
import { Link } from "react-router-dom";

import { appRoutes } from "../../app/routes";
import { Card } from "../../components/ui/Card";
import { Badge, Skeleton } from "../../components/ui/Feedback";
import type { ConnectorConfig } from "../../types";

interface DashboardOverviewProps {
  customerName: string | null;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  isLoading: boolean;
  hasLoadError: boolean;
  canOperateWorkspace: boolean;
  canViewConnections: boolean;
}

type OverviewState =
  | "loading"
  | "load-error"
  | "no-customer"
  | "no-organization"
  | "not-configured"
  | "configured"
  | "connected"
  | "connection-failed";

interface StatusPresentation {
  label: string;
  description: string;
  variant: "neutral" | "info" | "success" | "warning" | "danger";
  icon: typeof CheckCircle2;
}

const statePresentation: Record<Exclude<OverviewState, "loading">, StatusPresentation> = {
  "load-error": {
    label: "Status unavailable",
    description: "Connection status could not be loaded. Refresh the page or review connection settings.",
    variant: "danger",
    icon: CircleAlert
  },
  "no-customer": {
    label: "No customer selected",
    description: "Choose a customer from the Workspace selector to continue.",
    variant: "neutral",
    icon: CircleHelp
  },
  "no-organization": {
    label: "No workspace selected",
    description: "Choose an organization from the Workspace selector to continue.",
    variant: "neutral",
    icon: CircleHelp
  },
  "not-configured": {
    label: "Not configured",
    description: "Google Workspace Directory access has not been configured.",
    variant: "warning",
    icon: WifiOff
  },
  configured: {
    label: "Disconnected",
    description: "Connector settings are saved, but Directory access is not verified.",
    variant: "warning",
    icon: CircleHelp
  },
  connected: {
    label: "Connected",
    description: "Google Workspace Directory access is available.",
    variant: "success",
    icon: CheckCircle2
  },
  "connection-failed": {
    label: "Connection failed",
    description: "The latest connector test did not verify Directory access.",
    variant: "danger",
    icon: CircleAlert
  }
};

const quickActions = [
  {
    title: "Find a user",
    description: "Search for an exact user or alias in the connected Directory.",
    route: appRoutes.userLookup,
    icon: Search
  },
  {
    title: "Manage groups",
    description: "Review groups and manage direct membership.",
    route: appRoutes.groups,
    icon: UsersRound
  },
  {
    title: "View organizational units",
    description: "Browse the tenant hierarchy and its supported administration tools.",
    route: appRoutes.orgUnits,
    icon: FolderTree
  },
  {
    title: "Gmail delegations",
    description: "Look up a mailbox owner and manage delegates safely.",
    route: appRoutes.delegations,
    icon: MailCheck
  }
] as const;

function overviewState(
  isLoading: boolean,
  hasLoadError: boolean,
  customerName: string | null,
  organizationName: string | null,
  connectorConfig: ConnectorConfig | null
): OverviewState {
  if (isLoading) return "loading";
  if (hasLoadError) return "load-error";
  if (!customerName) return "no-customer";
  if (!organizationName) return "no-organization";
  if (!connectorConfig || connectorConfig.status === "not_configured") return "not-configured";
  if (connectorConfig.status === "connected") return "connected";
  if (connectorConfig.status === "connection_failed") return "connection-failed";
  return "configured";
}

function formatTestedAt(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

export function DashboardOverview({
  customerName,
  organizationName,
  connectorConfig,
  isLoading,
  hasLoadError,
  canOperateWorkspace,
  canViewConnections
}: DashboardOverviewProps) {
  const state = overviewState(
    isLoading,
    hasLoadError,
    customerName,
    organizationName,
    connectorConfig
  );
  const presentation = state === "loading" ? null : statePresentation[state];
  const StatusIcon = presentation?.icon;
  const lastTestedAt = formatTestedAt(connectorConfig?.last_tested_at ?? null);
  const workspaceReady = state === "connected" && canOperateWorkspace;

  return (
    <div className="dashboard-overview">
      <Card className={`overview-connection-band overview-connection-band--${state}`} aria-labelledby="overview-connection-heading">
        {state === "loading" ? (
          <div className="overview-connection-loading" role="status" aria-label="Loading connection status">
            <Skeleton lines={2} />
          </div>
        ) : (
          <>
            <div className="overview-connection-title">
              <span className="overview-status-icon" aria-hidden="true">
                {StatusIcon ? <StatusIcon /> : null}
              </span>
              <div>
                <span id="overview-connection-heading">Connection</span>
                <strong>{presentation?.label}</strong>
              </div>
            </div>
            <div className="overview-connection-copy">
              <p>{presentation?.description}</p>
              {lastTestedAt ? (
                <span>
                  Last verified <time dateTime={connectorConfig?.last_tested_at ?? undefined}>{lastTestedAt}</time>
                </span>
              ) : connectorConfig ? (
                <span>Last verified time unavailable</span>
              ) : null}
            </div>
            {canViewConnections && organizationName ? (
              <Link className="overview-connection-link" to={appRoutes.connections.path}>
                <Settings2 aria-hidden="true" />
                Connection settings
              </Link>
            ) : null}
          </>
        )}
      </Card>

      <div className="overview-task-layout">
        <Card className="overview-quick-actions" aria-labelledby="overview-actions-heading">
          <div className="overview-section-heading">
            <div>
              <h2 id="overview-actions-heading">Common tasks</h2>
              <p>Go directly to an existing Workspace administration tool.</p>
            </div>
          </div>
          {state !== "loading" && canOperateWorkspace && organizationName ? (
            <nav className="overview-action-list" aria-label="Common Workspace tasks">
              {quickActions.map(({ title, description, route, icon: Icon }) => (
                <Link to={route.path} key={route.id}>
                  <span className="overview-action-icon" aria-hidden="true"><Icon /></span>
                  <span>
                    <strong>{title}</strong>
                    <small>{description}</small>
                  </span>
                  <ArrowRight aria-hidden="true" />
                </Link>
              ))}
            </nav>
          ) : state !== "loading" ? (
            <div className="overview-actions-unavailable" role="status">
              <CircleHelp aria-hidden="true" />
              <p>
                {!organizationName
                  ? "Select a workspace to see available administration tools."
                  : "Your current role does not provide Workspace administration actions."}
              </p>
            </div>
          ) : <Skeleton lines={4} />}
        </Card>

        <Card className={`overview-guidance overview-guidance--${state}`} as="aside" aria-labelledby="overview-guidance-heading">
          {state === "loading" ? (
            <Skeleton lines={3} />
          ) : (
            <>
              <Badge variant={presentation?.variant ?? "neutral"} icon={StatusIcon ? <StatusIcon aria-hidden="true" /> : undefined}>
                {presentation?.label}
              </Badge>
              <div>
                <h2 id="overview-guidance-heading">
                  {workspaceReady
                    ? "Workspace ready"
                    : state === "connected"
                      ? "Connection available"
                      : state === "no-customer" || state === "no-organization"
                        ? "Choose a workspace"
                        : "Connection needs attention"}
                </h2>
                <p>
                  {workspaceReady
                    ? "Directory administration is available for users, groups, organizational units, and Gmail delegations."
                    : state === "connected"
                      ? "Directory access is connected. Available actions depend on your current role."
                      : presentation?.description}
                </p>
              </div>
              {workspaceReady ? (
                <Link className="overview-primary-action" to={appRoutes.userLookup.path}>
                  <Search aria-hidden="true" />
                  Find a user
                </Link>
              ) : canViewConnections && organizationName ? (
                <Link className="overview-primary-action" to={appRoutes.connections.path}>
                  <Settings2 aria-hidden="true" />
                  Review connection
                </Link>
              ) : null}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
