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
  previewGmailDelegateChange
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
    { type: "success" | "error"; message: string } | null
  >(null);
  const [pendingPreview, setPendingPreview] = useState<GmailDelegateChangePreview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const requestSequence = useRef(0);
  const readController = useRef<AbortController | null>(null);

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
    void loadDelegates();
    return () => readController.current?.abort();
  }, [loadDelegates]);

  async function previewChange(operation: "create" | "remove", email: string) {
    const normalizedEmail = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setActionFeedback({ type: "error", message: "Enter a valid full email address." });
      return;
    }
    if (!canMutate || isPreviewing || isMutating) return;

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

  async function confirmChange() {
    if (!pendingPreview || isMutating) return;
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
      setActionFeedback({ type: "error", message: delegationErrorMessage(error) });
    } finally {
      if (requestSequence.current === sequence) setIsMutating(false);
    }
  }

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
          disabled={isLoading || isPreviewing || isMutating}
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
                disabled={!canMutate || isPreviewing || isMutating}
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
            disabled={!canMutate || isPreviewing || isMutating}
          />
        </label>
        <button
          type="submit"
          disabled={!canMutate || !delegateEmail.trim() || isPreviewing || isMutating}
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
        <div className={`delegate-state ${actionFeedback.type}`} role="status" aria-live="polite">
          {actionFeedback.type === "success" ? (
            <CheckCircle2 aria-hidden="true" />
          ) : (
            <AlertCircle aria-hidden="true" />
          )}
          <span>{actionFeedback.message}</span>
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
