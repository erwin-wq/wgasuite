import { Activity, Building2, Cable, ClipboardList, RefreshCw } from "lucide-react";

import { Button } from "../../components/ui/Button";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Badge, ErrorState, Skeleton } from "../../components/ui/Feedback";
import type {
  PlatformAdminAuditEventSummary,
  PlatformAdminConnectorSummary,
  PlatformAdminCustomerSummary,
  PlatformAdminOverview,
  PlatformAdminScanRunSummary
} from "../../types";

interface PlatformAdministrationProps {
  overview: PlatformAdminOverview | null;
  loading: boolean;
  error: string | null;
  demoFeaturesEnabled: boolean;
  onRefresh: () => void;
}

function formatDateTime(value: string | null): string {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusVariant(value: string): "success" | "warning" | "danger" | "neutral" {
  if (["active", "connected", "completed", "success"].includes(value)) return "success";
  if (["configured", "prospect", "pending", "running"].includes(value)) return "warning";
  if (["connection_failed", "failed", "error", "denied"].includes(value)) return "danger";
  return "neutral";
}

const customerColumns: DataTableColumn<PlatformAdminCustomerSummary>[] = [
  {
    id: "customer",
    header: "Customer",
    cell: (customer) => <span className="admin-primary-cell"><strong>{customer.name}</strong><span>{customer.slug}</span></span>
  },
  { id: "status", header: "Status", cell: (customer) => <Badge variant={statusVariant(customer.status)}>{customer.status}</Badge> },
  { id: "organizations", header: "Organizations", cell: (customer) => customer.organization_count },
  { id: "connectors", header: "Connector configurations", cell: (customer) => customer.connector_config_count },
  { id: "audit", header: "Last audit event", cell: (customer) => formatDateTime(customer.last_audit_event_at) }
];

const connectorColumns: DataTableColumn<PlatformAdminConnectorSummary>[] = [
  {
    id: "organization",
    header: "Organization",
    cell: (connector) => <span className="admin-primary-cell"><strong>{connector.organization_name}</strong><span>{connector.customer_name ?? "No customer"}</span></span>
  },
  { id: "type", header: "Connector", cell: (connector) => connector.connector_type.replace(/_/g, " ") },
  { id: "status", header: "Status", cell: (connector) => <Badge variant={statusVariant(connector.status)}>{connector.status.replace(/_/g, " ")}</Badge> },
  { id: "domain", header: "Primary domain", cell: (connector) => connector.primary_domain ?? "Unavailable" },
  { id: "tested", header: "Last tested", cell: (connector) => formatDateTime(connector.last_tested_at) },
  { id: "error", header: "Last error", cell: (connector) => connector.last_error ?? "None reported" }
];

const auditColumns: DataTableColumn<PlatformAdminAuditEventSummary>[] = [
  { id: "time", header: "Time", cell: (event) => formatDateTime(event.created_at) },
  {
    id: "actor",
    header: "Actor",
    cell: (event) => <span className="admin-primary-cell"><strong>{event.actor_email ?? "System"}</strong><span>{event.actor_role ?? "No role"}</span></span>
  },
  { id: "customer", header: "Customer", cell: (event) => event.customer_name ?? "Platform" },
  { id: "action", header: "Action", cell: (event) => event.action },
  { id: "object", header: "Object type", cell: (event) => event.object_type },
  { id: "outcome", header: "Outcome", cell: (event) => <Badge variant={statusVariant(event.outcome)}>{event.outcome}</Badge> }
];

const scanColumns: DataTableColumn<PlatformAdminScanRunSummary>[] = [
  { id: "customer", header: "Customer", cell: (scan) => scan.customer_name ?? "No customer" },
  { id: "organization", header: "Organization", cell: (scan) => scan.organization_name },
  { id: "assessment", header: "Assessment", cell: (scan) => scan.assessment_title },
  { id: "status", header: "Status", cell: (scan) => <Badge variant={statusVariant(scan.status)}>{scan.status}</Badge> },
  { id: "findings", header: "Findings", cell: (scan) => scan.findings_created },
  { id: "completed", header: "Completed", cell: (scan) => formatDateTime(scan.completed_at) }
];

export function PlatformAdministration({
  overview,
  loading,
  error,
  demoFeaturesEnabled,
  onRefresh
}: PlatformAdministrationProps) {
  return (
    <section className="platform-administration" aria-label="Platform support overview">
      <div className="administration-toolbar platform-administration-toolbar">
        <div>
          <h2>Read-only support overview</h2>
          <p>Platform-wide operational metadata for authorized support roles. Secret fields are excluded.</p>
        </div>
        <Button variant="secondary" loading={loading} loadingLabel="Refreshing overview" onClick={onRefresh}>
          <RefreshCw aria-hidden="true" /> Refresh overview
        </Button>
      </div>

      {error ? (
        <ErrorState title="Platform overview unavailable" actionLabel="Try again" onAction={onRefresh}>{error}</ErrorState>
      ) : loading && !overview ? (
        <div className="platform-administration-loading" role="status" aria-label="Loading platform overview"><Skeleton lines={8} /></div>
      ) : overview ? (
        <>
          <dl className="platform-summary-strip" aria-label="Platform totals">
            <div><dt><Building2 aria-hidden="true" /> Customers</dt><dd>{overview.totals.customers_count}</dd></div>
            <div><dt><Building2 aria-hidden="true" /> Organizations</dt><dd>{overview.totals.organizations_count}</dd></div>
            <div><dt><Cable aria-hidden="true" /> Connector configurations</dt><dd>{overview.totals.connector_configs_count}</dd></div>
            <div><dt><ClipboardList aria-hidden="true" /> Audit events</dt><dd>{overview.totals.audit_events_count}</dd></div>
          </dl>

          <section className="platform-table-section" aria-labelledby="platform-customers-heading">
            <div className="platform-table-heading"><h3 id="platform-customers-heading">Customer overview</h3><p>Customer status, relationships, and recent audit activity.</p></div>
            <DataTable ariaLabel="Platform customer overview" columns={customerColumns} rows={overview.customers} rowKey={(customer) => customer.id} emptyTitle="No customers" emptyDescription="No customer records are available." minWidth="52rem" />
          </section>

          <section className="platform-table-section" aria-labelledby="platform-connectors-heading">
            <div className="platform-table-heading"><h3 id="platform-connectors-heading">Connector status</h3><p>Non-secret connector configuration and verification metadata.</p></div>
            <DataTable ariaLabel="Platform connector status" columns={connectorColumns} rows={overview.connector_configs} rowKey={(connector) => connector.id} emptyTitle="No connector configurations" emptyDescription="No connector configuration records are available." minWidth="68rem" />
          </section>

          {demoFeaturesEnabled ? (
            <section className="platform-table-section" aria-labelledby="platform-scans-heading">
              <div className="platform-table-heading"><h3 id="platform-scans-heading">Recent demo scan runs</h3><p>Development-only scan metadata for troubleshooting.</p></div>
              <DataTable ariaLabel="Recent demo scan runs" columns={scanColumns} rows={overview.recent_scan_runs} rowKey={(scan) => scan.id} emptyTitle="No scan runs" emptyDescription="No development scan runs are available." minWidth="60rem" />
            </section>
          ) : null}

          <section className="platform-table-section" aria-labelledby="platform-audit-heading">
            <div className="platform-table-heading"><h3 id="platform-audit-heading">Recent audit events</h3><p>Recent events without private metadata or secret fields.</p></div>
            <DataTable ariaLabel="Recent platform audit events" columns={auditColumns} rows={overview.recent_audit_events} rowKey={(event) => event.id} emptyTitle="No audit events" emptyDescription="No recent audit events are available." minWidth="68rem" />
          </section>
        </>
      ) : (
        <div className="platform-administration-loading" role="status"><Activity aria-hidden="true" />Open or refresh the overview to load support data.</div>
      )}
    </section>
  );
}
