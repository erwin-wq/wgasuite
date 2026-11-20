import {
  AlertTriangle,
  Building2,
  Cable,
  CheckCircle2,
  FolderTree,
  KeyRound,
  Settings2,
  UserRoundSearch,
  UsersRound
} from "lucide-react";
import { ReactNode, useEffect, useState } from "react";

import { Button } from "../../components/ui/Button";
import { Badge, ErrorState, Skeleton } from "../../components/ui/Feedback";
import type { ConnectorConfig } from "../../types";

interface GoogleWorkspaceAdministrationProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canManageConnection: boolean;
  canTestConnection?: boolean;
  isLoading?: boolean;
  hasLoadError?: boolean;
  isTesting?: boolean;
  onReload?: () => void;
  onTest?: () => void;
  connectionWizard: ReactNode;
  gmailAuthorization?: ReactNode;
  userLookup: ReactNode;
  groupManagement: ReactNode;
  organizationalUnits: ReactNode;
  groupNavigationRequestId?: number;
}

interface WorkspaceConnectionOverviewProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canManageConnection: boolean;
  canTestConnection?: boolean;
  isLoading?: boolean;
  hasLoadError?: boolean;
  isTesting?: boolean;
  onReload?: () => void;
  onTest?: () => void;
  connectionWizard: ReactNode;
  gmailAuthorization?: ReactNode;
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
  canTestConnection = canManageConnection,
  isLoading = false,
  hasLoadError = false,
  isTesting = false,
  onReload,
  onTest,
  connectionWizard,
  gmailAuthorization,
  userLookup,
  groupManagement,
  organizationalUnits,
  groupNavigationRequestId
}: GoogleWorkspaceAdministrationProps) {
  return (
    <div className="workspace-administration">
      <WorkspaceConnectionOverview
        organizationId={organizationId}
        organizationName={organizationName}
        connectorConfig={connectorConfig}
        canManageConnection={canManageConnection}
        canTestConnection={canTestConnection}
        isLoading={isLoading}
        hasLoadError={hasLoadError}
        isTesting={isTesting}
        onReload={onReload}
        onTest={onTest}
        connectionWizard={connectionWizard}
        gmailAuthorization={gmailAuthorization}
      />
      <WorkspaceToolPanels
        organizationId={organizationId}
        userLookup={userLookup}
        groupManagement={groupManagement}
        organizationalUnits={organizationalUnits}
        groupNavigationRequestId={groupNavigationRequestId}
      />
    </div>
  );
}

