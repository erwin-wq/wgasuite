import {
  AlertCircle,
  Building2,
  ChevronDown,
  ChevronRight,
  FolderTree,
  Loader2,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import { CSSProperties, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceOrganizationalUnits } from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceOrganizationalUnitTreeNode
} from "../../types";
import { DIRECTORY_ORGUNIT_READONLY_SCOPE } from "./scopes";

export { DIRECTORY_ORGUNIT_READONLY_SCOPE } from "./scopes";

interface OrganizationalUnitsProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canRead: boolean;
}

interface VisibleUnit {
  unit: GoogleWorkspaceOrganizationalUnitTreeNode;
  depth: number;
}

function organizationalUnitErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The organizational-unit hierarchy could not be loaded. Check the connection and try again.";
  }
  if (
    error.code === "missing_scope_or_permission" ||
    error.code === "delegation_rejected" ||
    error.code === "google_forbidden"
  ) {
    return `Google denied Organizational Units access. In Google Admin, authorize ${DIRECTORY_ORGUNIT_READONLY_SCOPE} for this connector's Domain-Wide Delegation client, then verify the delegated administrator can read organizational units.`;
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited the Organizational Units request. Wait a moment and try again.";
  }
  if (
    error.code === "google_service_unavailable" ||
    error.code === "google_network_error" ||
    error.code === "google_timeout"
  ) {
    return "Google Directory is temporarily unavailable. Try again shortly.";
  }
  if (error.code === "google_orgunit_hierarchy_invalid") {
    return "Google returned an organizational-unit hierarchy that WGASuite could not represent safely.";
  }
  if (error.status === 403) {
    return "You do not have permission to browse Organizational Units for this customer.";
  }
  if (error.status === 409) {
    return "The Google Workspace connector is not ready. Complete and test the connection first.";
  }
  return error.message;
}

function findUnit(
  roots: GoogleWorkspaceOrganizationalUnitTreeNode[],
  id: string | null
): GoogleWorkspaceOrganizationalUnitTreeNode | null {
  if (!id) return null;
  const pending = [...roots];
  while (pending.length > 0) {
    const unit = pending.shift();
    if (!unit) break;
    if (unit.id === id) return unit;
    pending.unshift(...unit.children);
  }
  return null;
}

function flattenVisible(
  roots: GoogleWorkspaceOrganizationalUnitTreeNode[],
  expanded: Set<string>
): VisibleUnit[] {
  const visible: VisibleUnit[] = [];
  function visit(unit: GoogleWorkspaceOrganizationalUnitTreeNode, depth: number) {
    visible.push({ unit, depth });
    if (expanded.has(unit.id)) {
      unit.children.forEach((child) => visit(child, depth + 1));
    }
  }
  roots.forEach((root) => visit(root, 1));
  return visible;
}

