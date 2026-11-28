import { AlertCircle, RefreshCw, ShieldCheck, UsersRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { listGoogleWorkspaceUserAdminRoleAssignments } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Alert, Badge, ErrorState, Skeleton } from "../../components/ui/Feedback";
import type {
  GoogleWorkspaceUser,
  GoogleWorkspaceUserRoleAssignment,
  GoogleWorkspaceUserRoleAssignmentInventory
} from "../../types";
import { googleWorkspaceUserLookupError } from "./googleWorkspaceUserPresentation";

interface UserAdminRoleAssignmentsProps {
  organizationId: string;
  user: GoogleWorkspaceUser;
}

function provenanceLabel(value: GoogleWorkspaceUserRoleAssignment["provenance"]): string {
  if (value === "DIRECT") return "Direct assignment";
  if (value === "GROUP_DERIVED") return "Google-reported indirect assignment";
  return "Unknown provenance";
}

function assignmentScope(item: GoogleWorkspaceUserRoleAssignment): string {
  if (item.assignment.scope_type === "CUSTOMER") return "Entire customer";
  if (item.assignment.scope_type === "ORG_UNIT") {
    return item.assignment.org_unit_id
      ? `Organizational unit ${item.assignment.org_unit_id}`
      : "Organizational unit";
  }
  return "Unknown scope";
}

function assignmentStatus(item: GoogleWorkspaceUserRoleAssignment): string {
  if (item.assignment.expired) return "Expired record";
  if (item.assignment.condition) return "Conditional record";
  return "Current record";
}

export function UserAdminRoleAssignments({
  organizationId,
  user
}: UserAdminRoleAssignmentsProps) {
  const [inventory, setInventory] =
    useState<GoogleWorkspaceUserRoleAssignmentInventory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);

  const load = useCallback(async () => {
    const request = ++sequence.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setInventory(null);
    setError(null);
    setLoading(true);
    try {
      const result = await listGoogleWorkspaceUserAdminRoleAssignments(
        organizationId,
        user.id,
        nextController.signal
      );
      if (request !== sequence.current || nextController.signal.aborted) return;
      setInventory(result);
    } catch (caught) {
      if (request !== sequence.current || nextController.signal.aborted) return;
      setError(googleWorkspaceUserLookupError(caught));
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [organizationId, user.id]);

  useEffect(() => {
    sequence.current += 1;
    controller.current?.abort();
    controller.current = null;
    setInventory(null);
    setError(null);
    setLoading(false);
    return () => controller.current?.abort();
  }, [organizationId, user.id]);

  return (
    <section className="user-detail-section user-admin-role-assignments" aria-labelledby="user-admin-roles-heading">
      <div className="user-detail-section-heading user-admin-role-assignments__heading">
        <ShieldCheck aria-hidden="true" />
        <div>
          <h4 id="user-admin-roles-heading">Administrator role assignments</h4>
          <p>On-demand, read-only results for this verified user.</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={loading}
          onClick={() => void load()}
        >
          <RefreshCw className={loading ? "spin" : ""} aria-hidden="true" />
          {inventory || error ? "Refresh assignments" : "Load assignments"}
        </Button>
      </div>

      <Alert variant="info" title="Google-reported assignments only">
        This view shows Google-reported administrator role assignments. It does not calculate
        effective administrator permissions.
      </Alert>

      {loading ? (
        <div aria-busy="true">
          <span className="sr-only">Loading administrator role assignments.</span>
          <Skeleton lines={4} />
        </div>
      ) : null}
      {error ? (
        <ErrorState title="Administrator assignments unavailable" actionLabel="Try again" onAction={() => void load()}>
          {error}
        </ErrorState>
      ) : null}
      {!loading && !error && !inventory ? (
        <div className="user-admin-role-assignments__idle">
          <UsersRound aria-hidden="true" />
          <p>Load assignments when you need to inspect this user. No tenant-wide scan runs automatically.</p>
        </div>
      ) : null}
      {inventory ? (
        <div className="user-admin-role-assignments__results">
          <div className="user-admin-role-assignments__summary" aria-label="Assignment summary">
            <span><strong>{inventory.direct_count}</strong> Direct</span>
            <span><strong>{inventory.group_derived_count}</strong> Google-reported indirect</span>
            <span><strong>{inventory.unknown_count}</strong> Unknown provenance</span>
          </div>
          {inventory.assignments.length === 0 ? (
            <div className="user-admin-role-assignments__empty" role="status">
              <ShieldCheck aria-hidden="true" />
              Google returned no direct or indirect administrator role assignments for this user.
            </div>
          ) : (
            <ul className="user-admin-role-assignments__list">
              {inventory.assignments.map((item) => (
                <li key={item.assignment.assignment_id}>
                  <div className="user-admin-role-assignments__title">
                    <div>
                      <strong>{item.role?.name ?? "Referenced role unavailable"}</strong>
                      <code>{item.assignment.role_id}</code>
                    </div>
                    <Badge
                      variant={
                        item.provenance === "DIRECT"
                          ? "success"
                          : item.provenance === "GROUP_DERIVED"
                            ? "info"
                            : "warning"
                      }
                    >
                      {provenanceLabel(item.provenance)}
                    </Badge>
                  </div>
                  <dl>
                    <div><dt>Scope</dt><dd>{assignmentScope(item)}</dd></div>
                    <div><dt>Status</dt><dd>{assignmentStatus(item)}</dd></div>
                    <div>
                      <dt>Assigned principal</dt>
                      <dd>
                        {item.principal.outcome === "verified"
                          ? item.principal.display_name ?? item.principal.primary_email ?? item.principal.principal_id
                          : "Not authoritatively resolved"}
                        {item.principal.identity_type === "GROUP" ? <small>Verified group</small> : null}
                      </dd>
                    </div>
                    <div><dt>Condition</dt><dd>{item.assignment.condition ?? "No condition returned"}</dd></div>
                    <div>
                      <dt>Expiration</dt>
                      <dd>{item.assignment.expires_at ? new Date(item.assignment.expires_at).toLocaleString() : "No expiration returned"}</dd>
                    </div>
                  </dl>
                  {item.provenance === "UNKNOWN" ? (
                    <p className="user-admin-role-assignments__uncertainty">
                      <AlertCircle aria-hidden="true" />
                      Google returned this record, but its relationship to the selected user could not be classified safely.
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}
