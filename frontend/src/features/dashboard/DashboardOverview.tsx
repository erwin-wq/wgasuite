import { Building2, CheckCircle2, CircleHelp, ShieldCheck, Users } from "lucide-react";

import type { ConnectorConfig } from "../../types";
import type { ActiveSection } from "../navigation/AppNavigation";

interface DashboardOverviewProps {
  customerName: string | null;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  onNavigate: (section: ActiveSection) => void;
}

function connectorLabel(connectorConfig: ConnectorConfig | null): string {
  if (!connectorConfig) return "Not configured";
  if (connectorConfig.status === "connected") return "Connected";
  if (connectorConfig.status === "connection_failed") return "Connection failed";
  return "Setup incomplete";
}

export function DashboardOverview({
  customerName,
  organizationName,
  connectorConfig,
  onNavigate
}: DashboardOverviewProps) {
  const connectorStatus = connectorLabel(connectorConfig);
  const isConnected = connectorConfig?.status === "connected";
  const nextStep = !customerName
    ? {
        title: "Select or create a customer",
        description: "Choose the customer context before administering an organization.",
        button: "Open Customer Context",
        target: "customers" as const
      }
    : !organizationName
      ? {
          title: "Select or create an organization",
          description: "Choose an organization within the active customer context.",
          button: "Open Organizations",
          target: "organizations" as const
        }
      : !isConnected
        ? {
            title: "Complete the Workspace connection",
            description: "Configure and manually test read-only Directory access.",
            button: "Open Google Workspace",
            target: "google-workspace" as const
          }
        : {
            title: "Look up a Workspace user or alias",
            description: "Search the connected Directory for one exact user account.",
            button: "Open User Lookup",
            target: "google-workspace" as const
          };

  return (
    <div className="dashboard-overview">
      <section className="current-workspace-panel" aria-labelledby="current-workspace-heading">
        <div className="workspace-panel-heading">
          <div>
            <h2 id="current-workspace-heading">Current workspace</h2>
            <p>Your active customer, organization and Google Workspace connection.</p>
          </div>
          {organizationName && (
            <button type="button" onClick={() => onNavigate("google-workspace")}>
              <ShieldCheck aria-hidden="true" />
              {isConnected ? "Open User Lookup" : "Open Google Workspace"}
            </button>
          )}
        </div>

        <div className="workspace-context-grid">
          <article>
            <Users aria-hidden="true" />
            <span>Active customer</span>
            <strong>{customerName ?? "Not selected"}</strong>
          </article>
          <article>
            <Building2 aria-hidden="true" />
            <span>Active organization</span>
            <strong>{organizationName ?? "Not selected"}</strong>
          </article>
          <article>
            {isConnected ? <CheckCircle2 aria-hidden="true" /> : <CircleHelp aria-hidden="true" />}
            <span>Google Workspace connection</span>
            <strong className={isConnected ? "dashboard-status-connected" : ""}>
              {connectorStatus}
            </strong>
          </article>
        </div>
      </section>

      <div className="dashboard-secondary-grid">
        <section className="truthful-status-panel" aria-labelledby="assessment-status-heading">
          <ShieldCheck aria-hidden="true" />
          <div>
            <h2 id="assessment-status-heading">Security assessment</h2>
            <strong>Not assessed</strong>
            <p>No evidence-backed Google Workspace security assessment has been run.</p>
          </div>
        </section>

        <section className="next-step-panel" aria-labelledby="next-step-heading">
          <div>
            <h2 id="next-step-heading">Next step</h2>
            <strong>{nextStep.title}</strong>
            <p>{nextStep.description}</p>
          </div>
          <button type="button" onClick={() => onNavigate(nextStep.target)}>
            {nextStep.button}
          </button>
        </section>
      </div>
    </div>
  );
}
