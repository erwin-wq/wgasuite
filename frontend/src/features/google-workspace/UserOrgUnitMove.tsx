import {
  AlertCircle,
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle2,
  FolderTree,
  Loader2,
  RefreshCw,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  executeGoogleWorkspaceUserOrgUnitMove,
  listGoogleWorkspaceOrganizationalUnits,
  previewGoogleWorkspaceUserOrgUnitMove,
  reconcileGoogleWorkspaceUserOrgUnitMove
} from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceOrganizationalUnitTreeNode,
  GoogleWorkspaceUser,
  GoogleWorkspaceUserOrgUnitMovePreview
} from "../../types";

interface UserOrgUnitMoveProps {
  organizationId: string;
  connectorConfig: ConnectorConfig | null;
  user: GoogleWorkspaceUser;
  canMutate: boolean;
  onRefresh: () => Promise<void>;
}

interface FlatUnit {
  unit: GoogleWorkspaceOrganizationalUnitTreeNode;
  depth: number;
}

const AMBIGUOUS_CODES = new Set([
  "google_timeout",
  "google_network_error",
  "google_service_unavailable",
  "google_api_error"
]);

function flatten(
  roots: GoogleWorkspaceOrganizationalUnitTreeNode[],
  depth = 0
): FlatUnit[] {
  return roots.flatMap((unit) => [
    { unit, depth },
    ...flatten(unit.children, depth + 1)
  ]);
}

function protectedReason(
  user: GoogleWorkspaceUser,
  connector: ConnectorConfig | null
): string | null {
  if (user.is_super_admin || user.is_delegated_admin) {
    return "Administrator accounts are protected from Organizational Unit moves.";
  }
  if (user.is_super_admin === null || user.is_delegated_admin === null) {
    return "Administrator status could not be verified, so moves are disabled.";
  }
  if (user.archived || user.deletion_time) return "Archived or deleted users cannot be moved.";
  const identities = [user.primary_email, ...user.aliases, ...user.non_editable_aliases].map(
    (value) => value.toLowerCase()
  );
  if (
    connector?.admin_subject_email &&
    identities.includes(connector.admin_subject_email.toLowerCase())
  ) {
    return "The delegated administrator account is protected.";
  }
  if (
    connector?.service_account_email &&
    identities.includes(connector.service_account_email.toLowerCase())
  ) {
    return "The configured service identity is protected.";
  }
  return null;
}

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The Organizational Unit move could not be completed.";
  }
  if (
    error.code === "google_orgunit_confirmation_expired" ||
    error.code === "google_orgunit_confirmation_used" ||
    error.code === "google_orgunit_state_changed"
  ) {
    return "The user or destination changed, or the confirmation expired. Refresh and review again.";
  }
  if (error.code === "google_orgunit_unchanged") {
    return "Select a different Organizational Unit.";
  }
  if (error.code === "missing_scope_or_permission" || error.code === "google_forbidden") {
    return "Google denied the move. Verify the Directory user write scope, Organizational Units read scope, and delegated administrator privileges.";
  }
  return error.message;
}

