import { AlertTriangle, CheckCircle2, Edit3, Loader2, X } from "lucide-react";
import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState
} from "react";

import {
  ApiError,
  executeGoogleWorkspaceOrganizationalUnitDescription,
  previewGoogleWorkspaceOrganizationalUnitDescription,
  reconcileGoogleWorkspaceOrganizationalUnitDescription
} from "../../api/client";
import type {
  GoogleWorkspaceOrganizationalUnitDescriptionPreview,
  GoogleWorkspaceOrganizationalUnitTreeNode
} from "../../types";
import { DIRECTORY_ORGUNIT_WRITE_SCOPE } from "./OrganizationalUnitCreation";

interface OrganizationalUnitDescriptionProps {
  organizationId: string;
  unit: GoogleWorkspaceOrganizationalUnitTreeNode;
  onUpdated: () => Promise<void>;
}

function descriptionErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The description could not be updated safely. Refresh the hierarchy before trying again.";
  }
  if (["missing_scope_or_permission", "delegation_rejected", "google_forbidden"].includes(error.code ?? "")) {
    return `Google denied the update. Authorize ${DIRECTORY_ORGUNIT_WRITE_SCOPE} for this connector and verify that the delegated administrator can update Organizational Units.`;
  }
  if (error.code === "google_orgunit_description_unchanged") {
    return "Enter a description that differs from the current value.";
  }
  if (error.code === "google_orgunit_description_target_protected") {
    return "The root and Workspace Guests system units cannot be edited.";
  }
  if ([
    "google_orgunit_description_confirmation_expired",
    "google_orgunit_description_confirmation_used",
    "google_orgunit_description_state_changed"
  ].includes(error.code ?? "")) {
    return "The Organizational Unit or confirmation changed. Close this dialog, refresh, and review a new preview.";
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited the request. Wait before creating a new preview.";
  }
  return error.message;
}

function displayDescription(value: string | null): string {
  return value ?? "No description";
}

export function OrganizationalUnitDescription({
  organizationId,
  unit,
  onUpdated
}: OrganizationalUnitDescriptionProps) {
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [preview, setPreview] =
    useState<GoogleWorkspaceOrganizationalUnitDescriptionPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const controller = useRef<AbortController | null>(null);
  const normalizedDescription = description.trim();
  const currentDescription = unit.description ?? "";
  const unchanged = normalizedDescription === currentDescription;

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (open) textarea.current?.focus();
  }, [open]);

  function openDialog() {
    setSuccess(null);
    setDescription(unit.description ?? "");
    setPreview(null);
    setError(null);
    setOpen(true);
  }

  function close() {
    if (busy) return;
    controller.current?.abort();
    setOpen(false);
    setDescription("");
    setPreview(null);
    setError(null);
    trigger.current?.focus();
  }

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      dialog.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      ) ?? []
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function requestPreview(event: FormEvent) {
    event.preventDefault();
    if (busy || unchanged) return;
    const nextController = new AbortController();
    controller.current?.abort();
    controller.current = nextController;
    setBusy(true);
    setError(null);
    try {
      setPreview(
        await previewGoogleWorkspaceOrganizationalUnitDescription(
          organizationId,
          unit.id,
          description,
          nextController.signal
        )
      );
    } catch (requestError) {
      if (!nextController.signal.aborted) setError(descriptionErrorMessage(requestError));
    } finally {
      if (controller.current === nextController) {
        controller.current = null;
        setBusy(false);
      }
    }
  }

  async function confirmUpdate() {
    if (!preview || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await executeGoogleWorkspaceOrganizationalUnitDescription(
        organizationId,
        preview.confirmation_token
      );
      setSuccess(result.message);
      await onUpdated();
      closeAfterSuccess();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.reconciliationAvailable) {
        try {
          const reconciled = await reconcileGoogleWorkspaceOrganizationalUnitDescription(
            organizationId,
            preview.confirmation_token
          );
          if (reconciled.status === "verified") {
            setSuccess(reconciled.message);
            await onUpdated();
            closeAfterSuccess();
            return;
          }
          setError("Google's final description is still unknown. Refresh before considering another update.");
        } catch (reconciliationError) {
          setError(descriptionErrorMessage(reconciliationError));
        }
      } else {
        setError(descriptionErrorMessage(requestError));
      }
    } finally {
      setBusy(false);
    }
  }

  function closeAfterSuccess() {
    setOpen(false);
    setDescription("");
    setPreview(null);
    setError(null);
    trigger.current?.focus();
  }

  return (
    <>
      <button ref={trigger} type="button" className="secondary-button" onClick={openDialog}>
        <Edit3 aria-hidden="true" /> Edit description
      </button>
      {success ? (
        <p className="ou-create-success" role="status">
          <CheckCircle2 aria-hidden="true" /> {success}
        </p>
      ) : null}
      {open ? (
        <div
          className="confirmation-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <section
            ref={dialog}
            className="confirmation-dialog ou-create-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ou-description-heading"
            aria-describedby="ou-description-warning"
            onKeyDown={handleDialogKeyDown}
          >
            <button
              type="button"
              className="dialog-close"
              aria-label="Close description dialog"
              onClick={close}
              disabled={busy}
            >
              <X aria-hidden="true" />
            </button>
            <div>
              <span className="eyebrow">Selected unit</span>
              <h3 id="ou-description-heading">Edit OU description</h3>
              <p><strong>{unit.name}</strong> · {unit.path}</p>
            </div>
            {!preview ? (
              <form className="ou-create-form" onSubmit={(event) => void requestPreview(event)}>
                <div className="ou-create-path">
                  <span>Current description</span>
                  <strong>{displayDescription(unit.description)}</strong>
                </div>
                <label>
                  New description <span>(leave empty to clear)</span>
                  <textarea
                    ref={textarea}
                    value={description}
                    maxLength={4096}
                    rows={5}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </label>
                <p id="ou-description-warning" className="ou-create-warning">
                  <AlertTriangle aria-hidden="true" /> Only the description will change. The name,
                  path, parent, users, and effective policies are not modified.
                </p>
                {error ? <p className="form-error" role="alert">{error}</p> : null}
                <div className="confirmation-actions">
                  <button type="button" className="secondary-button" onClick={close}>Cancel</button>
                  <button type="submit" className="primary-button" disabled={busy || unchanged}>
                    {busy ? <Loader2 className="spin" aria-hidden="true" /> : null} Review change
                  </button>
                </div>
              </form>
            ) : (
              <div className="ou-create-confirmation">
                <dl className="confirmation-identities">
                  <div><dt>Organizational Unit</dt><dd>{preview.path}</dd></div>
                  <div><dt>Original</dt><dd>{displayDescription(preview.original_description)}</dd></div>
                  <div><dt>Proposed</dt><dd>{displayDescription(preview.proposed_description)}</dd></div>
                </dl>
                <p id="ou-description-warning" className="ou-create-warning">
                  <AlertTriangle aria-hidden="true" /> {preview.effect}
                </p>
                {error ? <p className="form-error" role="alert">{error}</p> : null}
                <div className="confirmation-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => { setPreview(null); setError(null); }}
                    disabled={busy}
                  >
                    Back
                  </button>
                  <button type="button" className="primary-button" onClick={() => void confirmUpdate()} disabled={busy}>
                    {busy ? <Loader2 className="spin" aria-hidden="true" /> : null} Confirm description update once
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </>
  );
}
