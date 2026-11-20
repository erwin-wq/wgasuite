import { CircleAlert, MailPlus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  executeGmailDelegateChange,
  listGmailDelegates,
  previewGmailDelegateChange,
  reconcileGmailDelegateChange
} from "../../api/client";
import { Button } from "../../components/ui/Button";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Alert, Badge } from "../../components/ui/Feedback";
import { Input } from "../../components/ui/FormControls";
import { Modal } from "../../components/ui/Modal";
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
  const mutationInFlight = useRef(false);
  const addTriggerRef = useRef<HTMLButtonElement>(null);
  const previewTriggerRef = useRef<HTMLElement | null>(null);

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
    mutationInFlight.current = false;
    void loadDelegates();
    return () => readController.current?.abort();
  }, [loadDelegates]);

  async function previewChange(
    operation: "create" | "remove",
    email: string,
    trigger?: HTMLElement | null
  ) {
    const normalizedEmail = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setActionFeedback({ type: "error", message: "Enter a valid full email address." });
      return;
    }
    if (!canMutate || isPreviewing || isMutating || isReconciling || ambiguousChange) return;
    previewTriggerRef.current = trigger ?? null;

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
    await previewChange("create", delegateEmail, addTriggerRef.current);
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
    if (
      !pendingPreview ||
      mutationInFlight.current ||
      isMutating ||
      isReconciling ||
      ambiguousChange
    ) return;
    mutationInFlight.current = true;
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
      mutationInFlight.current = false;
      if (requestSequence.current === sequence) setIsMutating(false);
    }
  }

  const writeLocked =
    isPreviewing || isMutating || isReconciling || ambiguousChange !== null;
  const columns: DataTableColumn<GmailDelegate>[] = [
    {
      id: "delegate",
      header: "Delegate",
      cell: (delegate) => <span className="delegate-address">{delegate.primary_email}</span>
    },
    {
      id: "status",
      header: "Status",
      cell: (delegate) => (
        <Badge
          variant={
            delegate.verification_status === "accepted"
              ? "success"
              : delegate.verification_status === "rejected"
                ? "danger"
                : "warning"
          }
        >
          {verificationLabel(delegate)}
        </Badge>
      )
    },
    {
      id: "actions",
      header: <span className="sr-only">Delegate actions</span>,
      cell: (delegate) => (
        <Button
          variant="danger"
          size="sm"
          onClick={(event) =>
            void previewChange("remove", delegate.primary_email, event.currentTarget)
          }
          disabled={!canMutate || writeLocked}
          title={canMutate ? "Remove delegate" : "Administrator access required"}
        >
          <Trash2 aria-hidden="true" /> Remove
        </Button>
      )
    }
  ];

  return (
    <section className="mailbox-delegates" aria-labelledby="mailbox-delegates-heading">
      <div className="mailbox-delegates-heading">
        <div>
          <h4 id="mailbox-delegates-heading">Existing delegates</h4>
          <p>Direct Gmail mailbox delegates reported by Google.</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          loading={isLoading}
          loadingLabel="Refreshing delegates"
          onClick={() => void loadDelegates()}
          disabled={isPreviewing || isMutating || isReconciling}
        >
          <RefreshCw aria-hidden="true" /> Refresh
        </Button>
      </div>

      <DataTable
        ariaLabel={`Gmail delegates for ${owner.primary_email}`}
        columns={columns}
        rows={delegates}
        rowKey={(delegate) => delegate.primary_email}
        loading={isLoading}
        error={listError}
        errorTitle="Delegates could not be loaded"
        onRetry={() => void loadDelegates()}
        emptyTitle="No delegates"
        emptyDescription="This mailbox has no delegated users."
        minWidth="38rem"
        className="delegate-data-table"
      />

      <section className="delegate-add-panel" aria-labelledby="delegate-add-heading">
        <div className="delegate-add-heading">
          <h4 id="delegate-add-heading">Grant mailbox access</h4>
          <p>Add an eligible internal user. You will review the exact change before it is submitted.</p>
        </div>
        <form className="delegate-add-form" onSubmit={handleAddSubmit} noValidate>
          <Input
            id="delegate-email"
            label="Delegate primary email or alias"
            hint="Enter one complete internal address. Partial names, wildcards, and bulk changes are not supported."
            type="email"
            autoComplete="off"
            value={delegateEmail}
            onChange={(event) => setDelegateEmail(event.target.value)}
            placeholder="delegate@example.com"
            disabled={!canMutate || writeLocked}
          />
          <Button
            ref={addTriggerRef}
            type="submit"
            loading={isPreviewing}
            loadingLabel="Validating delegate"
            disabled={!canMutate || !delegateEmail.trim() || writeLocked}
          >
            <MailPlus aria-hidden="true" /> Review delegate
          </Button>
        </form>
        <Alert variant="info" icon={<ShieldCheck />}>
          Changes require review and explicit confirmation before they are submitted.
        </Alert>
      </section>
      {!canMutate && (
        <Alert variant="warning" title="Read-only access">
          Administrator access is required to change delegates.
        </Alert>
      )}

      {actionFeedback && (
        <Alert
          variant={actionFeedback.type === "error" ? "danger" : actionFeedback.type}
          aria-live="polite"
        >
          {actionFeedback.message}
        </Alert>
      )}

      {ambiguousChange && (
        <Alert
          className="delegate-reconciliation"
          variant="warning"
          title="Outcome unknown"
          icon={<CircleAlert />}
          aria-label="Ambiguous delegate change"
        >
          <p>
            Google did not confirm whether access for {ambiguousChange.preview.delegate_primary_email}
            {ambiguousChange.preview.operation === "create" ? " was granted" : " was revoked"}.
            Checking status only reads the delegate list and never repeats the change.
          </p>
          <Button
            variant="secondary"
            size="sm"
            loading={isReconciling}
            loadingLabel="Checking status"
            onClick={() =>
              void reconcileAmbiguousChange(ambiguousChange, requestSequence.current)
            }
          >
            <RefreshCw aria-hidden="true" /> Check status
          </Button>
        </Alert>
      )}

      <Modal
        open={pendingPreview !== null}
        onClose={() => setPendingPreview(null)}
        title={pendingPreview?.operation === "remove" ? "Revoke mailbox access?" : "Grant mailbox access?"}
        description="Review this protected change before submitting it to Google."
        restoreFocusRef={previewTriggerRef}
        closeDisabled={isMutating}
        className="delegate-confirmation-modal"
        footer={pendingPreview ? (
          <>
            <Button variant="secondary" onClick={() => setPendingPreview(null)} disabled={isMutating}>
              Cancel
            </Button>
            <Button
              variant={pendingPreview.operation === "remove" ? "danger" : "primary"}
              loading={isMutating}
              loadingLabel="Submitting delegate change"
              onClick={() => void confirmChange()}
            >
              {pendingPreview.operation === "create" ? "Grant access" : "Revoke access"}
            </Button>
          </>
        ) : null}
      >
        {pendingPreview ? (
          <div className="delegate-confirmation-content">
            <dl className="confirmation-identities">
              <div><dt>Mailbox owner</dt><dd>{pendingPreview.owner_primary_email}</dd></div>
              <div><dt>Delegate</dt><dd>{pendingPreview.delegate_primary_email}</dd></div>
              <div><dt>Effect</dt><dd>{pendingPreview.effect}</dd></div>
            </dl>
            <Alert variant="warning">This confirmation is single-use and expires automatically.</Alert>
          </div>
        ) : null}
      </Modal>
    </section>
  );
}
