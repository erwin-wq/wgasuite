import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  MailPlus,
  RefreshCw,
  ShieldAlert,
  Trash2,
  UsersRound,
  X
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  executeGmailDelegateChange,
  listGmailDelegates,
  previewGmailDelegateChange,
  reconcileGmailDelegateChange
} from "../../api/client";
import type {
  GmailDelegate,
  GmailDelegateChangePreview,
  GoogleWorkspaceUser
} from "../../types";

interface MailboxDelegatesProps {
  organizationId: string;
  owner: GoogleWorkspaceUser;
  canMutate: boolean;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const AMBIGUOUS_MUTATION_CODES = new Set([
  "google_timeout",
  "google_network_error",
  "google_service_unavailable"
]);

interface AmbiguousChange {
  preview: GmailDelegateChangePreview;
}

function isAmbiguousMutationError(error: unknown): error is ApiError {
  return (
    error instanceof ApiError &&
    error.reconciliationAvailable &&
    AMBIGUOUS_MUTATION_CODES.has(error.code ?? "")
  );
}

function delegationErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The Gmail delegation request could not be completed. Check the connection and try again.";
  }
  if (error.code === "gmail_scope_missing") {
    return "Gmail delegation access is not authorized. Add the required Gmail scope in domain-wide delegation.";
  }
  if (error.code === "gmail_api_unavailable") {
    return "The Gmail API is not enabled or accessible for this Google Cloud project.";
  }
  if (error.code === "gmail_mailbox_not_configured") {
    return "This user does not have an active Gmail mailbox.";
  }
  if (error.code === "gmail_user_ineligible") {
    return "The mailbox owner or delegate is suspended, archived, or not Gmail-enabled.";
  }
  if (error.code === "gmail_delegate_already_exists") {
    return "That user already has access to this mailbox. Refresh the delegate list.";
  }
  if (error.code === "gmail_delegate_not_found") {
    return "That delegation no longer exists. Refresh the delegate list.";
  }
  if (
    error.code === "gmail_confirmation_invalid" ||
    error.code === "gmail_confirmation_expired" ||
    error.code === "gmail_confirmation_used"
  ) {
    return "The confirmation is no longer valid. Review the operation again.";
  }
  if (error.code === "google_tenant_mismatch") {
    return "The mailbox owner and delegate do not belong to the configured Workspace tenant.";
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited this request. Wait before trying again.";
  }
  if (
    error.code === "google_timeout" ||
    error.code === "google_network_error" ||
    error.code === "google_service_unavailable"
  ) {
    return "Google did not return a reliable result. Refresh before attempting another change.";
  }
  if (error.status === 403) {
    return "You do not have permission to manage delegates for this organization.";
  }
  return error.message;
}

function verificationLabel(delegate: GmailDelegate): string {
  if (delegate.verification_status === "accepted") return "Accepted";
  if (delegate.verification_status === "pending") return "Pending";
  if (delegate.verification_status === "rejected") return "Rejected";
  return "Unknown";
}

