import {
  AlertCircle,
  Building2,
  ExternalLink,
  Filter,
  RefreshCw,
  RotateCcw
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceUsers } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { DataTable, DataTablePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { Badge } from "../../components/ui/Feedback";
import { Input, SearchField, Select } from "../../components/ui/FormControls";
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

function accountStatus(user: GoogleWorkspaceDirectoryUser): { label: string; variant: "neutral" | "success" | "danger" } {
  if (user.archived === true) return { label: "Archived", variant: "neutral" };
  if (user.suspended === true) return { label: "Suspended", variant: "danger" };
  if (user.suspended === false && user.archived === false) {
    return { label: "Active", variant: "success" };
  }
  return { label: "Unknown", variant: "neutral" };
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

  const columns: DataTableColumn<GoogleWorkspaceDirectoryUser>[] = [
    {
      id: "user",
      header: "User",
      sortDirection: orderBy === "given_name" ? sortDirection : "none",
      onSort: () => changeSort("given_name"),
      cell: (user) => (
        <span className="directory-user-cell">
          <strong>{user.full_name ?? "Name unavailable"}</strong>
          <span>{[user.given_name, user.family_name].filter(Boolean).join(" ") || "Name parts unavailable"}</span>
        </span>
      )
    },
    {
      id: "email",
      header: "Primary email",
      sortDirection: orderBy === "email" ? sortDirection : "none",
      onSort: () => changeSort("email"),
      cell: (user) => <span className="directory-long-value">{user.primary_email}</span>
    },
    { id: "ou", header: "Organizational unit", cell: (user) => <span className="directory-long-value">{user.org_unit_path ?? "Not available"}</span> },
    { id: "account", header: "Account", cell: (user) => { const status = accountStatus(user); return <Badge variant={status.variant}>{status.label}</Badge>; } },
    { id: "admin", header: "Administrator", cell: administratorStatus },
    { id: "created", header: "Created", cell: (user) => formatTimestamp(user.creation_time) },
    { id: "last-sign-in", header: "Last sign-in", cell: (user) => formatTimestamp(user.last_login_time) },
    {
      id: "actions",
      header: <span className="sr-only">Details</span>,
      cell: (user) => (
        <Button variant="secondary" size="sm" onClick={() => onSelectUser(user.primary_email)}>
          Open details <ExternalLink aria-hidden="true" />
        </Button>
      )
    }
  ];

  return (
    <section className="user-directory" aria-labelledby="user-directory-heading">
      <h2 id="user-directory-heading" className="sr-only">Directory users</h2>

      {!organizationId ? (
        <div className="directory-state" role="status"><Building2 aria-hidden="true" />Select an organization to browse users.</div>
      ) : !canSearch ? (
        <div className="directory-state warning" role="status"><AlertCircle aria-hidden="true" />Customer administrator access is required.</div>
      ) : !connectorReady ? (
        <div className="directory-state warning" role="status"><AlertCircle aria-hidden="true" />Connect and successfully test Google Workspace for {organizationName ?? "this organization"} before browsing.</div>
      ) : (
        <>
          <form className="directory-filters" onSubmit={applyFilters}>
            <SearchField className="directory-search-field" label="Search users" value={draftFilters.search} maxLength={100} onChange={(event) => setDraftFilters((current) => ({ ...current, search: event.target.value }))} onClear={() => setDraftFilters((current) => ({ ...current, search: "" }))} placeholder="Name, email or alias" />
            <Select label="Search field" value={draftFilters.searchField} onChange={(event) => setDraftFilters((current) => ({ ...current, searchField: event.target.value as UserDirectorySearchField }))} options={[{ value: "all", label: "General" }, { value: "email", label: "Email or alias" }, { value: "given_name", label: "Given name" }, { value: "family_name", label: "Family name" }, { value: "full_name", label: "Full name" }]} />
            <Select label="Account status" value={draftFilters.suspended} onChange={(event) => setDraftFilters((current) => ({ ...current, suspended: event.target.value as UserDirectorySuspendedFilter }))} options={[{ value: "all", label: "All accounts" }, { value: "active", label: "Active" }, { value: "suspended", label: "Suspended" }]} />
            <Select label="Administrator" value={draftFilters.adminStatus} onChange={(event) => setDraftFilters((current) => ({ ...current, adminStatus: event.target.value as UserDirectoryAdminFilter }))} options={[{ value: "all", label: "All roles" }, { value: "super_admin", label: "Super administrators" }, { value: "delegated_admin", label: "Delegated administrators" }]} />
            <Select label="Archive status" value={draftFilters.archived} onChange={(event) => setDraftFilters((current) => ({ ...current, archived: event.target.value as UserDirectoryArchivedFilter }))} options={[{ value: "all", label: "All archive states" }, { value: "not_archived", label: "Not archived" }, { value: "archived", label: "Archived" }]} />
            <Input className="directory-ou-field" label="Organizational unit path" hint="Includes users in descendant organizational units." value={draftFilters.orgUnitPath} maxLength={1000} onChange={(event) => setDraftFilters((current) => ({ ...current, orgUnitPath: event.target.value }))} placeholder="/Engineering" />
            <div className="directory-filter-actions"><Button type="submit" loading={isLoading} loadingLabel="Applying filters"><Filter aria-hidden="true" /> Apply</Button><Button type="button" variant="secondary" disabled={isLoading} onClick={resetFilters}><RotateCcw aria-hidden="true" /> Reset</Button></div>
          </form>

          <div className="directory-toolbar">
            <span>Page {pageIndex + 1} · Google does not provide a total count</span>
            <div className="directory-sort-controls">
              <Select label="Sort by" hideLabel aria-label="Sort by" value={orderBy} onChange={(event) => changeOrderBy(event.target.value as UserDirectoryOrder)} disabled={isLoading} options={[{ value: "email", label: "Primary email" }, { value: "given_name", label: "Given name" }, { value: "family_name", label: "Family name" }]} />
              <Select label="Direction" hideLabel aria-label="Direction" value={sortDirection} onChange={(event) => changeSortDirection(event.target.value as UserDirectorySortDirection)} disabled={isLoading} options={[{ value: "ascending", label: "Ascending" }, { value: "descending", label: "Descending" }]} />
              <Button
                variant="secondary"
                size="sm"
                loading={isLoading}
                loadingLabel="Refreshing users"
                onClick={() => void loadPage(
                  appliedFilters,
                  orderBy,
                  sortDirection,
                  pageSize,
                  pageTokens[pageIndex] ?? null,
                  pageIndex
                )}
              ><RefreshCw aria-hidden="true" /> Refresh</Button>
            </div>
          </div>

          <DataTable ariaLabel="Workspace directory users" columns={columns} rows={users} rowKey={(user) => user.id} loading={isLoading} error={error} onRetry={() => { if (pageIndex > 0) { setPageTokens([null]); void loadPage(appliedFilters, orderBy, sortDirection, pageSize, null, 0); } else { void loadPage(appliedFilters, orderBy, sortDirection, pageSize, pageTokens[pageIndex] ?? null, pageIndex); } }} errorActionLabel={pageIndex > 0 ? "Return to first page" : "Try again"} emptyTitle="No users on this page" emptyDescription="No users were returned for this page and filter set." minWidth="80rem" stickyLastColumn className="directory-data-table" />

          <DataTablePagination ariaLabel="User directory pages" page={pageIndex} onPrevious={previousPage} onNext={nextPage} previousDisabled={pageIndex === 0} nextDisabled={!nextPageToken} pageSize={pageSize} pageSizeOptions={[{ value: 25 }, { value: 50 }, { value: 100 }]} onPageSizeChange={(value) => changePageSize(String(value))} disabled={isLoading} />
        </>
      )}
    </section>
  );
}
