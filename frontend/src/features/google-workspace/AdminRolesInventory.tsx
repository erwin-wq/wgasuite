import {
  AlertCircle,
  Building2,
  CircleHelp,
  RefreshCw,
  ShieldCheck,
  UsersRound
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceAdminRoles } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Alert, Badge, EmptyState, ErrorState, Skeleton } from "../../components/ui/Feedback";
import { SearchField, Select } from "../../components/ui/FormControls";
import type {
  ConnectorConfig,
  GoogleWorkspaceAdminRole,
  GoogleWorkspaceAdminRoleInventory,
  GoogleWorkspaceRoleAssignment
} from "../../types";
import { DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE } from "./scopes";

interface AdminRolesInventoryProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canRead: boolean;
}

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "The administrator role inventory could not be loaded.";
  if (["missing_scope_or_permission", "delegation_rejected", "google_forbidden"].includes(error.code ?? "")) {
    return `Google denied role-management access. Authorize ${DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE} for this connector and verify the delegated administrator can read roles.`;
  }
  if (error.status === 403) return "You do not have permission to view this tenant's administrator roles.";
  return error.message;
}

function roleBadge(role: GoogleWorkspaceAdminRole) {
  if (role.is_super_admin_role) return <Badge variant="warning">Super administrator</Badge>;
  if (role.is_system_role) return <Badge variant="info">System role</Badge>;
  return <Badge variant="neutral">Custom role</Badge>;
}

function assignmentScope(assignment: GoogleWorkspaceRoleAssignment) {
  if (assignment.scope_type === "CUSTOMER") return <Badge variant="info">Customer-wide</Badge>;
  if (assignment.scope_type === "ORG_UNIT") return <Badge variant="neutral">Organizational unit</Badge>;
  return <Badge variant="warning">Unknown scope</Badge>;
}

