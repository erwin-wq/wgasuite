import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Building2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Filter,
  Loader2,
  RefreshCw,
  RotateCcw,
  Search,
  UsersRound
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceUsers } from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceDirectoryUser,
  GoogleWorkspaceUserDirectoryRequest,
  UserDirectoryAdminFilter,
  UserDirectoryArchivedFilter,
  UserDirectoryOrder,
  UserDirectorySearchField,
  UserDirectorySortDirection,
  UserDirectorySuspendedFilter
} from "../../types";

interface UserDirectoryProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canSearch: boolean;
  onSelectUser: (primaryEmail: string) => void;
}

interface DirectoryFilters {
  search: string;
  searchField: UserDirectorySearchField;
  orgUnitPath: string;
  suspended: UserDirectorySuspendedFilter;
  adminStatus: UserDirectoryAdminFilter;
  archived: UserDirectoryArchivedFilter;
}

const DEFAULT_FILTERS: DirectoryFilters = {
  search: "",
  searchField: "all",
  orgUnitPath: "",
  suspended: "all",
  adminStatus: "all",
  archived: "all"
};

function directoryErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The user directory could not be loaded. Check your connection and try again.";
  }
  if (error.code === "google_page_token_invalid") {
    return "This Directory page expired. Return to the first page and try again.";
  }
  if (error.code === "missing_scope_or_permission" || error.code === "google_forbidden") {
    return "Google denied this request. Verify the delegated administrator and read-only Directory scope.";
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited the directory request. Wait a moment and try again.";
  }
  if (
    error.code === "google_service_unavailable" ||
    error.code === "google_network_error" ||
    error.code === "google_timeout"
  ) {
    return "Google Directory is temporarily unavailable. Try again shortly.";
  }
  if (error.status === 403) return "You do not have permission to browse this user directory.";
  if (error.status === 409) {
    return "The Google Workspace connector is not ready. Complete and test the connection first.";
  }
  return error.message;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Not available";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not available";
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function accountStatus(user: GoogleWorkspaceDirectoryUser): { label: string; className: string } {
  if (user.archived === true) return { label: "Archived", className: "status-neutral" };
  if (user.suspended === true) return { label: "Suspended", className: "status-danger" };
  if (user.suspended === false && user.archived === false) {
    return { label: "Active", className: "status-success" };
  }
  return { label: "Unknown", className: "status-neutral" };
}

function administratorStatus(user: GoogleWorkspaceDirectoryUser): string {
  if (user.is_super_admin === true) return "Super administrator";
  if (user.is_delegated_admin === true) return "Delegated administrator";
  if (user.is_super_admin === false && user.is_delegated_admin === false) return "Standard user";
  return "Unknown";
}

function requestPayload(
  filters: DirectoryFilters,
  orderBy: UserDirectoryOrder,
  sortDirection: UserDirectorySortDirection,
  pageSize: 25 | 50 | 100,
  pageToken: string | null
): GoogleWorkspaceUserDirectoryRequest {
  return {
    search: filters.search.trim(),
    search_field: filters.searchField,
    org_unit_path: filters.orgUnitPath.trim() || null,
    suspended: filters.suspended,
    admin_status: filters.adminStatus,
    archived: filters.archived,
    order_by: orderBy,
    sort_direction: sortDirection,
    page_size: pageSize,
    page_token: pageToken
  };
}

