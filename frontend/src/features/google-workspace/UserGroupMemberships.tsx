import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  RefreshCw,
  UsersRound
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceUserGroupMemberships } from "../../api/client";
import type {
  GoogleWorkspaceUser,
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

  return (
    <section className="user-memberships" aria-labelledby="user-memberships-heading">
      <div className="user-memberships-heading">
        <div>
          <h4 id="user-memberships-heading">Direct group memberships</h4>
          <p>Verified direct memberships in this Workspace customer. External and indirect groups are omitted.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          disabled={isLoading}
          onClick={() => void loadMemberships(pageTokens[page] ?? null, page, pageSize)}
        >
          <RefreshCw className={isLoading ? "spin" : ""} aria-hidden="true" /> Refresh
        </button>
      </div>

      {error ? (
        <div className="user-membership-state error" role="alert">
          <AlertCircle aria-hidden="true" /> {error}
        </div>
      ) : isLoading && !result ? (
        <div className="user-membership-state" role="status">
          <Loader2 className="spin" aria-hidden="true" /> Loading direct memberships…
        </div>
      ) : result && result.memberships.length > 0 ? (
        <div className="user-membership-table-wrap">
          <table className="user-membership-table">
            <thead>
              <tr><th>Group</th><th>Role</th><th>Status</th><th><span className="sr-only">Open</span></th></tr>
            </thead>
            <tbody>
              {result.memberships.map((membership) => (
                <tr key={membership.group_id}>
                  <td><strong>{membership.group_name}</strong><span>{membership.group_primary_email}</span></td>
                  <td>{membership.role}</td>
                  <td>{membership.status ?? "Unknown"}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => onOpenGroup(membership.group_primary_email)}
                    >
                      Open group <ExternalLink aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : result ? (
        <div className="user-membership-state" role="status">
          <UsersRound aria-hidden="true" />
          {result.next_page_token
            ? "No verified direct memberships are on this page. Continue to the next page."
            : "This user has no verified direct group memberships."}
        </div>
      ) : null}

      {result && (result.omitted_external_count > 0 || result.omitted_indirect_count > 0) && (
        <p className="user-membership-note">
          Omitted on this page: {result.omitted_external_count} outside this customer and {result.omitted_indirect_count} indirect or unavailable.
        </p>
      )}

      <div className="user-membership-controls" aria-label="User group membership pages">
        <label>
          Rows
          <select
            value={pageSize}
            disabled={isLoading}
            onChange={(event) => setPageSize(Number(event.target.value) as 10 | 25)}
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
          </select>
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={page === 0 || isLoading}
          onClick={() => void loadMemberships(pageTokens[page - 1] ?? null, page - 1, pageSize)}
        >
          <ChevronLeft aria-hidden="true" /> Previous
        </button>
        <span>Page {page + 1}</span>
        <button
          type="button"
          className="secondary-button"
          disabled={!result?.next_page_token || isLoading}
          onClick={nextPage}
        >
          Next <ChevronRight aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