export function AdminRolesInventory({
  organizationId,
  organizationName,
  connectorConfig,
  canRead
}: AdminRolesInventoryProps) {
  const [inventory, setInventory] = useState<GoogleWorkspaceAdminRoleInventory | null>(null);
  const [search, setSearch] = useState("");
  const [roleType, setRoleType] = useState("all");
  const [assignmentFilter, setAssignmentFilter] = useState("all");
  const deferredSearch = useDeferredValue(search.trim().toLocaleLowerCase());
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const connectorReady = connectorConfig?.status === "connected";

  const load = useCallback(async () => {
    if (!organizationId || !canRead || !connectorReady) return;
    const request = ++sequence.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setLoading(true);
    setError(null);
    try {
      const result = await listGoogleWorkspaceAdminRoles(organizationId, nextController.signal);
      if (request !== sequence.current || nextController.signal.aborted) return;
      setInventory(result);
      setSelectedRoleId((current) =>
        current && result.roles.some((role) => role.role_id === current) ? current : null
      );
    } catch (caught) {
      if (request !== sequence.current || nextController.signal.aborted) return;
      setInventory(null);
      setError(errorMessage(caught));
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [canRead, connectorReady, organizationId]);

  useEffect(() => {
    sequence.current += 1;
    controller.current?.abort();
    setInventory(null);
    setSelectedRoleId(null);
    setSearch("");
    setRoleType("all");
    setAssignmentFilter("all");
    setError(null);
    setLoading(false);
    if (organizationId && canRead && connectorReady) void load();
    return () => controller.current?.abort();
  }, [canRead, connectorReady, load, organizationId]);

  const assignmentCountsByRole = useMemo(() => {
    const counts = new Map<string, number>();
    for (const assignment of inventory?.assignments ?? []) {
      counts.set(assignment.role_id, (counts.get(assignment.role_id) ?? 0) + 1);
    }
    return counts;
  }, [inventory]);
  const roles = useMemo(() => {
    const values = inventory?.roles ?? [];
    return values.filter((role) => {
      const matchesSearch = !deferredSearch ||
        [role.name, role.description ?? "", role.is_system_role ? "system" : "custom"]
          .some((value) => value.toLocaleLowerCase().includes(deferredSearch));
      const matchesType = roleType === "all" ||
        (roleType === "super" && role.is_super_admin_role) ||
        (roleType === "system" && role.is_system_role && !role.is_super_admin_role) ||
        (roleType === "custom" && !role.is_system_role);
      const hasAssignments = (assignmentCountsByRole.get(role.role_id) ?? 0) > 0;
      const matchesAssignment = assignmentFilter === "all" ||
        (assignmentFilter === "assigned" && hasAssignments) ||
        (assignmentFilter === "unassigned" && !hasAssignments);
      return matchesSearch && matchesType && matchesAssignment;
    });
  }, [assignmentCountsByRole, assignmentFilter, deferredSearch, inventory, roleType]);
  const selectedRole = inventory?.roles.find((role) => role.role_id === selectedRoleId) ?? null;
  const selectedAssignments = inventory?.assignments.filter(
    (assignment) => assignment.role_id === selectedRoleId
  ) ?? [];
  const roleColumns = useMemo<readonly DataTableColumn<GoogleWorkspaceAdminRole>[]>(() => [
    { id: "name", header: "Role", cell: (role) => <strong>{role.name}</strong> },
    { id: "type", header: "Type", cell: roleBadge },
    { id: "privileges", header: "Privileges", cell: (role) => role.privileges.length.toLocaleString() },
    {
      id: "assignments",
      header: "Direct assignments",
      cell: (role) => assignmentCountsByRole.get(role.role_id) ?? 0
    },
    {
      id: "actions",
      header: "Details",
      cell: (role) => (
        <Button
          variant="secondary"
          size="sm"
          aria-label={`View details for ${role.name}`}
          aria-pressed={role.role_id === selectedRoleId}
          onClick={() => setSelectedRoleId(role.role_id)}
        >
          {role.role_id === selectedRoleId ? "Selected" : "View"}
        </Button>
      )
    }
  ], [assignmentCountsByRole, selectedRoleId]);

  if (!organizationId) return <EmptyState title="Select an organization" icon={<Building2 aria-hidden="true" />}>Choose an organization to view administrator roles.</EmptyState>;
  if (!canRead) return <EmptyState title="Access unavailable" icon={<AlertCircle aria-hidden="true" />}>Connector-operation access is required.</EmptyState>;
  if (!connectorReady) return <EmptyState title="Connect Google Workspace" icon={<ShieldCheck aria-hidden="true" />}>Connect and test Google Workspace for {organizationName ?? "this organization"} first.</EmptyState>;

  return (
    <section className="admin-roles-inventory" aria-labelledby="admin-roles-heading">
      <div className="workspace-section-heading admin-roles-heading">
        <div><h2 id="admin-roles-heading">Admin roles & assignments</h2><p>Authoritative read-only direct assignments from Google Directory.</p></div>
        <Button variant="secondary" disabled={loading} onClick={() => void load()}><RefreshCw className={loading ? "spin" : ""} aria-hidden="true" /> Refresh</Button>
      </div>
      <Alert variant="info" title="Direct assignments, not effective permissions">
        Group-derived, inherited, and otherwise effective administrator access is not calculated here. Assignee identifiers are immutable Google IDs, not resolved account names.
      </Alert>
      <div className="admin-role-summary" aria-label="Administrator role inventory summary">
        <Card padding="sm"><ShieldCheck aria-hidden="true" /><span><strong>{inventory?.role_count ?? 0}</strong> Roles</span></Card>
        <Card padding="sm"><UsersRound aria-hidden="true" /><span><strong>{inventory?.assignment_count ?? 0}</strong> Direct assignments</span></Card>
      </div>
      <div className="admin-role-filters" aria-label="Role inventory filters">
        <SearchField className="admin-roles-search" label="Search roles" value={search} onChange={(event) => setSearch(event.target.value)} onClear={() => setSearch("")} placeholder="Role name or description" />
        <Select
          label="Role type"
          value={roleType}
          onChange={(event) => setRoleType(event.target.value)}
          options={[
            { value: "all", label: "All role types" },
            { value: "super", label: "Super administrator" },
            { value: "system", label: "System roles" },
            { value: "custom", label: "Custom roles" }
          ]}
        />
        <Select
          label="Direct assignments"
          value={assignmentFilter}
          onChange={(event) => setAssignmentFilter(event.target.value)}
          options={[
            { value: "all", label: "All assignment states" },
            { value: "assigned", label: "Has direct assignments" },
            { value: "unassigned", label: "No direct assignments" }
          ]}
        />
      </div>
      {loading && !inventory ? <div aria-busy="true"><span className="sr-only">Loading administrator roles.</span><Skeleton lines={6} /></div> : null}
      {error ? <ErrorState title="Admin roles unavailable" actionLabel="Try again" onAction={() => void load()}>{error}</ErrorState> : null}
      {!loading && !error && inventory && roles.length === 0 ? <EmptyState title={search ? "No matching roles" : "No roles returned"} icon={<CircleHelp aria-hidden="true" />}>{search ? "Try another search." : "Google returned no administrator roles for this customer."}</EmptyState> : null}
      {inventory && roles.length ? (
        <DataTable<GoogleWorkspaceAdminRole>
          ariaLabel="Administrator roles"
          columns={roleColumns}
          rows={roles}
          rowKey={(role) => role.role_id}
          emptyTitle="No roles returned"
          emptyDescription="Google returned no administrator roles for this customer."
          minWidth="48rem"
        />
      ) : null}
      {selectedRole ? (
        <aside className="admin-role-detail" aria-labelledby="admin-role-detail-heading">
          <div><span className="eyebrow">Read-only role detail</span><h3 id="admin-role-detail-heading">{selectedRole.name}</h3><p>{selectedRole.description ?? "No description provided."}</p></div>
          <div className="admin-role-detail-grid"><div><span>Role type</span>{roleBadge(selectedRole)}</div><div><span>Privilege entries</span><strong>{selectedRole.privileges.length}</strong></div><div><span>Direct assignments</span><strong>{selectedAssignments.length}</strong></div></div>
          <section aria-labelledby="role-privileges-heading"><h4 id="role-privileges-heading">Privilege summary</h4>{selectedRole.privileges.length ? <ul className="admin-role-privileges">{selectedRole.privileges.map((privilege) => <li key={`${privilege.service_id}:${privilege.privilege_name}`}><span>{privilege.privilege_name}</span><code>{privilege.service_id}</code></li>)}</ul> : <p>No privilege entries were returned.</p>}</section>
          <section aria-labelledby="direct-assignments-heading"><h4 id="direct-assignments-heading">Direct assignments</h4>{selectedAssignments.length ? <ul className="admin-role-assignments">{selectedAssignments.map((assignment) => <li key={assignment.assignment_id}><div><Badge variant="neutral">{assignment.assignee_type}</Badge>{assignmentScope(assignment)}</div><code>{assignment.assigned_to}</code>{assignment.org_unit_id ? <p>OU ID: <code>{assignment.org_unit_id}</code></p> : null}{assignment.condition ? <p>Condition: {assignment.condition}</p> : null}</li>)}</ul> : <p>No direct assignments were returned for this role.</p>}</section>
        </aside>
      ) : null}
    </section>
  );
}
