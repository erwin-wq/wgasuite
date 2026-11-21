import {
  AlertCircle,
  ArrowLeft,
  Building2,
  ChevronDown,
  ChevronRight,
  Folder,
  FolderTree,
  Info,
  ListTree,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck
} from "lucide-react";
import { CSSProperties, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, listGoogleWorkspaceOrganizationalUnits } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Alert, Badge } from "../../components/ui/Feedback";
import type {
  ConnectorConfig,
  GoogleWorkspaceOrganizationalUnitTreeNode
} from "../../types";
import { DIRECTORY_ORGUNIT_READONLY_SCOPE } from "./scopes";
import { OrganizationalUnitCreation } from "./OrganizationalUnitCreation";
import { OrganizationalUnitDescription } from "./OrganizationalUnitDescription";

export { DIRECTORY_ORGUNIT_READONLY_SCOPE } from "./scopes";

interface OrganizationalUnitsProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canRead: boolean;
  canCreate: boolean;
}

interface VisibleUnit {
  unit: GoogleWorkspaceOrganizationalUnitTreeNode;
  depth: number;
}

type MobileView = "hierarchy" | "details";

const WORKSPACE_GUESTS_PATH = "/Workspace Guests";

function isCreationProtected(unit: GoogleWorkspaceOrganizationalUnitTreeNode): boolean {
  return (
    unit.path === WORKSPACE_GUESTS_PATH ||
    unit.path.startsWith(`${WORKSPACE_GUESTS_PATH}/`)
  );
}