export function WorkspaceConnectionOverview({
  organizationId,
  organizationName,
  connectorConfig,
  canManageConnection,
  canTestConnection = canManageConnection,
  isLoading = false,
  hasLoadError = false,
  isTesting = false,
  onReload,
  onTest,
  connectionWizard,
  gmailAuthorization
}: WorkspaceConnectionOverviewProps) {
  const needsSetup =
    !connectorConfig ||
    !connectorConfig.credentials_configured ||
    connectorConfig.status === "not_configured" ||
    connectorConfig.status === "configured";
  const isConnected = connectorConfig?.status === "connected";
  const isFailed = connectorConfig?.status === "connection_failed";
  const [showWizard, setShowWizard] = useState(needsSetup);

  useEffect(() => {
    setShowWizard(needsSetup);
  }, [organizationId, needsSetup]);

  return (
    <div className="workspace-connection-overview">
      {isLoading ? (
        <section className="connection-loading" role="status" aria-label="Loading connection configuration">
          <Skeleton lines={5} />
        </section>
      ) : hasLoadError ? (
        <ErrorState
          title="Connection status unavailable"
          actionLabel={onReload ? "Try again" : undefined}
          onAction={onReload}
        >
          The connector configuration could not be loaded. This is not the same as an unconfigured connection.
        </ErrorState>
      ) : !organizationId ? (
        <section className="workspace-setup-callout" aria-label="Google Workspace setup unavailable">
          <Building2 aria-hidden="true" />
          <div>
            <h2>Select an organization</h2>
            <p>Choose an organization before configuring Google Workspace.</p>
          </div>
        </section>
      ) : needsSetup ? (
        <>
          <section className="workspace-setup-callout" aria-label="Google Workspace setup required">
            <KeyRound aria-hidden="true" />
            <div>
              <h2>Connect Google Workspace</h2>
              <p>
                {connectorConfig
                  ? `Complete and verify the existing configuration for ${organizationName}.`
                  : `No connector is configured for ${organizationName}. Complete the guided setup to establish one.`}
              </p>
            </div>
          </section>
          {organizationId ? (
            <section id="workspace-connection-settings" className="workspace-settings-panel setup-required">
              {connectionWizard}
              {gmailAuthorization}
            </section>
          ) : null}
        </>
      ) : (
        <>
          <section
            className={`workspace-connection-status ${isFailed ? "connection-failed" : ""}`}
            aria-label="Google Workspace connection status"
          >
            <div className="connection-status-heading">
              <span className="connection-status-icon"><Cable aria-hidden="true" /></span>
              <div>
                <h2>{connectorConfig?.display_name ?? "Google Workspace"}</h2>
                <p>{organizationName ?? "Selected organization"}</p>
              </div>
              <Badge variant={isConnected ? "success" : "danger"}>
                {isConnected ? <CheckCircle2 aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
                {isConnected ? "Connected" : "Connection failed"}
              </Badge>
            </div>
            <dl className="connection-facts">
              <div><dt>Primary domain</dt><dd>{connectorConfig?.primary_domain ?? "Unavailable"}</dd></div>
              <div><dt>Delegated administrator</dt><dd>{connectorConfig?.admin_subject_email ?? "Not configured"}</dd></div>
              <div><dt>Credential source</dt><dd>{connectorConfig?.credentials_configured ? "Configured" : "Not configured"}</dd></div>
              <div><dt>{isConnected ? "Last successful test" : "Last attempted test"}</dt><dd>{formatTestTime(connectorConfig?.last_tested_at ?? null)}</dd></div>
            </dl>
            {isFailed && connectorConfig?.last_error ? (
              <p className="connection-status-error" role="alert">{connectorConfig.last_error}</p>
            ) : null}
            <div className="connection-status-actions">
              {!showWizard && canTestConnection && onTest ? (
                <Button loading={isTesting} loadingLabel="Testing connection" onClick={onTest}>
                  <CheckCircle2 aria-hidden="true" /> Test connection
                </Button>
              ) : null}
              {canManageConnection ? (
                <Button
                  variant="secondary"
                  onClick={() => setShowWizard((current) => !current)}
                  aria-expanded={showWizard}
                  aria-controls="workspace-connection-settings"
                >
                  <Settings2 aria-hidden="true" />
                  {showWizard ? "Close configuration" : isFailed ? "Inspect configuration" : "Manage connection"}
                </Button>
              ) : null}
            </div>
          </section>

          {canManageConnection ? (
            <details className="connection-disclosure" open={showWizard} onToggle={(event) => setShowWizard(event.currentTarget.open)}>
              <summary><Settings2 aria-hidden="true" /><span><strong>Advanced configuration</strong><small>Credentials, delegated administrator, and connection test settings.</small></span></summary>
              <section id="workspace-connection-settings" className="workspace-settings-panel">
                {connectionWizard}
              </section>
            </details>
          ) : null}
          {gmailAuthorization ? (
            <details className="connection-disclosure">
              <summary><KeyRound aria-hidden="true" /><span><strong>Troubleshooting &amp; authorization</strong><small>Review Gmail delegation authorization guidance when needed.</small></span></summary>
              <section className="workspace-settings-panel authorization-panel">{gmailAuthorization}</section>
            </details>
          ) : null}
        </>
      )}
    </div>
  );
}

function WorkspaceToolPanels({
  organizationId,
  userLookup,
  groupManagement,
  organizationalUnits,
  groupNavigationRequestId
}: Pick<
  GoogleWorkspaceAdministrationProps,
  | "organizationId"
  | "userLookup"
  | "groupManagement"
  | "organizationalUnits"
  | "groupNavigationRequestId"
>) {
  const [activeTool, setActiveTool] = useState<"users" | "groups" | "orgunits">("users");

  useEffect(() => {
    setActiveTool("users");
  }, [organizationId]);

  useEffect(() => {
    if (groupNavigationRequestId !== undefined) setActiveTool("groups");
  }, [groupNavigationRequestId]);

  return (
    <>
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
        <button
          type="button"
          className={activeTool === "orgunits" ? "active" : ""}
          aria-current={activeTool === "orgunits" ? "page" : undefined}
          onClick={() => setActiveTool("orgunits")}
        >
          <FolderTree aria-hidden="true" /> Organizational Units
        </button>
      </nav>

      <section className="workspace-user-lookup-panel">
        {activeTool === "users"
          ? userLookup
          : activeTool === "groups"
            ? groupManagement
            : organizationalUnits}
      </section>
    </>
  );
}