export function MailboxDelegates({
  organizationId,
  owner,
  canMutate
}: MailboxDelegatesProps) {
  const [delegates, setDelegates] = useState<GmailDelegate[]>([]);
  const [delegateEmail, setDelegateEmail] = useState("");
  const [listError, setListError] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<
    { type: "success" | "error" | "warning" | "info"; message: string } | null
  >(null);
  const [pendingPreview, setPendingPreview] = useState<GmailDelegateChangePreview | null>(null);
  const [ambiguousChange, setAmbiguousChange] = useState<AmbiguousChange | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [isReconciling, setIsReconciling] = useState(false);
  const requestSequence = useRef(0);
  const readController = useRef<AbortController | null>(null);
  const reconciliationInFlight = useRef(false);

  const loadDelegates = useCallback(async (preserveActionFeedback = false) => {
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setIsLoading(true);
    setListError(null);
    if (!preserveActionFeedback) setActionFeedback(null);
    try {
      const result = await listGmailDelegates(
        organizationId,
        owner.primary_email,
        controller.signal
      );
      if (requestSequence.current === sequence) setDelegates(result.delegates);
    } catch (error) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setDelegates([]);
      setListError(delegationErrorMessage(error));
    } finally {
      if (requestSequence.current === sequence) {
        readController.current = null;
        setIsLoading(false);
      }
    }
  }, [organizationId, owner.primary_email]);

  useEffect(() => {
    requestSequence.current += 1;
    readController.current?.abort();
    setDelegates([]);
    setDelegateEmail("");
    setListError(null);
    setActionFeedback(null);
    setPendingPreview(null);
    setAmbiguousChange(null);
    setIsPreviewing(false);
    setIsMutating(false);
    setIsReconciling(false);
    reconciliationInFlight.current = false;
    void loadDelegates();
    return () => readController.current?.abort();
  }, [loadDelegates]);

  async function previewChange(operation: "create" | "remove", email: string) {
    const normalizedEmail = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setActionFeedback({ type: "error", message: "Enter a valid full email address." });
      return;
    }
    if (!canMutate || isPreviewing || isMutating || isReconciling || ambiguousChange) return;

    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setIsPreviewing(true);
    setActionFeedback(null);
    try {
      const preview = await previewGmailDelegateChange(
        organizationId,
        operation,
        owner.primary_email,
        normalizedEmail,
        controller.signal
      );
      if (requestSequence.current === sequence) setPendingPreview(preview);
    } catch (error) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setActionFeedback({ type: "error", message: delegationErrorMessage(error) });
    } finally {
      if (requestSequence.current === sequence) {
        readController.current = null;
        setIsPreviewing(false);
      }
    }
  }

  async function handleAddSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await previewChange("create", delegateEmail);
  }

  async function reconcileAmbiguousChange(change: AmbiguousChange, sequence: number) {
    if (reconciliationInFlight.current) return;
    reconciliationInFlight.current = true;
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    setIsReconciling(true);
    setActionFeedback({
      type: "info",
      message: "Google did not confirm the mutation response. Checking the current state without resubmitting the change…"
    });
    try {
      const result = await reconcileGmailDelegateChange(
        organizationId,
        change.preview.operation,
        change.preview.confirmation_token,
        controller.signal
      );
      if (requestSequence.current !== sequence) return;
      if (result.status === "verified") {
        setAmbiguousChange(null);
        setActionFeedback({ type: "success", message: result.message });
        setIsReconciling(false);
        reconciliationInFlight.current = false;
        await loadDelegates(true);
        return;
      }
      setActionFeedback({ type: "warning", message: result.message });
    } catch (error) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setActionFeedback({
        type: "warning",
        message: `The outcome is still unknown. ${delegationErrorMessage(error)} The original change was not resubmitted.`
      });
    } finally {
      if (requestSequence.current === sequence) {
        readController.current = null;
        setIsReconciling(false);
        reconciliationInFlight.current = false;
      }
    }
  }

  async function confirmChange() {
    if (!pendingPreview || isMutating || isReconciling || ambiguousChange) return;
    const preview = pendingPreview;
    const sequence = requestSequence.current;
    setIsMutating(true);
    setActionFeedback(null);
    try {
      const result = await executeGmailDelegateChange(
        organizationId,
        preview.operation,
        preview.confirmation_token
      );
      if (requestSequence.current !== sequence) return;
      setPendingPreview(null);
      setDelegateEmail("");
      setActionFeedback({ type: "success", message: result.message });
      setIsMutating(false);
      await loadDelegates(true);
    } catch (error) {
      if (requestSequence.current !== sequence) return;
      setPendingPreview(null);
      if (isAmbiguousMutationError(error)) {
        const change = { preview };
        setAmbiguousChange(change);
        setIsMutating(false);
        await reconcileAmbiguousChange(change, sequence);
      } else {
        setActionFeedback({ type: "error", message: delegationErrorMessage(error) });
      }
    } finally {
      if (requestSequence.current === sequence) setIsMutating(false);
    }
  }

  const writeLocked =
    isPreviewing || isMutating || isReconciling || ambiguousChange !== null;

  return (
    <section className="mailbox-delegates" aria-labelledby="mailbox-delegates-heading">
      <div className="mailbox-delegates-heading">
        <div>
          <span className="eyebrow">Gmail administration</span>
          <h4 id="mailbox-delegates-heading">Mailbox Delegates</h4>
          <p>
            Mailbox owner <strong>{owner.primary_email}</strong>
          </p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void loadDelegates()}
          disabled={isLoading || isPreviewing || isMutating || isReconciling}
        >
          <RefreshCw className={isLoading ? "spin" : ""} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {listError ? (
        <div className="delegate-state error" role="alert">
          <AlertCircle aria-hidden="true" />
          <span>{listError}</span>
        </div>
      ) : isLoading ? (
        <div className="delegate-state" role="status">
          <Loader2 className="spin" aria-hidden="true" />
          Loading Gmail delegates…
        </div>
      ) : delegates.length === 0 ? (
        <div className="delegate-state" role="status">
          <UsersRound aria-hidden="true" />
          <span><strong>No delegates</strong>This mailbox has no delegated users.</span>
        </div>
      ) : (
        <div className="delegate-list" aria-label={`${delegates.length} mailbox delegates`}>
          <div className="delegate-list-summary">
            {delegates.length} delegate{delegates.length === 1 ? "" : "s"}
          </div>
          {delegates.map((delegate) => (
            <div className="delegate-row" key={delegate.primary_email}>
              <div>
                <strong>{delegate.primary_email}</strong>
                <span className={`verification-status ${delegate.verification_status}`}>
                  {verificationLabel(delegate)}
                </span>
              </div>
              <button
                type="button"
                className="danger-button"
                onClick={() => void previewChange("remove", delegate.primary_email)}
                disabled={!canMutate || writeLocked}
                title={canMutate ? "Remove delegate" : "Administrator access required"}
              >
                <Trash2 aria-hidden="true" />
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      <form className="delegate-add-form" onSubmit={handleAddSubmit} noValidate>
        <label htmlFor="delegate-email">
          Add delegate by primary email or alias
          <input
            id="delegate-email"
            type="email"
            autoComplete="off"
            value={delegateEmail}
            onChange={(event) => setDelegateEmail(event.target.value)}
            placeholder="delegate@example.com"
            disabled={!canMutate || writeLocked}
          />
        </label>
        <button
          type="submit"
          disabled={!canMutate || !delegateEmail.trim() || writeLocked}
        >
          {isPreviewing ? <Loader2 className="spin" aria-hidden="true" /> : <MailPlus aria-hidden="true" />}
          {isPreviewing ? "Validating" : "Review delegate"}
        </button>
      </form>
      {!canMutate && (
        <p className="delegate-permission-note">
          <ShieldAlert aria-hidden="true" /> Administrator access is required to change delegates.
        </p>
      )}

      {actionFeedback && (
        <div
          className={`delegate-state ${actionFeedback.type}`}
          role={actionFeedback.type === "error" ? "alert" : "status"}
          aria-live="polite"
        >
          {actionFeedback.type === "success" ? (
            <CheckCircle2 aria-hidden="true" />
          ) : actionFeedback.type === "info" ? (
            <Loader2 className="spin" aria-hidden="true" />
          ) : (
            <AlertCircle aria-hidden="true" />
          )}
          <span>{actionFeedback.message}</span>
        </div>
      )}

      {ambiguousChange && (
        <div className="delegate-reconciliation" aria-label="Ambiguous delegate change">
          <div>
            <strong>Outcome unknown</strong>
            <span>
              Google did not confirm whether access for {ambiguousChange.preview.delegate_primary_email}
              {ambiguousChange.preview.operation === "create" ? " was granted" : " was revoked"}.
              Checking status only reads the delegate list and never repeats the change.
            </span>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              void reconcileAmbiguousChange(ambiguousChange, requestSequence.current)
            }
            disabled={isReconciling}
          >
            {isReconciling && <Loader2 className="spin" aria-hidden="true" />}
            {isReconciling ? "Checking status" : "Check status"}
          </button>
        </div>
      )}

      {pendingPreview && (
        <div className="confirmation-backdrop" role="presentation">
          <section
            className="confirmation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delegate-confirmation-title"
          >
            <button
              type="button"
              className="dialog-close"
              onClick={() => setPendingPreview(null)}
              aria-label="Cancel delegate change"
              disabled={isMutating}
            >
              <X aria-hidden="true" />
            </button>
            <span className={`confirmation-icon ${pendingPreview.operation}`}>
              {pendingPreview.operation === "create" ? (
                <MailPlus aria-hidden="true" />
              ) : (
                <Trash2 aria-hidden="true" />
              )}
            </span>
            <h3 id="delegate-confirmation-title">
              {pendingPreview.operation === "create" ? "Grant mailbox access?" : "Revoke mailbox access?"}
            </h3>
            <dl className="confirmation-identities">
              <div><dt>Mailbox owner</dt><dd>{pendingPreview.owner_primary_email}</dd></div>
              <div><dt>Delegate</dt><dd>{pendingPreview.delegate_primary_email}</dd></div>
            </dl>
            <p>{pendingPreview.effect}</p>
            <div className="confirmation-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPendingPreview(null)}
                disabled={isMutating}
              >
                Cancel
              </button>
              <button
                type="button"
                className={pendingPreview.operation === "remove" ? "danger-button" : ""}
                onClick={() => void confirmChange()}
                disabled={isMutating}
              >
                {isMutating && <Loader2 className="spin" aria-hidden="true" />}
                {pendingPreview.operation === "create" ? "Grant access" : "Revoke access"}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