function isDescriptionProtected(unit: GoogleWorkspaceOrganizationalUnitTreeNode): boolean {
  return unit.path === "/" || isCreationProtected(unit);
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

function findParent(
  roots: GoogleWorkspaceOrganizationalUnitTreeNode[],
  unit: GoogleWorkspaceOrganizationalUnitTreeNode | null
): GoogleWorkspaceOrganizationalUnitTreeNode | null {
  return unit?.parent_id ? findUnit(roots, unit.parent_id) : null;
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
  canRead,
  canCreate
}: OrganizationalUnitsProps) {
  const [roots, setRoots] = useState<GoogleWorkspaceOrganizationalUnitTreeNode[]>([]);
  const [total, setTotal] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<MobileView>("hierarchy");
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
      setSelectedId((current) =>
        findUnit(result.roots, current) ? current : (result.roots[0]?.id ?? null)
      );
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
    setMobileView("hierarchy");
    setError(null);
    setIsLoading(false);
    if (organizationId && connectorReady && canRead) void loadHierarchy();
    return () => requestController.current?.abort();
  }, [canRead, connectorReady, loadHierarchy, organizationId]);

  const visibleUnits = useMemo(() => flattenVisible(roots, expanded), [expanded, roots]);
  const selectedUnit = useMemo(() => findUnit(roots, selectedId), [roots, selectedId]);
  const selectedParent = useMemo(
    () => findParent(roots, selectedUnit),
    [roots, selectedUnit]
  );

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
        <h2 id="organizational-units-heading" className="sr-only">Organizational Units explorer</h2>
        <p>Verified Google Directory hierarchy</p>
        <Button
          variant="secondary"
          disabled={isLoading || !connectorReady || !canRead}
          onClick={() => void loadHierarchy()}
        >
          <RefreshCw className={isLoading ? "spin" : ""} aria-hidden="true" /> Refresh
        </Button>
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
      ) : isLoading && roots.length === 0 ? (
        <div className="ou-state" role="status">
          <Loader2 className="spin" aria-hidden="true" /> Loading Organizational Units…
        </div>
      ) : roots.length === 0 ? (
        <div className="ou-state" role="status">
          <FolderTree aria-hidden="true" /> Google returned no Organizational Units.
        </div>
      ) : (
        <>
          <div className="ou-mobile-view-switch" aria-label="Organizational Unit view">
            <button
              type="button"
              className={mobileView === "hierarchy" ? "active" : ""}
              aria-pressed={mobileView === "hierarchy"}
              onClick={() => setMobileView("hierarchy")}
            >
              <ListTree aria-hidden="true" /> Hierarchy
            </button>
            <button
              type="button"
              className={mobileView === "details" ? "active" : ""}
              aria-pressed={mobileView === "details"}
              disabled={!selectedUnit}
              onClick={() => setMobileView("details")}
            >
              <Info aria-hidden="true" /> Details
            </button>
          </div>

        <div className="ou-layout">
          <section
            className={`ou-tree-panel ${mobileView === "hierarchy" ? "ou-mobile-active" : ""}`}
            aria-labelledby="ou-tree-heading"
          >
            <div className="ou-panel-heading">
              <div>
                <h3 id="ou-tree-heading">Hierarchy</h3>
                <p>{total} organizational {total === 1 ? "unit" : "units"}</p>
              </div>
              <Badge variant="info" icon={<ShieldCheck aria-hidden="true" />}>Verified hierarchy</Badge>
            </div>
            <div className="ou-tree" role="tree" aria-label="Organizational Units hierarchy">
              {visibleUnits.map(({ unit, depth }) => {
                const hasChildren = unit.children.length > 0;
                const isExpanded = expanded.has(unit.id);
                const isSelected = selectedId === unit.id;
                const isRoot = unit.path === "/";
                const isProtected = isCreationProtected(unit);
                const UnitIcon = isRoot ? Building2 : isProtected ? ShieldAlert : Folder;
                return (
                  <div
                    className={`ou-tree-row ${isRoot ? "ou-tree-row--root" : ""} ${isProtected ? "ou-tree-row--protected" : ""}`}
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
                      onClick={() => {
                        setSelectedId(unit.id);
                        setMobileView("details");
                      }}
                      onKeyDown={(event) => handleTreeKeyDown(event, unit)}
                    >
                      <UnitIcon aria-hidden="true" />
                      <span>
                        <strong>{unit.name}</strong>
                        <small>{unit.path}</small>
                      </span>
                      {isRoot ? <em>Root</em> : null}
                      {isProtected ? <em>Protected</em> : null}
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          <aside
            className={`ou-detail-panel ${mobileView === "details" ? "ou-mobile-active" : ""}`}
            aria-live="polite"
          >
            {selectedUnit ? (
              <>
                <button
                  type="button"
                  className="ou-mobile-back"
                  onClick={() => setMobileView("hierarchy")}
                >
                  <ArrowLeft aria-hidden="true" /> Back to hierarchy
                </button>
                <div className="ou-current-path">
                  <FolderTree aria-hidden="true" />
                  <span><strong>Current path</strong>{selectedUnit.path}</span>
                </div>
                <div className="ou-panel-heading">
                  <div className="ou-selected-heading">
                    {selectedUnit.path === "/" ? <Building2 aria-hidden="true" /> : <Folder aria-hidden="true" />}
                    <div><span className="eyebrow">Selected unit</span><h3>{selectedUnit.name}</h3></div>
                  </div>
                  <Badge variant="success" icon={<ShieldCheck aria-hidden="true" />}>Verified tenant</Badge>
                </div>
                {canCreate && (
                  <div className="ou-detail-actions">
                    {!isCreationProtected(selectedUnit) ? (
                      <OrganizationalUnitCreation
                        organizationId={organizationId}
                        parent={selectedUnit}
                        onCreated={loadHierarchy}
                      />
                    ) : null}
                    {!isDescriptionProtected(selectedUnit) ? (
                      <OrganizationalUnitDescription
                        organizationId={organizationId}
                        unit={selectedUnit}
                        onUpdated={loadHierarchy}
                      />
                    ) : null}
                  </div>
                )}
                {canCreate && isCreationProtected(selectedUnit) && (
                  <p className="ou-create-warning" role="status">
                    <AlertCircle aria-hidden="true" /> Workspace Guests and its descendants are
                    protected system Organizational Units. Create a child under an ordinary OU.
                  </p>
                )}
                {canCreate && selectedUnit.path === "/" && (
                  <p className="ou-create-warning" role="status">
                    <AlertCircle aria-hidden="true" /> The root Organizational Unit description is
                    protected. Select an ordinary child unit to edit its description.
                  </p>
                )}
                <dl className="ou-details">
                  <div><dt>Full path</dt><dd>{selectedUnit.path}</dd></div>
                  <div><dt>Parent</dt><dd>{selectedParent ? <><strong>{selectedParent.name}</strong><span>{selectedUnit.parent_path}</span></> : "Top level"}</dd></div>
                  <div><dt>Immutable ID</dt><dd><code>{selectedUnit.id}</code></dd></div>
                  <div><dt>Description</dt><dd>{selectedUnit.description ?? "No description provided."}</dd></div>
                  <div><dt>Access</dt><dd>{canCreate ? "Guarded administration" : "Read only"}</dd></div>
                </dl>
                <section className="ou-children" aria-labelledby="ou-children-heading">
                  <div>
                    <h4 id="ou-children-heading">Direct children</h4>
                    <span>{selectedUnit.children.length}</span>
                  </div>
                  {selectedUnit.children.length > 0 ? (
                    <ul>
                      {selectedUnit.children.map((child) => (
                        <li key={child.id}><Folder aria-hidden="true" /> {child.name}</li>
                      ))}
                    </ul>
                  ) : <p>No direct child units.</p>}
                </section>
                <Alert variant="warning" title="Effective inherited policies are unknown.">
                  Google Directory does not expose the effective inherited policy configuration in this view.
                </Alert>
                <Alert variant="info" title="Unsupported operations">
                  Rename, reparent, delete, and device movement are not available. Supported writes retain explicit preview and confirmation safeguards.
                </Alert>
              </>
            ) : (
              <div className="ou-state" role="status">Select an Organizational Unit to inspect it.</div>
            )}
          </aside>
        </div>
        </>
      )}
    </section>
  );
}
