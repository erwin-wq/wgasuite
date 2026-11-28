import {
  AlertCircle,
  Building2,
  CircleHelp,
  RefreshCw,
  ShieldCheck,
  UsersRound
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  getGoogleWorkspaceAdminRole,
  getGoogleWorkspaceRoleAssignment,
  listGoogleWorkspaceAdminRoles,
  resolveGoogleWorkspaceRoleAssignmentPrincipal
} from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Alert, Badge, EmptyState, ErrorState, Skeleton } from "../../components/ui/Feedback";
import { SearchField, Select } from "../../components/ui/FormControls";
import type {
  ConnectorConfig,
  GoogleWorkspaceAdminRole,
  GoogleWorkspaceAdminRoleDetail,
  GoogleWorkspaceAdminRoleInventory,
  GoogleWorkspaceAdminPrincipal,
  GoogleWorkspaceRoleAssignment,
  GoogleWorkspaceRoleAssignmentDetail
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

function detailErrorMessage(error: unknown, resource: "role" | "assignment"): string {
  if (!(error instanceof ApiError)) return `The administrator ${resource} could not be loaded.`;
  if (error.status === 404) return `This administrator ${resource} no longer exists. Refresh the inventory.`;
  return errorMessage(error);
}

function formatExpiration(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Invalid timestamp returned by Google";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short"
  }).format(parsed);
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

