import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  X
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  executeGoogleWorkspaceUserStatusChange,
  previewGoogleWorkspaceUserStatusChange,
  reconcileGoogleWorkspaceUserStatusChange
} from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceUser,
  GoogleWorkspaceUserStatusPreview
} from "../../types";

interface UserStatusManagementProps {
  organizationId: string;
  connectorConfig: ConnectorConfig | null;
  user: GoogleWorkspaceUser;
  canMutate: boolean;
  onRefresh: () => Promise<void>;
}

const AMBIGUOUS_CODES = new Set([
  "google_timeout",
  "google_network_error",
  "google_service_unavailable",
  "google_api_error"
]);

function isAmbiguous(error: unknown): error is ApiError {
  return (
    error instanceof ApiError &&
    error.reconciliationAvailable &&
    AMBIGUOUS_CODES.has(error.code ?? "")
  );
}

function actionError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The user status request could not be completed. Check the connection and try again.";
  }
  const protectedCodes = new Set([
    "google_user_admin_protected",
    "google_user_self_protected",
    "google_user_service_account_protected",
    "google_user_archived",
    "google_user_deleted",
    "google_user_suspension_reason_unsupported"
  ]);
  if (protectedCodes.has(error.code ?? "")) return error.message;
  if (
    error.code === "google_user_confirmation_invalid" ||
    error.code === "google_user_confirmation_expired" ||
    error.code === "google_user_confirmation_used" ||
    error.code === "google_user_state_changed"
  ) {
    return "The account changed or the confirmation expired. Refresh the user and review again.";
  }
  if (error.code === "missing_scope_or_permission" || error.code === "google_forbidden") {
    return "Google denied this change. Verify the Directory user write scope and delegated administrator privileges.";
  }
  if (error.status === 403) {
    return "You do not have permission to change users for this organization.";
  }
  return error.message;
}

function protectionReason(
  user: GoogleWorkspaceUser,
  connectorConfig: ConnectorConfig | null
): string | null {
  if (user.is_super_admin) return "Super administrator accounts are protected.";
  if (user.is_delegated_admin) return "Delegated administrator accounts are protected.";
  if (user.is_super_admin === null || user.is_delegated_admin === null) {
    return "Administrator status could not be verified, so changes are disabled.";
  }
  if (user.archived) return "Archived accounts cannot be changed here.";
  if (user.deletion_time) return "Deleted accounts cannot be changed here.";
  const identities = [user.primary_email, ...user.aliases, ...user.non_editable_aliases].map(
    (value) => value.toLowerCase()
  );
  if (
    connectorConfig?.admin_subject_email &&
    identities.includes(connectorConfig.admin_subject_email.toLowerCase())
  ) {
    return "The configured delegated administrator is protected.";
  }
  if (
    connectorConfig?.service_account_email &&
    identities.includes(connectorConfig.service_account_email.toLowerCase())
  ) {
    return "The configured service identity is protected.";
  }
  if (user.suspended && user.suspension_reason?.trim().toUpperCase() !== "ADMIN") {
    return "Only suspensions verified as administrator-controlled can be reversed here.";
  }
  return null;
}

