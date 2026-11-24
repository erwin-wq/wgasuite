import {
  AlertCircle,
  Building2,
  CheckCircle2,
  CircleHelp,
  Eye,
  Globe2,
  Link2,
  RefreshCw,
  ShieldCheck,
  X
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  getGoogleWorkspaceDomain,
  getGoogleWorkspaceDomainAlias,
  listGoogleWorkspaceDomains
} from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Badge, EmptyState, ErrorState, Skeleton } from "../../components/ui/Feedback";
import { SearchField } from "../../components/ui/FormControls";
import type {
  ConnectorConfig,
  GoogleWorkspaceDomain,
  GoogleWorkspaceDomainAlias,
  GoogleWorkspaceDomainAliasDetail,
  GoogleWorkspaceDomainDetail
} from "../../types";
import { DIRECTORY_DOMAIN_READONLY_SCOPE } from "./scopes";

type InventoryRow =
  | (GoogleWorkspaceDomain & { parent_domain: null })
  | GoogleWorkspaceDomainAlias;

type DetailSelection = { kind: "domain" | "alias"; name: string };
type DetailResult =
  | { kind: "domain"; value: GoogleWorkspaceDomainDetail }
  | { kind: "alias"; value: GoogleWorkspaceDomainAliasDetail };

interface DomainsInventoryProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canRead: boolean;
}

function domainsErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The domain inventory could not be loaded. Check the connection and try again.";
  }
  if (
    error.code === "missing_scope_or_permission" ||
    error.code === "delegation_rejected" ||
    error.code === "google_forbidden"
  ) {
    return `Google denied domain access. Authorize ${DIRECTORY_DOMAIN_READONLY_SCOPE} for this connector's Domain-Wide Delegation client and verify the delegated administrator can read domains.`;
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited the domain request. Wait a moment and try again.";
  }
  if (
    error.code === "google_service_unavailable" ||
    error.code === "google_network_error" ||
    error.code === "google_timeout"
  ) {
    return "Google Directory is temporarily unavailable. Try again shortly.";
  }
  if (error.status === 403) {
    return "You do not have permission to view domains for this customer.";
  }
  if (error.status === 409) {
    return "The Google Workspace connector is not ready. Complete and test the connection first.";
  }
  return error.message;
}

function domainDetailErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (
      error.code === "google_domain_not_found" ||
      error.code === "google_domain_alias_not_found"
    ) {
      return "Google no longer returns this exact domain resource. Refresh the inventory.";
    }
    if (error.code === "google_domain_name_invalid") {
      return "The selected domain name is invalid. Refresh the inventory before trying again.";
    }
  }
  return domainsErrorMessage(error);
}

function verificationBadge(value: boolean | null) {
  if (value === true) {
    return <Badge variant="success" icon={<CheckCircle2 aria-hidden="true" />}>Verified</Badge>;
  }
  if (value === false) {
    return <Badge variant="warning" icon={<AlertCircle aria-hidden="true" />}>Not verified</Badge>;
  }
  return <Badge variant="neutral" icon={<CircleHelp aria-hidden="true" />}>Unknown</Badge>;
}

function kindBadge(kind: InventoryRow["kind"]) {
  if (kind === "primary") return <Badge variant="info">Primary domain</Badge>;
  if (kind === "secondary") return <Badge variant="neutral">Secondary domain</Badge>;
  if (kind === "alias") return <Badge variant="neutral" icon={<Link2 aria-hidden="true" />}>Alias</Badge>;
  return <Badge variant="neutral">Domain</Badge>;
}