export function OrganizationalUnits({
  organizationId,
  organizationName,
  connectorConfig,
  canRead
}: OrganizationalUnitsProps) {
  const [roots, setRoots] = useState<GoogleWorkspaceOrganizationalUnitTreeNode[]>([]);
  const [total, setTotal] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestSequence = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const itemRefs = useRef(new Map<string, HTMLButtonElement>());
  const connectorReady = connectorConfig?.status === "connected";

  const loadHierarchy = useCallback(async () => {
    if (!organizationId || !connectorReady || !canRead) return;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setIsLoading(true);
    setError(null);
    try {
      const result = await listGoogleWorkspaceOrganizationalUnits(
        organizationId,
        controller.signal
      );
      if (requestSequence.current !== sequence) return;
      setRoots(result.roots);
      setTotal(result.total);
      const rootIds = new Set(result.roots.map((root) => root.id));
      setExpanded(rootIds);
      setSelectedId(result.roots[0]?.id ?? null);
    } catch (loadError) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setRoots([]);
      setTotal(0);
      setSelectedId(null);
      setExpanded(new Set());
      setError(organizationalUnitErrorMessage(loadError));
    } finally {
      if (requestSequence.current === sequence) {
        requestController.current = null;
        setIsLoading(false);
      }
    }
  }, [canRead, connectorReady, organizationId]);

  useEffect(() => {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    itemRefs.current.clear();
    setRoots([]);
    setTotal(0);
    setExpanded(new Set());
    setSelectedId(null);
    setError(null);
    setIsLoading(false);
    if (organizationId && connectorReady && canRead) void loadHierarchy();
    return () => requestController.current?.abort();
  }, [canRead, connectorReady, loadHierarchy, organizationId]);

  const visibleUnits = useMemo(() => flattenVisible(roots, expanded), [expanded, roots]);
  const selectedUnit = useMemo(() => findUnit(roots, selectedId), [roots, selectedId]);

  function toggle(unit: GoogleWorkspaceOrganizationalUnitTreeNode) {
    if (unit.children.length === 0) return;
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(unit.id)) {
        next.delete(unit.id);
        setSelectedId(unit.id);
      } else {
        next.add(unit.id);
      }
      return next;
    });
  }

  function selectAndFocus(id: string) {
    setSelectedId(id);
    window.requestAnimationFrame(() => itemRefs.current.get(id)?.focus());
  }

  function handleTreeKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    unit: GoogleWorkspaceOrganizationalUnitTreeNode
  ) {
    const index = visibleUnits.findIndex((item) => item.unit.id === unit.id);
    if (index < 0) return;
    if (event.key === "ArrowDown" && index < visibleUnits.length - 1) {
      event.preventDefault();
      selectAndFocus(visibleUnits[index + 1].unit.id);
    } else if (event.key === "ArrowUp" && index > 0) {
      event.preventDefault();
      selectAndFocus(visibleUnits[index - 1].unit.id);
    } else if (event.key === "Home" && visibleUnits.length > 0) {
      event.preventDefault();
      selectAndFocus(visibleUnits[0].unit.id);
    } else if (event.key === "End" && visibleUnits.length > 0) {
      event.preventDefault();
      selectAndFocus(visibleUnits[visibleUnits.length - 1].unit.id);
    } else if (event.key === "ArrowRight" && unit.children.length > 0) {
      event.preventDefault();
      if (!expanded.has(unit.id)) toggle(unit);
      else selectAndFocus(unit.children[0].id);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (expanded.has(unit.id) && unit.children.length > 0) toggle(unit);
      else if (unit.parent_id) selectAndFocus(unit.parent_id);
    }
  }

  return (
    <section className="organizational-units" aria-labelledby="organizational-units-heading">
      <div className="workspace-section-heading ou-heading">
        <div>
          <span className="eyebrow">Read-only Directory</span>
          <h2 id="organizational-units-heading">Organizational Units</h2>
          <p>Inspect the complete hierarchy for the verified Workspace customer.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          disabled={isLoading || !connectorReady || !canRead}
          onClick={() => void loadHierarchy()}
        >
          <RefreshCw className={isLoading ? "spin" : ""} aria-hidden="true" /> Refresh
        </button>
      </div>

      {!organizationId ? (
        <div className="ou-state" role="status">
          <Building2 aria-hidden="true" /> Select an organization to browse Organizational Units.
        </div>
      ) : !canRead ? (
        <div className="ou-state warning" role="status">
          <AlertCircle aria-hidden="true" /> Connector-operation access is required.
        </div>
      ) : !connectorReady ? (
        <div className="ou-state warning" role="status">
          <AlertCircle aria-hidden="true" /> Connect and successfully test Google Workspace for {organizationName ?? "this organization"} before browsing.
        </div>
      ) : error ? (
        <div className="ou-state error" role="alert">
          <AlertCircle aria-hidden="true" /> <span>{error}</span>
          <button type="button" className="secondary-button" onClick={() => void loadHierarchy()}>
            Try again
          </button>
        </div>
      ) : isLoading ? (
        <div className="ou-state" role="status">
          <Loader2 className="spin" aria-hidden="true" /> Loading Organizational Units…
        </div>
      ) : roots.length === 0 ? (
        <div className="ou-state" role="status">
          <FolderTree aria-hidden="true" /> Google returned no Organizational Units.
        </div>
      ) : (
        <div className="ou-layout">
          <section className="ou-tree-panel" aria-labelledby="ou-tree-heading">
            <div className="ou-panel-heading">
              <div>
                <h3 id="ou-tree-heading">Hierarchy</h3>
                <p>{total} organizational {total === 1 ? "unit" : "units"}</p>
              </div>
              <span className="readonly-badge"><ShieldCheck aria-hidden="true" /> Read only</span>
            </div>
            <div className="ou-tree" role="tree" aria-label="Organizational Units hierarchy">
              {visibleUnits.map(({ unit, depth }) => {
                const hasChildren = unit.children.length > 0;
                const isExpanded = expanded.has(unit.id);
                const isSelected = selectedId === unit.id;
                return (
                  <div
                    className="ou-tree-row"
                    key={unit.id}
                    style={{ "--ou-depth": depth } as CSSProperties}
                  >
                    <button
                      type="button"
                      className="ou-expand-button"
                      aria-label={`${isExpanded ? "Collapse" : "Expand"} ${unit.name}`}
                      disabled={!hasChildren}
                      onClick={() => toggle(unit)}
                    >
                      {hasChildren ? (
                        isExpanded ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />
                      ) : <span aria-hidden="true" />}
                    </button>
                    <button
                      type="button"
                      className={`ou-tree-item ${isSelected ? "selected" : ""}`}
                      role="treeitem"
                      aria-label={`${unit.name} (${unit.path})`}
                      aria-level={depth}
                      aria-selected={isSelected}
                      aria-expanded={hasChildren ? isExpanded : undefined}
                      tabIndex={isSelected ? 0 : -1}
                      ref={(element) => {
                        if (element) itemRefs.current.set(unit.id, element);
                        else itemRefs.current.delete(unit.id);
                      }}
                      onClick={() => setSelectedId(unit.id)}
                      onKeyDown={(event) => handleTreeKeyDown(event, unit)}
                    >
                      <FolderTree aria-hidden="true" />
                      <span><strong>{unit.name}</strong><small>{unit.path}</small></span>
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          <aside className="ou-detail-panel" aria-live="polite">
            {selectedUnit ? (
              <>
                <div className="ou-panel-heading">
                  <div><span className="eyebrow">Selected unit</span><h3>{selectedUnit.name}</h3></div>
                  <span className="readonly-badge"><ShieldCheck aria-hidden="true" /> Read only</span>
                </div>
                <dl className="ou-details">
                  <div><dt>Full path</dt><dd>{selectedUnit.path}</dd></div>
                  <div><dt>Parent path</dt><dd>{selectedUnit.parent_path ?? "Top level"}</dd></div>
                  <div><dt>Immutable ID</dt><dd><code>{selectedUnit.id}</code></dd></div>
                  <div><dt>Description</dt><dd>{selectedUnit.description ?? "No description provided."}</dd></div>
                  <div><dt>Direct children</dt><dd>{selectedUnit.children.length}</dd></div>
                  <div><dt>Access</dt><dd>Read only</dd></div>
                </dl>
                <p className="ou-readonly-note">
                  Create, rename, move, delete, and user/device movement are unavailable in DIR-003.1.
                </p>
              </>
            ) : (
              <div className="ou-state" role="status">Select an Organizational Unit to inspect it.</div>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