export function UserOrgUnitMove({
  organizationId,
  connectorConfig,
  user,
  canMutate,
  onRefresh
}: UserOrgUnitMoveProps) {
  const [open, setOpen] = useState(false);
  const [units, setUnits] = useState<GoogleWorkspaceOrganizationalUnitTreeNode[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<GoogleWorkspaceUserOrgUnitMovePreview | null>(null);
  const [ambiguousPreview, setAmbiguousPreview] =
    useState<GoogleWorkspaceUserOrgUnitMovePreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<"load" | "preview" | "move" | "reconcile" | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "warning"; message: string } | null>(null);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const mutationInFlight = useRef(false);
  const restriction = protectedReason(user, connectorConfig);
  const flatUnits = useMemo(() => flatten(units), [units]);
  const selected = flatUnits.find(({ unit }) => unit.id === selectedId)?.unit ?? null;

  function moveTreeFocus(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = Array.from(
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
        '[role="treeitem"]:not(:disabled)'
      ) ?? []
    );
    if (items.length === 0) return;
    const current = items.indexOf(event.currentTarget);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? items.length - 1
          : event.key === "ArrowDown"
            ? Math.min(current + 1, items.length - 1)
            : Math.max(current - 1, 0);
    event.preventDefault();
    items[next]?.focus();
  }

  useEffect(() => {
    sequence.current += 1;
    controller.current?.abort();
    setOpen(false);
    setUnits([]);
    setSelectedId(null);
    setPreview(null);
    setAmbiguousPreview(null);
    setConfirmed(false);
    setBusy(null);
    setFeedback(null);
    mutationInFlight.current = false;
    return () => controller.current?.abort();
  }, [organizationId, user.id, user.org_unit_path]);

  async function openPicker() {
    if (!canMutate || restriction || busy) return;
    const requestController = new AbortController();
    controller.current = requestController;
    const current = ++sequence.current;
    setOpen(true);
    setBusy("load");
    setFeedback(null);
    try {
      const result = await listGoogleWorkspaceOrganizationalUnits(
        organizationId,
        requestController.signal
      );
      if (current !== sequence.current) return;
      setUnits(result.roots);
    } catch (error) {
      if (!requestController.signal.aborted && current === sequence.current) {
        setFeedback({ type: "error", message: errorMessage(error) });
      }
    } finally {
      if (current === sequence.current) setBusy(null);
    }
  }

  async function reviewMove() {
    if (!selected || selected.path === user.org_unit_path || busy) return;
    const requestController = new AbortController();
    controller.current = requestController;
    const current = sequence.current;
    setBusy("preview");
    setFeedback(null);
    try {
      const result = await previewGoogleWorkspaceUserOrgUnitMove(
        organizationId,
        user.id,
        selected.id,
        requestController.signal
      );
      if (current === sequence.current) {
        setPreview(result);
        setConfirmed(false);
      }
    } catch (error) {
      if (!requestController.signal.aborted && current === sequence.current) {
        setFeedback({ type: "error", message: errorMessage(error) });
      }
    } finally {
      if (current === sequence.current) setBusy(null);
    }
  }

  async function reconcile(change: GoogleWorkspaceUserOrgUnitMovePreview, current: number) {
    setBusy("reconcile");
    try {
      const result = await reconcileGoogleWorkspaceUserOrgUnitMove(
        organizationId,
        change.confirmation_token
      );
      if (current !== sequence.current) return;
      if (result.status === "verified") {
        setOpen(false);
        setPreview(null);
        setAmbiguousPreview(null);
        setFeedback({ type: "success", message: result.message });
        setBusy(null);
        await onRefresh();
      } else {
        setFeedback({ type: "warning", message: result.message });
      }
    } catch (error) {
      if (current === sequence.current) {
        setFeedback({
          type: "warning",
          message: `${errorMessage(error)} The original move was not resubmitted.`
        });
      }
    } finally {
      if (current === sequence.current) setBusy(null);
    }
  }

  async function confirmMove() {
    if (!preview || !confirmed || busy || mutationInFlight.current) return;
    mutationInFlight.current = true;
    const change = preview;
    const current = sequence.current;
    setBusy("move");
    try {
      const result = await executeGoogleWorkspaceUserOrgUnitMove(
        organizationId,
        change.confirmation_token
      );
      if (current !== sequence.current) return;
      setOpen(false);
      setPreview(null);
      setFeedback({ type: "success", message: result.message });
      setBusy(null);
      await onRefresh();
    } catch (error) {
      if (current !== sequence.current) return;
      setPreview(null);
      if (
        error instanceof ApiError &&
        error.reconciliationAvailable &&
        AMBIGUOUS_CODES.has(error.code ?? "")
      ) {
        setAmbiguousPreview(change);
        setFeedback({
          type: "warning",
          message: "Google did not confirm the response. Checking without repeating the move…"
        });
        setBusy(null);
        await reconcile(change, current);
      } else {
        setFeedback({ type: "error", message: errorMessage(error) });
        setBusy(null);
      }
    } finally {
      mutationInFlight.current = false;
    }
  }

  return (
    <section className="user-orgunit-move" aria-labelledby="user-orgunit-move-heading">
      <div className="user-status-heading">
        <div>
          <h4 id="user-orgunit-move-heading">Organizational Unit</h4>
          <p>Move this user between existing units with a guarded confirmation.</p>
        </div>
        {!restriction && canMutate && (
          <button type="button" className="secondary-button" onClick={() => void openPicker()} disabled={busy !== null}>
            <ArrowRightLeft aria-hidden="true" /> Move to Organizational Unit
          </button>
        )}
      </div>
      <p className="user-orgunit-current"><strong>Current path:</strong> {user.org_unit_path ?? "Not available"}</p>
      {(restriction || !canMutate) && (
        <p className="user-status-protected"><AlertTriangle aria-hidden="true" />{restriction ?? "Customer administrator access is required."}</p>
      )}
      {feedback && (
        <div className={`user-status-feedback ${feedback.type}`} role={feedback.type === "error" ? "alert" : "status"}>
          {feedback.type === "success" ? <CheckCircle2 aria-hidden="true" /> : <AlertCircle aria-hidden="true" />}
          <span>{feedback.message}</span>
          {feedback.type === "warning" && ambiguousPreview && (
            <button type="button" className="secondary-button" onClick={() => void reconcile(ambiguousPreview, sequence.current)} disabled={busy !== null}>
              <RefreshCw aria-hidden="true" /> Check again
            </button>
          )}
        </div>
      )}
      {open && (
        <div className="ou-move-backdrop" role="presentation">
          <div className="ou-move-dialog" role="dialog" aria-modal="true" aria-labelledby="ou-move-dialog-heading">
            <div className="ou-move-dialog-heading">
              <div><span className="eyebrow">Guarded Directory change</span><h3 id="ou-move-dialog-heading">Move {user.primary_email}</h3></div>
              <button type="button" className="icon-button" aria-label="Close Organizational Unit picker" onClick={() => setOpen(false)} disabled={busy === "move" || busy === "reconcile"}><X aria-hidden="true" /></button>
            </div>
            <p><strong>Current:</strong> {user.org_unit_path ?? "Unknown"}</p>
            {busy === "load" ? (
              <p className="ou-move-state"><Loader2 className="spin" aria-hidden="true" /> Loading hierarchy…</p>
            ) : (
              <div className="ou-move-tree" role="tree" aria-label="Choose destination Organizational Unit">
                {flatUnits.map(({ unit, depth }) => {
                  const current = unit.path === user.org_unit_path;
                  return (
                    <button
                      type="button"
                      key={unit.id}
                      role="treeitem"
                      aria-level={depth + 1}
                      aria-selected={selectedId === unit.id}
                      className={selectedId === unit.id ? "selected" : ""}
                      style={{ paddingInlineStart: `${1 + depth * 1.25}rem` }}
                      disabled={current || preview !== null}
                      onClick={() => setSelectedId(unit.id)}
                      onKeyDown={moveTreeFocus}
                    >
                      <FolderTree aria-hidden="true" /><span><strong>{unit.name}</strong><small>{unit.path}{current ? " (current)" : ""}</small></span>
                    </button>
                  );
                })}
              </div>
            )}
            {selected && <p><strong>Destination:</strong> {selected.path}</p>}
            {preview && (
              <div className="ou-move-preview">
                <AlertTriangle aria-hidden="true" />
                <div><strong>{preview.source_org_unit_path} → {preview.destination_org_unit_path}</strong><p>{preview.effect}</p></div>
              </div>
            )}
            {preview && (
              <label className="confirmation-checkbox">
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                I confirm this user should move to {preview.destination_org_unit_path}.
              </label>
            )}
            <div className="confirmation-actions">
              <button type="button" className="secondary-button" onClick={() => setOpen(false)} disabled={busy === "move" || busy === "reconcile"}>Cancel</button>
              {!preview ? (
                <button type="button" onClick={() => void reviewMove()} disabled={!selected || selected.path === user.org_unit_path || busy !== null}>{busy === "preview" && <Loader2 className="spin" aria-hidden="true" />} Review move</button>
              ) : (
                <button type="button" onClick={() => void confirmMove()} disabled={!confirmed || busy !== null}>{busy === "move" && <Loader2 className="spin" aria-hidden="true" />} Confirm move</button>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