function formatCreationTime(value: number | null): string {
  if (value === null) return "Unavailable";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

const columns: readonly DataTableColumn<InventoryRow>[] = [
  {
    id: "name",
    header: "Domain",
    cell: (row) => <strong className="domain-name">{row.name}</strong>
  },
  { id: "type", header: "Classification", cell: (row) => kindBadge(row.kind) },
  {
    id: "parent",
    header: "Parent domain",
    cell: (row) => row.kind === "alias" ? row.parent_domain : <span className="domain-muted">Not applicable</span>
  },
  { id: "verification", header: "Verification", cell: (row) => verificationBadge(row.verified) },
  { id: "created", header: "Created", cell: (row) => formatCreationTime(row.creation_time) }
];

interface DomainDetailPanelProps {
  selection: DetailSelection | null;
  result: DetailResult | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
}

function DomainDetailPanel({
  selection,
  result,
  loading,
  error,
  onRetry,
  onClose
}: DomainDetailPanelProps) {
  if (!selection) {
    return (
      <aside className="domain-detail-panel" aria-label="Domain details">
        <EmptyState title="Select a domain or alias" icon={<Eye aria-hidden="true" />}>
          Use a View details action to inspect authoritative read-only metadata.
        </EmptyState>
      </aside>
    );
  }
  if (loading) {
    return (
      <aside className="domain-detail-panel" aria-label="Domain details" aria-busy="true">
        <span className="sr-only">Loading details for {selection.name}.</span>
        <Skeleton lines={5} />
      </aside>
    );
  }
  if (error) {
    return (
      <aside className="domain-detail-panel" aria-label="Domain details">
        <ErrorState title="Domain details unavailable" actionLabel="Try again" onAction={onRetry}>
          {error}
        </ErrorState>
        <Button variant="ghost" size="sm" onClick={onClose}><X aria-hidden="true" /> Close</Button>
      </aside>
    );
  }
  if (!result) return null;

  const resource = result.kind === "domain" ? result.value.domain : result.value.alias;
  const aliases = result.kind === "domain" ? result.value.aliases : [];
  return (
    <aside className="domain-detail-panel" aria-labelledby="domain-detail-heading">
      <div className="domain-detail-heading">
        <div>
          <span className="eyebrow">Read-only detail</span>
          <h3 id="domain-detail-heading">{resource.name}</h3>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}><X aria-hidden="true" /> Close</Button>
      </div>
      <dl className="domain-detail-list">
        <div><dt>Classification</dt><dd>{kindBadge(resource.kind)}</dd></div>
        <div><dt>Verification</dt><dd>{verificationBadge(resource.verified)}</dd></div>
        <div><dt>Created</dt><dd>{formatCreationTime(resource.creation_time)}</dd></div>
        {result.kind === "alias" ? (
          <div><dt>Parent domain</dt><dd className="domain-name">{result.value.alias.parent_domain}</dd></div>
        ) : null}
      </dl>
      {result.kind === "domain" ? (
        <section className="domain-related-aliases" aria-labelledby="related-aliases-heading">
          <h4 id="related-aliases-heading">Associated aliases</h4>
          {aliases.length ? (
            <ul>{aliases.map((alias) => <li key={alias.name}><Link2 aria-hidden="true" /><span>{alias.name}</span>{verificationBadge(alias.verified)}</li>)}</ul>
          ) : <p>No aliases were returned for this domain.</p>}
        </section>
      ) : null}
      <Button variant="secondary" size="sm" onClick={onRetry}><RefreshCw aria-hidden="true" /> Refresh details</Button>
    </aside>
  );
}