export function UserStatusManagement({
  organizationId,
  connectorConfig,
  user,
  canMutate,
  onRefresh
}: UserStatusManagementProps) {
  const [preview, setPreview] = useState<GoogleWorkspaceUserStatusPreview | null>(null);
  const [ambiguousPreview, setAmbiguousPreview] =
    useState<GoogleWorkspaceUserStatusPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error" | "warning" | "info";
    message: string;
  } | null>(null);
  const [busy, setBusy] = useState<"preview" | "mutation" | "reconcile" | null>(null);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const mutationInFlight = useRef(false);
  const protectedReason = protectionReason(user, connectorConfig);
  const operation = user.suspended ? "reactivate" : "suspend";

  useEffect(() => {
    sequence.current += 1;
    controller.current?.abort();
    controller.current = null;
    setPreview(null);
    setAmbiguousPreview(null);
    setConfirmed(false);
    setFeedback(null);
    setBusy(null);
    mutationInFlight.current = false;
    return () => controller.current?.abort();
  }, [organizationId, user.id, user.suspended]);

  async function startPreview() {
    if (!canMutate || protectedReason || busy || ambiguousPreview) return;
    controller.current?.abort();
    const requestController = new AbortController();
    controller.current = requestController;
    const current = sequence.current + 1;
    sequence.current = current;
    setBusy("preview");
    setFeedback(null);
    try {
      const result = await previewGoogleWorkspaceUserStatusChange(
        organizationId,
        operation,
        user.primary_email,
        requestController.signal
      );
      if (sequence.current === current) {
        setPreview(result);
        setConfirmed(false);
      }
    } catch (error) {
      if (requestController.signal.aborted || sequence.current !== current) return;
      setFeedback({ type: "error", message: actionError(error) });
    } finally {
      if (sequence.current === current) {
        controller.current = null;
        setBusy(null);
      }
    }
  }

  async function reconcile(change: GoogleWorkspaceUserStatusPreview, current: number) {
    if (busy === "reconcile") return;
    const requestController = new AbortController();
    controller.current = requestController;
    setBusy("reconcile");
    setFeedback({
      type: "info",
      message: "Google did not confirm the response. Checking current status without resubmitting the change…"
    });
    try {
      const result = await reconcileGoogleWorkspaceUserStatusChange(
        organizationId,
        change.operation,
        change.confirmation_token,
        requestController.signal
      );
      if (sequence.current !== current) return;
      if (result.status === "verified") {
        setAmbiguousPreview(null);
        setFeedback({ type: "success", message: result.message });
        setBusy(null);
        await onRefresh();
        return;
      }
      setFeedback({ type: "warning", message: result.message });
    } catch (error) {
      if (requestController.signal.aborted || sequence.current !== current) return;
      setFeedback({
        type: "warning",
        message: `The outcome is still unknown. ${actionError(error)} The original change was not resubmitted.`
      });
    } finally {
      if (sequence.current === current) {
        controller.current = null;
        setBusy(null);
      }
    }
  }

  async function confirmChange() {
    if (!preview || !confirmed || mutationInFlight.current || busy || ambiguousPreview) return;
    mutationInFlight.current = true;
    const change = preview;
    const current = sequence.current;
    setBusy("mutation");
    setFeedback(null);
    try {
      const result = await executeGoogleWorkspaceUserStatusChange(
        organizationId,
        change.operation,
        change.confirmation_token
      );
      if (sequence.current !== current) return;
      setPreview(null);
      setConfirmed(false);
      setFeedback({ type: "success", message: result.message });
      setBusy(null);
      await onRefresh();
    } catch (error) {
      if (sequence.current !== current) return;
      setPreview(null);
      setConfirmed(false);
      if (isAmbiguous(error)) {
        setAmbiguousPreview(change);
        setBusy(null);
        await reconcile(change, current);
        return;
      }
      setFeedback({ type: "error", message: actionError(error) });
      setBusy(null);
    } finally {
      mutationInFlight.current = false;
    }
  }

  return (
    <section className="user-status-management" aria-labelledby="user-status-heading">
      <div className="user-status-heading">
        <div>
          <h4 id="user-status-heading">Account access</h4>
          <p>
            Suspend or reactivate this Directory user. Google data is not deleted by suspension.
          </p>
        </div>
        {!protectedReason && canMutate && (
          <button
            type="button"
            className={operation === "suspend" ? "danger-button" : "secondary-button"}
            onClick={() => void startPreview()}
            disabled={busy !== null || ambiguousPreview !== null}
          >
            {busy === "preview" ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : operation === "suspend" ? (
              <PauseCircle aria-hidden="true" />
            ) : (
              <PlayCircle aria-hidden="true" />
            )}
            {operation === "suspend" ? "Suspend user" : "Reactivate user"}
          </button>
        )}
      </div>

      {protectedReason && (
        <p className="user-status-protected"><ShieldAlert aria-hidden="true" />{protectedReason}</p>
      )}
      {!canMutate && !protectedReason && (
        <p className="user-status-protected"><ShieldAlert aria-hidden="true" />Customer administrator access is required.</p>
      )}
      {feedback && (
        <p className={`message ${feedback.type}`} role={feedback.type === "error" ? "alert" : "status"}>
          {feedback.type === "success" ? <CheckCircle2 aria-hidden="true" /> : <AlertCircle aria-hidden="true" />}
          {feedback.message}
        </p>
      )}
      {ambiguousPreview && (
        <button
          type="button"
          className="secondary-button"
          onClick={() => void reconcile(ambiguousPreview, sequence.current)}
          disabled={busy !== null}
        >
          {busy === "reconcile" ? <Loader2 className="spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
          Check status
        </button>
      )}

      {preview && (
        <div className="confirmation-backdrop" role="presentation">
          <div
            className="confirmation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-status-confirmation-title"
          >
            <button
              type="button"
              className="dialog-close"
              aria-label="Close confirmation"
              onClick={() => setPreview(null)}
              disabled={busy === "mutation"}
            >
              <X aria-hidden="true" />
            </button>
            <div className={`confirmation-icon ${preview.operation === "suspend" ? "remove" : ""}`}>
              <AlertTriangle aria-hidden="true" />
            </div>
            <h3 id="user-status-confirmation-title">
              {preview.operation === "suspend" ? "Suspend this user?" : "Reactivate this user?"}
            </h3>
            <p>{preview.effect}</p>
            <dl className="confirmation-identities">
              <div><dt>Google Workspace account</dt><dd>{preview.target_primary_email}</dd></div>
              <div><dt>Immutable Google user ID</dt><dd>{preview.target_google_id}</dd></div>
            </dl>
            <label className="confirmation-checkbox">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
                disabled={busy === "mutation"}
              />
              I understand this changes the user&apos;s access to Google Workspace.
            </label>
            <div className="confirmation-actions">
              <button type="button" className="secondary-button" onClick={() => setPreview(null)} disabled={busy === "mutation"}>Cancel</button>
              <button
                type="button"
                className={preview.operation === "suspend" ? "danger-button" : ""}
                onClick={() => void confirmChange()}
                disabled={!confirmed || busy === "mutation"}
              >
                {busy === "mutation" && <Loader2 className="spin" aria-hidden="true" />}
                Confirm {preview.operation === "suspend" ? "suspension" : "reactivation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
