import { ExternalLink, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceUserGroupMemberships } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { DataTable, DataTablePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { Badge } from "../../components/ui/Feedback";
import type {
  GoogleWorkspaceUser,
  GoogleWorkspaceUserGroupMembership,
  GoogleWorkspaceUserGroupMembershipResult
} from "../../types";

interface UserGroupMembershipsProps {
  organizationId: string;
  user: GoogleWorkspaceUser;
  onOpenGroup: (groupEmail: string) => void;
}

function membershipsErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Group memberships could not be loaded. Check the connection and try again.";
  }

  const messages: Record<string, string> = {
    google_operation_budget_exceeded:
      "This page exceeded the safe verification limit. Reduce the page size and try again.",
    google_page_token_invalid:
      "This result page expired. Refresh memberships to start again.",
    missing_scope_or_permission:
      "Google denied this request. Verify the read-only Directory group scope and delegated administrator privileges.",
    google_rate_limited: "Google rate-limited this request. Wait a moment and try again.",
    google_timeout: "Google timed out while verifying memberships. Try again shortly.",
    google_network_error: "Google could not be reached. Check the connection and try again.",
    google_service_unavailable: "Google is temporarily unavailable. Try again shortly."
  };
  if (error.code && messages[error.code]) return messages[error.code];
  if (error.status === 403) return "Administrator access is required for this organization.";
  return error.message;
}

export function UserGroupMemberships({
  organizationId,
  user,
  onOpenGroup
}: UserGroupMembershipsProps) {
  const [result, setResult] = useState<GoogleWorkspaceUserGroupMembershipResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pageSize, setPageSize] = useState<10 | 25>(10);
  const [pageTokens, setPageTokens] = useState<Array<string | null>>([null]);
  const [page, setPage] = useState(0);
  const requestSequence = useRef(0);
  const controller = useRef<AbortController | null>(null);

  const loadMemberships = useCallback(
    async (token: string | null, pageIndex: number, requestedPageSize: 10 | 25) => {
      controller.current?.abort();
      const nextController = new AbortController();
      controller.current = nextController;
      const sequence = requestSequence.current + 1;
      requestSequence.current = sequence;
      setIsLoading(true);
      setError(null);

      try {
        const nextResult = await listGoogleWorkspaceUserGroupMemberships(
          organizationId,
          user.primary_email,
          requestedPageSize,
          token,
          nextController.signal
        );
        if (requestSequence.current !== sequence) return;
        setResult(nextResult);
        setPage(pageIndex);
      } catch (loadError) {
        if (nextController.signal.aborted || requestSequence.current !== sequence) return;
        setResult(null);
        setError(membershipsErrorMessage(loadError));
      } finally {
        if (requestSequence.current === sequence) {
          controller.current = null;
          setIsLoading(false);
        }
      }
    },
    [organizationId, user.primary_email]
  );

  useEffect(() => {
    setPageTokens([null]);
    setPage(0);
    setResult(null);
    setError(null);
    void loadMemberships(null, 0, pageSize);
    return () => {
      requestSequence.current += 1;
      controller.current?.abort();
    };
  }, [loadMemberships, pageSize]);

  function nextPage() {
    if (!result?.next_page_token) return;
    const tokens = pageTokens.slice(0, page + 1);
    tokens.push(result.next_page_token);
    setPageTokens(tokens);
    void loadMemberships(result.next_page_token, page + 1, pageSize);
  }

  const columns: DataTableColumn<GoogleWorkspaceUserGroupMembership>[] = [
    { id: "group", header: "Group", cell: (membership) => <span className="group-primary-cell"><strong>{membership.group_name}</strong><span>{membership.group_primary_email}</span></span> },
    { id: "role", header: "Role", cell: (membership) => <Badge variant={membership.role === "OWNER" ? "warning" : membership.role === "MANAGER" ? "info" : "neutral"}>{membership.role}</Badge> },
    { id: "status", header: "Status", cell: (membership) => <Badge variant={membership.status === "ACTIVE" ? "success" : "neutral"}>{membership.status ?? "Unknown"}</Badge> },
    { id: "actions", header: <span className="sr-only">Open group</span>, cell: (membership) => <Button variant="secondary" size="sm" onClick={() => onOpenGroup(membership.group_primary_email)}>Open group <ExternalLink aria-hidden="true" /></Button> }
  ];

  return (
    <section className="user-memberships" aria-labelledby="user-memberships-heading">
      <div className="user-memberships-heading">
        <div>
          <h4 id="user-memberships-heading">Direct group memberships</h4>
          <p>Verified direct memberships in this Workspace customer. External and indirect groups are omitted.</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          loading={isLoading}
          loadingLabel="Refreshing memberships"
          onClick={() => void loadMemberships(pageTokens[page] ?? null, page, pageSize)}
        >
          <RefreshCw aria-hidden="true" /> Refresh
        </Button>
      </div>

      <DataTable ariaLabel={`Direct group memberships for ${user.primary_email}`} columns={columns} rows={result?.memberships ?? []} rowKey={(membership) => membership.group_id} loading={isLoading && !result} error={error} errorTitle="Memberships could not be loaded" onRetry={() => void loadMemberships(pageTokens[page] ?? null, page, pageSize)} emptyTitle="No direct memberships on this page" emptyDescription={result?.next_page_token ? "No verified direct memberships are on this page. Continue to the next page." : "This user has no verified direct group memberships."} minWidth="42rem" className="user-membership-data-table" />

      {result && (result.omitted_external_count > 0 || result.omitted_indirect_count > 0) && (
        <p className="user-membership-note">
          Omitted on this page: {result.omitted_external_count} outside this customer and {result.omitted_indirect_count} indirect or unavailable.
        </p>
      )}

      <DataTablePagination ariaLabel="User group membership pages" page={page} onPrevious={() => void loadMemberships(pageTokens[page - 1] ?? null, page - 1, pageSize)} onNext={nextPage} previousDisabled={page === 0} nextDisabled={!result?.next_page_token} pageSize={pageSize} pageSizeOptions={[{ value: 10 }, { value: 25 }]} onPageSizeChange={(value) => setPageSize(value as 10 | 25)} disabled={isLoading} />
    </section>
  );
}