function principalKey(assignment: GoogleWorkspaceRoleAssignment): string {
  return `${assignment.assignee_type}:${assignment.assigned_to}`;
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
  const [roleDetail, setRoleDetail] = useState<GoogleWorkspaceAdminRoleDetail | null>(null);
  const [roleDetailLoading, setRoleDetailLoading] = useState(false);
  const [roleDetailError, setRoleDetailError] = useState<string | null>(null);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [assignmentDetail, setAssignmentDetail] = useState<GoogleWorkspaceRoleAssignmentDetail | null>(null);
  const [assignmentDetailLoading, setAssignmentDetailLoading] = useState(false);
  const [assignmentDetailError, setAssignmentDetailError] = useState<string | null>(null);
  const [principal, setPrincipal] = useState<GoogleWorkspaceAdminPrincipal | null>(null);
  const [resolvedPrincipals, setResolvedPrincipals] = useState(
    new Map<string, GoogleWorkspaceAdminPrincipal>()
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const inventoryRef = useRef<GoogleWorkspaceAdminRoleInventory | null>(null);
  const controller = useRef<AbortController | null>(null);
  const roleDetailSequence = useRef(0);
  const roleDetailController = useRef<AbortController | null>(null);
  const assignmentDetailSequence = useRef(0);
  const assignmentDetailController = useRef<AbortController | null>(null);
  const principalCache = useRef(new Map<string, GoogleWorkspaceAdminPrincipal>());
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
      inventoryRef.current = result;
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

  const loadRoleDetail = useCallback(async (roleId: string) => {
    const request = ++roleDetailSequence.current;
    roleDetailController.current?.abort();
    const nextController = new AbortController();
    roleDetailController.current = nextController;
    setRoleDetail(null);
    setRoleDetailError(null);
    setRoleDetailLoading(true);
    try {
      const result = await getGoogleWorkspaceAdminRole(
        organizationId,
        roleId,
        nextController.signal
      );
      if (request !== roleDetailSequence.current || nextController.signal.aborted) return;
      setRoleDetail(result);
    } catch (caught) {
      if (request !== roleDetailSequence.current || nextController.signal.aborted) return;
      setRoleDetailError(detailErrorMessage(caught, "role"));
    } finally {
      if (request === roleDetailSequence.current) setRoleDetailLoading(false);
    }
  }, [organizationId]);

  const loadAssignmentDetail = useCallback(async (assignmentId: string) => {
    const request = ++assignmentDetailSequence.current;
    assignmentDetailController.current?.abort();
    const nextController = new AbortController();
    assignmentDetailController.current = nextController;
    setAssignmentDetail(null);
    setPrincipal(null);
    setAssignmentDetailError(null);
    setAssignmentDetailLoading(true);
    try {
      const assignment = inventoryRef.current?.assignments.find(
        (item) => item.assignment_id === assignmentId
      );
      const cacheKey = assignment ? principalKey(assignment) : null;
      const cachedPrincipal = cacheKey ? principalCache.current.get(cacheKey) : undefined;
      if (cachedPrincipal) {
        const result = await getGoogleWorkspaceRoleAssignment(
          organizationId,
          assignmentId,
          nextController.signal
        );
        if (request !== assignmentDetailSequence.current || nextController.signal.aborted) return;
        setAssignmentDetail(result);
        setPrincipal(cachedPrincipal);
        return;
      }
      const result = await resolveGoogleWorkspaceRoleAssignmentPrincipal(
        organizationId,
        assignmentId,
        nextController.signal
      );
      if (request !== assignmentDetailSequence.current || nextController.signal.aborted) return;
      setAssignmentDetail({
        assignment: result.assignment,
        direct_assignment: result.direct_assignment,
        effective_permissions_included: result.effective_permissions_included,
        read_only: result.read_only
      });
      setPrincipal(result.principal);
      principalCache.current.set(
        principalKey(result.assignment),
        result.principal
      );
      setResolvedPrincipals(new Map(principalCache.current));
    } catch (caught) {
      if (request !== assignmentDetailSequence.current || nextController.signal.aborted) return;
      setAssignmentDetailError(detailErrorMessage(caught, "assignment"));
    } finally {
      if (request === assignmentDetailSequence.current) setAssignmentDetailLoading(false);
    }
  }, [organizationId]);

  const selectRole = useCallback((roleId: string) => {
    setSelectedRoleId(roleId);
    setSelectedAssignmentId(null);
    setAssignmentDetail(null);
    setPrincipal(null);
    setAssignmentDetailError(null);
    assignmentDetailSequence.current += 1;
    assignmentDetailController.current?.abort();
    void loadRoleDetail(roleId);
  }, [loadRoleDetail]);

  const selectAssignment = useCallback((assignmentId: string) => {
    setSelectedAssignmentId(assignmentId);
    void loadAssignmentDetail(assignmentId);
  }, [loadAssignmentDetail]);

  useEffect(() => {
    sequence.current += 1;
    controller.current?.abort();
    roleDetailSequence.current += 1;
    roleDetailController.current?.abort();
    assignmentDetailSequence.current += 1;
    assignmentDetailController.current?.abort();
    setInventory(null);
    inventoryRef.current = null;
    setSelectedRoleId(null);
    setRoleDetail(null);
    setRoleDetailError(null);
    setRoleDetailLoading(false);
    setSelectedAssignmentId(null);
    setAssignmentDetail(null);
    setAssignmentDetailError(null);
    setAssignmentDetailLoading(false);
    principalCache.current.clear();
    setResolvedPrincipals(new Map());
    setSearch("");
    setRoleType("all");
    setAssignmentFilter("all");
    setError(null);
    setLoading(false);
    if (organizationId && canRead && connectorReady) void load();
    return () => {
      controller.current?.abort();
      roleDetailController.current?.abort();
      assignmentDetailController.current?.abort();
    };
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
          onClick={() => selectRole(role.role_id)}
        >
          {role.role_id === selectedRoleId ? "Selected" : "View"}
        </Button>
      )
    }
  ], [assignmentCountsByRole, selectRole, selectedRoleId]);

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
        Verified identities describe only the principal directly referenced by each assignment. Group membership, inherited access, and otherwise effective administrator permissions are not calculated here.
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
          <div className="admin-role-detail-heading">
            <div><span className="eyebrow">Authoritative read-only role detail</span><h3 id="admin-role-detail-heading">{selectedRole.name}</h3></div>
            <Button variant="secondary" size="sm" disabled={roleDetailLoading} onClick={() => void loadRoleDetail(selectedRole.role_id)}><RefreshCw className={roleDetailLoading ? "spin" : ""} aria-hidden="true" /> Refresh role</Button>
          </div>
          {roleDetailLoading ? <div aria-busy="true"><span className="sr-only">Loading administrator role detail.</span><Skeleton lines={4} /></div> : null}
          {roleDetailError ? <ErrorState title="Role detail unavailable" actionLabel="Try again" onAction={() => void loadRoleDetail(selectedRole.role_id)}>{roleDetailError}</ErrorState> : null}
          {roleDetail?.role.role_id === selectedRole.role_id ? (
            <>
              <p>{roleDetail.role.description ?? "No description provided."}</p>
              <div className="admin-role-detail-grid"><div><span>Role type</span>{roleBadge(roleDetail.role)}</div><div><span>Privilege entries</span><strong>{roleDetail.role.privileges.length}</strong></div><div><span>Direct assignments</span><strong>{selectedAssignments.length}</strong></div></div>
              <section aria-labelledby="role-privileges-heading"><h4 id="role-privileges-heading">Privilege details</h4>{roleDetail.role.privileges.length ? <ul className="admin-role-privileges">{roleDetail.role.privileges.map((privilege) => <li key={`${privilege.service_id}:${privilege.privilege_name}`}><span>{privilege.privilege_name}</span><code>{privilege.service_id}</code></li>)}</ul> : <p>No privilege entries were returned.</p>}</section>
            </>
          ) : null}
          <section aria-labelledby="direct-assignments-heading">
            <h4 id="direct-assignments-heading">Direct assignments</h4>
            {selectedAssignments.length ? <ul className="admin-role-assignments">{selectedAssignments.map((assignment) => {
              const resolved = resolvedPrincipals.get(principalKey(assignment));
              return <li key={assignment.assignment_id}><div><Badge variant="neutral">{assignment.assignee_type}</Badge>{assignmentScope(assignment)}</div>{resolved?.outcome === "verified" ? <span className="admin-principal-summary"><strong>{resolved.display_name ?? resolved.primary_email}</strong>{resolved.display_name && resolved.primary_email ? <small>{resolved.primary_email}</small> : null}</span> : <code>{assignment.assigned_to}</code>}<Button variant="secondary" size="sm" aria-pressed={assignment.assignment_id === selectedAssignmentId} onClick={() => selectAssignment(assignment.assignment_id)}>{assignment.assignment_id === selectedAssignmentId ? "Selected assignment" : "View assignment"}</Button></li>;
            })}</ul> : <p>No direct assignments were returned for this role.</p>}
          </section>
        </aside>
      ) : null}
      {selectedAssignmentId ? (
        <aside className="admin-role-detail admin-assignment-detail" aria-labelledby="admin-assignment-detail-heading">
          <div className="admin-role-detail-heading">
            <div><span className="eyebrow">Authoritative direct assignment detail</span><h3 id="admin-assignment-detail-heading">Direct assignment</h3></div>
            <Button variant="secondary" size="sm" disabled={assignmentDetailLoading} onClick={() => void loadAssignmentDetail(selectedAssignmentId)}><RefreshCw className={assignmentDetailLoading ? "spin" : ""} aria-hidden="true" /> Refresh assignment</Button>
          </div>
          <Alert variant="info" title="Scope-aware record">
            This direct assignment is not a calculation of effective access. Scope, conditions, expiration, and indirect group membership may change where it applies.
          </Alert>
          {assignmentDetailLoading ? <div aria-busy="true"><span className="sr-only">Loading direct role assignment detail.</span><Skeleton lines={5} /></div> : null}
          {assignmentDetailError ? <ErrorState title="Assignment detail unavailable" actionLabel="Try again" onAction={() => void loadAssignmentDetail(selectedAssignmentId)}>{assignmentDetailError}</ErrorState> : null}
          {assignmentDetail?.assignment.assignment_id === selectedAssignmentId ? (
            <div className="admin-assignment-detail-body">
              <div className="admin-role-detail-grid"><div><span>Principal type</span><Badge variant="neutral">{assignmentDetail.assignment.assignee_type}</Badge></div><div><span>Assignment scope</span>{assignmentScope(assignmentDetail.assignment)}</div><div><span>Status</span>{assignmentDetail.assignment.expired ? <Badge variant="warning">Expired</Badge> : <Badge variant="success">Current record</Badge>}</div></div>
              <dl className="admin-assignment-metadata">
                <div><dt>Resolved identity</dt><dd>{principal?.outcome === "verified" ? <><strong>{principal.display_name ?? principal.primary_email}</strong>{principal.display_name && principal.primary_email ? <small>{principal.primary_email}</small> : null}</> : "Identity not authoritatively resolved"}</dd></div>
                <div><dt>Resolution</dt><dd><Badge variant={principal?.outcome === "verified" ? "success" : principal?.outcome === "lookup_unavailable" ? "warning" : "neutral"}>{principal?.outcome.replace(/_/g, " ") ?? "Loading"}</Badge>{principal?.reason ? <small>{principal.reason.replace(/_/g, " ")}</small> : null}</dd></div>
                <div><dt>Account status</dt><dd>{principal?.account_status ? <Badge variant={principal.account_status === "ACTIVE" ? "success" : "warning"}>{principal.account_status}</Badge> : "Not available"}</dd></div>
                <div><dt>Assigned principal ID</dt><dd><code>{assignmentDetail.assignment.assigned_to}</code></dd></div>
                <div><dt>Referenced role</dt><dd>{selectedRole?.name ?? "Role not present in current inventory"} <code>{assignmentDetail.assignment.role_id}</code></dd></div>
                <div><dt>Organizational unit ID</dt><dd>{assignmentDetail.assignment.org_unit_id ? <code>{assignmentDetail.assignment.org_unit_id}</code> : "Not OU-scoped"}</dd></div>
                <div><dt>Condition</dt><dd>{assignmentDetail.assignment.condition ?? "No condition returned"}</dd></div>
                <div><dt>Expiration</dt><dd>{assignmentDetail.assignment.expires_at ? formatExpiration(assignmentDetail.assignment.expires_at) : "No expiration returned"}</dd></div>
              </dl>
            </div>
          ) : null}
        </aside>
      ) : null}
    </section>
  );
}
