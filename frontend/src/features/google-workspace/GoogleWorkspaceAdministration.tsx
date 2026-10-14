import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock3,
  KeyRound,
  Settings2,
  UserRoundSearch,
  UsersRound
} from "lucide-react";
import { ReactNode, useEffect, useState } from "react";

import type { ConnectorConfig } from "../../types";

interface GoogleWorkspaceAdministrationProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canManageConnection: boolean;
  connectionWizard: ReactNode;
  gmailAuthorization?: ReactNode;
  userLookup: ReactNode;
  groupManagement: ReactNode;
  groupNavigationRequestId?: number;
}

function formatTestTime(value: string | null): string {
  if (!value) return "Not yet tested";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export function GoogleWorkspaceAdministration({
  organizationId,
  organizationName,
  connectorConfig,
  canManageConnection,
  connectionWizard,
  gmailAuthorization,
  userLookup,
  groupManagement,
  groupNavigationRequestId
}: GoogleWorkspaceAdministrationProps) {
  const needsSetup =
    !connectorConfig ||
    !connectorConfig.credentials_configured ||
    connectorConfig.status === "not_configured" ||
    connectorConfig.status === "configured";
  const isConnected = connectorConfig?.status === "connected";
  const isFailed = connectorConfig?.status === "connection_failed";
  const [showWizard, setShowWizard] = useState(needsSetup);
  const [activeTool, setActiveTool] = useState<"users" | "groups">("users");

  useEffect(() => {
    setShowWizard(needsSetup);
    setActiveTool("users");
  }, [organizationId, needsSetup]);

  useEffect(() => {
    if (groupNavigationRequestId !== undefined) setActiveTool("groups");
  }, [groupNavigationRequestId]);

  return (
    <div className="workspace-administration">
      {!organizationId ? (
        <section className="workspace-setup-callout" aria-label="Google Workspace setup unavailable">
          <Building2 aria-hidden="true" />
          <div>
            <h2>Select an organization</h2>
            <p>Choose an organization before configuring Google Workspace.</p>
          </div>
        </section>
      ) : needsSetup ? (
        <section className="workspace-setup-callout" aria-label="Google Workspace setup required">
          <KeyRound aria-hidden="true" />
          <div>
            <h2>Connect Google Workspace</h2>
            <p>
              Complete the setup and manually verify read-only Directory access for {organizationName}.
            </p>
          </div>
        </section>
      ) : (
        <section
          className={`workspace-connection-status ${isFailed ? "connection-failed" : ""}`}
          aria-label="Google Workspace connection status"
        >
          <div className="connection-status-item">
            <Building2 aria-hidden="true" />
            <span>Organization</span>
            <strong>{organizationName ?? "Selected organization"}</strong>
          </div>
          <div className="connection-status-item">
            {isConnected ? <CheckCircle2 aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
            <span>Connection state</span>
            <strong className={isConnected ? "connected" : "failed"}>
              {isConnected ? "Connected" : "Connection failed"}
            </strong>
          </div>
          <div className="connection-status-item">
            <Clock3 aria-hidden="true" />
            <span>{isConnected ? "Last successful test" : "Last attempted test"}</span>
            <strong>{formatTestTime(connectorConfig?.last_tested_at ?? null)}</strong>
          </div>
          <div className="connection-status-item">
            <KeyRound aria-hidden="true" />
            <span>API capability</span>
            <strong>Directory users & groups</strong>
          </div>
          {canManageConnection && (
            <button
              type="button"
              className="secondary-button manage-connection-button"
              onClick={() => setShowWizard((current) => !current)}
              aria-expanded={showWizard}
              aria-controls="workspace-connection-settings"
            >
              <Settings2 aria-hidden="true" />
              {showWizard ? "Close configuration" : isFailed ? "Inspect configuration" : "Manage connection"}
            </button>
          )}
          {isFailed && connectorConfig?.last_error && (
            <p className="connection-status-error" role="alert">
              {connectorConfig.last_error}
            </p>
          )}
        </section>
      )}

      {showWizard && organizationId && (
        <section id="workspace-connection-settings" className="workspace-settings-panel">
          <div className="workspace-section-heading">
            <div>
              <h2>Connection settings</h2>
              <p>Configure credentials, delegation and the manual connection test.</p>
            </div>
          </div>
          {connectionWizard}
          {gmailAuthorization}
        </section>
      )}

      <nav className="workspace-tool-navigation" aria-label="Google Workspace administration tools">
        <button
          type="button"
          className={activeTool === "users" ? "active" : ""}
          aria-current={activeTool === "users" ? "page" : undefined}
          onClick={() => setActiveTool("users")}
        >
          <UserRoundSearch aria-hidden="true" /> Users & aliases
        </button>
        <button
          type="button"
          className={activeTool === "groups" ? "active" : ""}
          aria-current={activeTool === "groups" ? "page" : undefined}
          onClick={() => setActiveTool("groups")}
        >
          <UsersRound aria-hidden="true" /> Groups
        </button>
      </nav>

      <section className="workspace-user-lookup-panel">
        {activeTool === "users" ? userLookup : groupManagement}
      </section>
    </div>
  );
}