export function UserDirectory({
  organizationId,
  organizationName,
  connectorConfig,
  canSearch,
  onSelectUser
}: UserDirectoryProps) {
  const [draftFilters, setDraftFilters] = useState<DirectoryFilters>({ ...DEFAULT_FILTERS });
  const [appliedFilters, setAppliedFilters] = useState<DirectoryFilters>({ ...DEFAULT_FILTERS });
  const [orderBy, setOrderBy] = useState<UserDirectoryOrder>("email");
  const [sortDirection, setSortDirection] = useState<UserDirectorySortDirection>("ascending");
  const [pageSize, setPageSize] = useState<25 | 50 | 100>(50);
  const [users, setUsers] = useState<GoogleWorkspaceDirectoryUser[]>([]);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [pageTokens, setPageTokens] = useState<Array<string | null>>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestSequence = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const connectorReady = connectorConfig?.status === "connected";

  const loadPage = useCallback(async (
    filters: DirectoryFilters,
    nextOrderBy: UserDirectoryOrder,
    nextSortDirection: UserDirectorySortDirection,
    nextPageSize: 25 | 50 | 100,
    pageToken: string | null,
    nextPageIndex: number
  ) => {
    if (!organizationId || !connectorReady || !canSearch) return;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setUsers([]);
    setError(null);
    setIsLoading(true);
    try {
      const result = await listGoogleWorkspaceUsers(
        organizationId,
        requestPayload(filters, nextOrderBy, nextSortDirection, nextPageSize, pageToken),
        controller.signal
      );
      if (requestSequence.current !== sequence) return;
      setUsers(result.users);
      setNextPageToken(result.next_page_token);
      setPageIndex(nextPageIndex);
    } catch (loadError) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setNextPageToken(null);
      setError(directoryErrorMessage(loadError));
    } finally {
      if (requestSequence.current === sequence) {
        requestController.current = null;
        setIsLoading(false);
      }
    }
  }, [canSearch, connectorReady, organizationId]);

  useEffect(() => {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    const defaults = { ...DEFAULT_FILTERS };
    setDraftFilters(defaults);
    setAppliedFilters(defaults);
    setOrderBy("email");
    setSortDirection("ascending");
    setPageSize(50);
    setUsers([]);
    setNextPageToken(null);
    setPageTokens([null]);
    setPageIndex(0);
    setError(null);
    setIsLoading(false);
    if (organizationId && connectorReady && canSearch) {
      void loadPage(defaults, "email", "ascending", 50, null, 0);
    }
    return () => requestController.current?.abort();
  }, [canSearch, connectorReady, loadPage, organizationId]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextFilters = { ...draftFilters };
    setAppliedFilters(nextFilters);
    setPageTokens([null]);
    void loadPage(nextFilters, orderBy, sortDirection, pageSize, null, 0);
  }

  function resetFilters() {
    const defaults = { ...DEFAULT_FILTERS };
    setDraftFilters(defaults);
    setAppliedFilters(defaults);
    setPageTokens([null]);
    void loadPage(defaults, orderBy, sortDirection, pageSize, null, 0);
  }

  function changeSort(nextOrderBy: UserDirectoryOrder) {
    const nextDirection =
      orderBy === nextOrderBy && sortDirection === "ascending" ? "descending" : "ascending";
    setOrderBy(nextOrderBy);
    setSortDirection(nextDirection);
    setPageTokens([null]);
    void loadPage(appliedFilters, nextOrderBy, nextDirection, pageSize, null, 0);
  }

  function changeOrderBy(nextOrderBy: UserDirectoryOrder) {
    setOrderBy(nextOrderBy);
    setPageTokens([null]);
    void loadPage(appliedFilters, nextOrderBy, sortDirection, pageSize, null, 0);
  }

  function changeSortDirection(nextDirection: UserDirectorySortDirection) {
    setSortDirection(nextDirection);
    setPageTokens([null]);
    void loadPage(appliedFilters, orderBy, nextDirection, pageSize, null, 0);
  }

  function changePageSize(value: string) {
    const nextSize = Number(value) as 25 | 50 | 100;
    setPageSize(nextSize);
    setPageTokens([null]);
    void loadPage(appliedFilters, orderBy, sortDirection, nextSize, null, 0);
  }

  function nextPage() {
    if (!nextPageToken || isLoading) return;
    const tokens = pageTokens.slice(0, pageIndex + 1);
    tokens.push(nextPageToken);
    setPageTokens(tokens);
    void loadPage(
      appliedFilters,
      orderBy,
      sortDirection,
      pageSize,
      nextPageToken,
      pageIndex + 1
    );
  }

  function previousPage() {
    if (pageIndex === 0 || isLoading) return;
    const previousToken = pageTokens[pageIndex - 1] ?? null;
    void loadPage(
      appliedFilters,
      orderBy,
      sortDirection,
      pageSize,
      previousToken,
      pageIndex - 1
    );
  }

  function sortIcon(field: UserDirectoryOrder) {
    if (orderBy !== field) return null;
    return sortDirection === "ascending" ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" />;
  }

  const sortAria = (field: UserDirectoryOrder) =>
    orderBy === field ? sortDirection : "none";

  return (
    <section className="user-directory" aria-labelledby="user-directory-heading">
      <div className="workspace-section-heading directory-heading">
        <div>
          <span className="eyebrow">Read-only Directory</span>
          <h2 id="user-directory-heading">User Directory</h2>
          <p>Browse users across every domain in the verified Workspace customer.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          disabled={isLoading || !connectorReady || !canSearch}
          onClick={() => void loadPage(
            appliedFilters,
            orderBy,
            sortDirection,
            pageSize,
            pageTokens[pageIndex] ?? null,
            pageIndex
          )}
        >
          <RefreshCw className={isLoading ? "spin" : ""} aria-hidden="true" /> Refresh
        </button>
      </div>

      {!organizationId ? (
        <div className="directory-state" role="status"><Building2 aria-hidden="true" />Select an organization to browse users.</div>
      ) : !canSearch ? (
        <div className="directory-state warning" role="status"><AlertCircle aria-hidden="true" />Customer administrator access is required.</div>
      ) : !connectorReady ? (
        <div className="directory-state warning" role="status"><AlertCircle aria-hidden="true" />Connect and successfully test Google Workspace for {organizationName ?? "this organization"} before browsing.</div>
      ) : (
        <>
          <form className="directory-filters" onSubmit={applyFilters}>
            <label className="directory-search-field">
              Search users
              <span className="directory-search-row">
                <Search aria-hidden="true" />
                <input
                  value={draftFilters.search}
                  maxLength={100}
                  onChange={(event) => setDraftFilters((current) => ({ ...current, search: event.target.value }))}
                  placeholder="Name, email or alias"
                />
              </span>
            </label>
            <label>Search field<select value={draftFilters.searchField} onChange={(event) => setDraftFilters((current) => ({ ...current, searchField: event.target.value as UserDirectorySearchField }))}><option value="all">General</option><option value="email">Email or alias</option><option value="given_name">Given name</option><option value="family_name">Family name</option><option value="full_name">Full name</option></select></label>
            <label>Account status<select value={draftFilters.suspended} onChange={(event) => setDraftFilters((current) => ({ ...current, suspended: event.target.value as UserDirectorySuspendedFilter }))}><option value="all">All accounts</option><option value="active">Active</option><option value="suspended">Suspended</option></select></label>
            <label>Administrator<select value={draftFilters.adminStatus} onChange={(event) => setDraftFilters((current) => ({ ...current, adminStatus: event.target.value as UserDirectoryAdminFilter }))}><option value="all">All roles</option><option value="super_admin">Super administrators</option><option value="delegated_admin">Delegated administrators</option></select></label>
            <label>Archive status<select value={draftFilters.archived} onChange={(event) => setDraftFilters((current) => ({ ...current, archived: event.target.value as UserDirectoryArchivedFilter }))}><option value="all">All archive states</option><option value="not_archived">Not archived</option><option value="archived">Archived</option></select></label>
            <label className="directory-ou-field">Organizational unit path<input value={draftFilters.orgUnitPath} maxLength={1000} onChange={(event) => setDraftFilters((current) => ({ ...current, orgUnitPath: event.target.value }))} placeholder="/Engineering" /><small>Includes users in descendant organizational units.</small></label>
            <div className="directory-filter-actions"><button type="submit" disabled={isLoading}><Filter aria-hidden="true" /> Apply</button><button type="button" className="secondary-button" disabled={isLoading} onClick={resetFilters}><RotateCcw aria-hidden="true" /> Reset</button></div>
          </form>

          <div className="directory-toolbar">
            <span>Page {pageIndex + 1} · Google does not provide a total count</span>
            <div className="directory-sort-controls">
              <label>Sort by<select value={orderBy} onChange={(event) => changeOrderBy(event.target.value as UserDirectoryOrder)} disabled={isLoading}><option value="email">Primary email</option><option value="given_name">Given name</option><option value="family_name">Family name</option></select></label>
              <label>Direction<select value={sortDirection} onChange={(event) => changeSortDirection(event.target.value as UserDirectorySortDirection)} disabled={isLoading}><option value="ascending">Ascending</option><option value="descending">Descending</option></select></label>
              <label>Rows per page<select value={pageSize} onChange={(event) => changePageSize(event.target.value)} disabled={isLoading}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label>
            </div>
          </div>

          {error ? (
            <div className="directory-state error" role="alert"><AlertCircle aria-hidden="true" /><span>{error}</span>{pageIndex > 0 && <button type="button" className="secondary-button" onClick={() => { setPageTokens([null]); void loadPage(appliedFilters, orderBy, sortDirection, pageSize, null, 0); }}>Return to first page</button>}</div>
          ) : isLoading ? (
            <div className="directory-state" role="status"><Loader2 className="spin" aria-hidden="true" />Loading Directory users…</div>
          ) : users.length === 0 ? (
            <div className="directory-state" role="status"><UsersRound aria-hidden="true" />No users were returned for this page and filter set.</div>
          ) : (
            <div className="directory-table-wrap">
              <table className="directory-table">
                <thead><tr><th aria-sort={sortAria("given_name")}><button type="button" onClick={() => changeSort("given_name")}>User {sortIcon("given_name")}</button></th><th aria-sort={sortAria("email")}><button type="button" onClick={() => changeSort("email")}>Primary email {sortIcon("email")}</button></th><th>Organizational unit</th><th>Account</th><th>Administrator</th><th>Created</th><th>Last sign-in</th><th><span className="sr-only">Details</span></th></tr></thead>
                <tbody>{users.map((user) => { const status = accountStatus(user); return <tr key={user.id}><td><strong>{user.full_name ?? "Name unavailable"}</strong><span>{[user.given_name, user.family_name].filter(Boolean).join(" ") || "Name parts unavailable"}</span></td><td>{user.primary_email}</td><td>{user.org_unit_path ?? "Not available"}</td><td><span className={status.className}>{status.label}</span></td><td>{administratorStatus(user)}</td><td>{formatTimestamp(user.creation_time)}</td><td>{formatTimestamp(user.last_login_time)}</td><td><button type="button" className="secondary-button" onClick={() => onSelectUser(user.primary_email)}>Open details <ExternalLink aria-hidden="true" /></button></td></tr>; })}</tbody>
              </table>
            </div>
          )}

          <div className="pagination-controls" aria-label="User directory pages"><button type="button" className="secondary-button" disabled={pageIndex === 0 || isLoading} onClick={previousPage}><ChevronLeft aria-hidden="true" /> Previous</button><span>Page {pageIndex + 1}</span><button type="button" className="secondary-button" disabled={!nextPageToken || isLoading} onClick={nextPage}>Next <ChevronRight aria-hidden="true" /></button></div>
        </>
      )}
    </section>
  );
}