export function DomainsInventory({
  organizationId,
  organizationName,
  connectorConfig,
  canRead
}: DomainsInventoryProps) {
  const [domains, setDomains] = useState<GoogleWorkspaceDomain[]>([]);
  const [aliases, setAliases] = useState<GoogleWorkspaceDomainAlias[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [detailSelection, setDetailSelection] = useState<DetailSelection | null>(null);
  const [detailResult, setDetailResult] = useState<DetailResult | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const deferredSearch = useDeferredValue(search.trim().toLocaleLowerCase());
  const requestSequence = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const detailRequestSequence = useRef(0);
  const detailRequestController = useRef<AbortController | null>(null);
  const connectorReady = connectorConfig?.status === "connected";

  const loadInventory = useCallback(async () => {
    if (!organizationId || !connectorReady || !canRead) return;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setIsLoading(true);
    setError(null);
    try {
      const result = await listGoogleWorkspaceDomains(organizationId, controller.signal);
      if (requestSequence.current !== sequence) return;
      setDomains(result.domains);
      setAliases(result.aliases);
    } catch (loadError) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setDomains([]);
      setAliases([]);
      setError(domainsErrorMessage(loadError));
    } finally {
      if (requestSequence.current === sequence) {
        requestController.current = null;
        setIsLoading(false);
      }
    }
  }, [canRead, connectorReady, organizationId]);

  const loadDetail = useCallback(async (selection: DetailSelection) => {
    if (!organizationId || !connectorReady || !canRead) return;
    detailRequestController.current?.abort();
    const controller = new AbortController();
    detailRequestController.current = controller;
    const sequence = detailRequestSequence.current + 1;
    detailRequestSequence.current = sequence;
    setDetailSelection(selection);
    setDetailResult(null);
    setDetailError(null);
    setIsDetailLoading(true);
    try {
      const value = selection.kind === "alias"
        ? await getGoogleWorkspaceDomainAlias(organizationId, selection.name, controller.signal)
        : await getGoogleWorkspaceDomain(organizationId, selection.name, controller.signal);
      if (detailRequestSequence.current !== sequence) return;
      setDetailResult({ kind: selection.kind, value } as DetailResult);
    } catch (loadError) {
      if (controller.signal.aborted || detailRequestSequence.current !== sequence) return;
      setDetailError(domainDetailErrorMessage(loadError));
    } finally {
      if (detailRequestSequence.current === sequence) {
        detailRequestController.current = null;
        setIsDetailLoading(false);
      }
    }
  }, [canRead, connectorReady, organizationId]);

  const closeDetail = useCallback(() => {
    detailRequestSequence.current += 1;
    detailRequestController.current?.abort();
    detailRequestController.current = null;
    setDetailSelection(null);
    setDetailResult(null);
    setDetailError(null);
    setIsDetailLoading(false);
  }, []);

  useEffect(() => {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setDomains([]);
    setAliases([]);
    setSearch("");
    setError(null);
    setIsLoading(false);
    closeDetail();
    if (organizationId && connectorReady && canRead) void loadInventory();
    return () => requestController.current?.abort();
  }, [canRead, closeDetail, connectorReady, loadInventory, organizationId]);

  const rows = useMemo<InventoryRow[]>(
    () => [
      ...domains.map((domain) => ({ ...domain, parent_domain: null } as const)),
      ...aliases
    ],
    [aliases, domains]
  );
  const filteredRows = useMemo(() => {
    if (!deferredSearch) return rows;
    return rows.filter((row) =>
      [row.name, row.kind, row.kind === "alias" ? row.parent_domain : ""]
        .some((value) => value.toLocaleLowerCase().includes(deferredSearch))
    );
  }, [deferredSearch, rows]);
  const primaryCount = domains.filter((domain) => domain.kind === "primary").length;
  const detailColumns = useMemo<readonly DataTableColumn<InventoryRow>[]>(() => [
    ...columns,
    {
      id: "actions",
      header: "Details",
      cell: (row) => {
        const kind = row.kind === "alias" ? "alias" : "domain";
        const selected = detailSelection?.kind === kind &&
          detailSelection.name.toLocaleLowerCase() === row.name.toLocaleLowerCase();
        return (
          <Button
            variant="secondary"
            size="sm"
            aria-label={`View details for ${row.name}`}
            aria-pressed={selected}
            onClick={() => void loadDetail({ kind, name: row.name })}
          >
            <Eye aria-hidden="true" /> {selected ? "Selected" : "View"}
          </Button>
        );
      }
    }
  ], [detailSelection, loadDetail]);

  if (!organizationId) {
    return <EmptyState title="Select an organization" icon={<Building2 aria-hidden="true" />}>Choose an organization from the workspace selector to view its domains.</EmptyState>;
  }
  if (!canRead) {
    return <EmptyState title="Access unavailable" icon={<AlertCircle aria-hidden="true" />}>Connector-operation access is required to view this inventory.</EmptyState>;
  }
  if (!connectorReady) {
    return <EmptyState title="Connect Google Workspace" icon={<Globe2 aria-hidden="true" />}>Connect and successfully test Google Workspace for {organizationName ?? "this organization"} before loading domains.</EmptyState>;
  }

  return (
    <section className="domains-inventory" aria-labelledby="domains-inventory-heading">
      <div className="workspace-section-heading domains-heading">
        <div>
          <h2 id="domains-inventory-heading">Tenant domain inventory</h2>
          <p>Authoritative read-only domains and aliases from Google Directory.</p>
        </div>
        <Button variant="secondary" disabled={isLoading} onClick={() => void loadInventory()}>
          <RefreshCw className={isLoading ? "spin" : ""} aria-hidden="true" /> Refresh
        </Button>
      </div>

      <div className="domain-summary" aria-label="Domain inventory summary">
        <Card padding="sm"><Globe2 aria-hidden="true" /><span><strong>{domains.length}</strong> Domains</span></Card>
        <Card padding="sm"><Link2 aria-hidden="true" /><span><strong>{aliases.length}</strong> Aliases</span></Card>
        <Card padding="sm"><ShieldCheck aria-hidden="true" /><span><strong>{primaryCount}</strong> Primary</span></Card>
      </div>

      <SearchField
        className="domains-search"
        label="Search domains and aliases"
        placeholder="Search by domain, alias, parent, or classification"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        onClear={() => setSearch("")}
      />

      <DataTable
        ariaLabel="Google Workspace domains and aliases"
        columns={detailColumns}
        rows={filteredRows}
        rowKey={(row) => `${row.kind}:${row.name.toLocaleLowerCase()}`}
        loading={isLoading && rows.length === 0}
        error={error}
        errorTitle="Domain inventory unavailable"
        onRetry={() => void loadInventory()}
        emptyTitle={search ? "No matching domains" : "No domains returned"}
        emptyDescription={search ? "Try a different search term." : "Google returned an empty domain inventory for this customer."}
        minWidth="48rem"
        className="domains-data-table"
      />
      <DomainDetailPanel
        selection={detailSelection}
        result={detailResult}
        loading={isDetailLoading}
        error={detailError}
        onRetry={() => detailSelection ? void loadDetail(detailSelection) : undefined}
        onClose={closeDetail}
      />
    </section>
  );
}
