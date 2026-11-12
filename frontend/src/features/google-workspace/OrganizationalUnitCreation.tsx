import { AlertTriangle, CheckCircle2, Loader2, Plus, X } from "lucide-react";
import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import {
  ApiError,
  executeGoogleWorkspaceOrganizationalUnitCreation,
  previewGoogleWorkspaceOrganizationalUnitCreation,
  reconcileGoogleWorkspaceOrganizationalUnitCreation
} from "../../api/client";
import type {
  GoogleWorkspaceOrganizationalUnitCreatePreview,
  GoogleWorkspaceOrganizationalUnitTreeNode
} from "../../types";

export const DIRECTORY_ORGUNIT_WRITE_SCOPE =
  "https://www.googleapis.com/auth/admin.directory.orgunit";

interface OrganizationalUnitCreationProps {
  organizationId: string;
  parent: GoogleWorkspaceOrganizationalUnitTreeNode;
  onCreated: () => Promise<void>;
}

function createErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The Organizational Unit could not be created safely. Refresh the hierarchy before trying again.";
  }
  if (["missing_scope_or_permission", "delegation_rejected", "google_forbidden"].includes(error.code ?? "")) {
    return `Google denied creation. Authorize ${DIRECTORY_ORGUNIT_WRITE_SCOPE} for the connector's Domain-Wide Delegation client and verify the delegated administrator can create Organizational Units.`;
  }
  if (error.code === "google_orgunit_already_exists") {
    return "An Organizational Unit with that name already exists under this parent.";
  }
  if (error.code === "google_orgunit_parent_protected") {
    return "This system Organizational Unit cannot contain new child units.";
  }
  if (["google_orgunit_create_confirmation_expired", "google_orgunit_create_confirmation_used", "google_orgunit_create_state_changed"].includes(error.code ?? "")) {
    return "The hierarchy or confirmation changed. Close this dialog, refresh, and review a new preview.";
  }
  if (error.code === "google_rate_limited") return "Google rate-limited the request. Wait before creating a new preview.";
  return error.message;
}

export function OrganizationalUnitCreation({ organizationId, parent, onCreated }: OrganizationalUnitCreationProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [preview, setPreview] = useState<GoogleWorkspaceOrganizationalUnitCreatePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const controller = useRef<AbortController | null>(null);
  const expectedPath = useMemo(() => {
    const normalized = name.trim();
    if (!normalized) return null;
    return parent.path === "/" ? `/${normalized}` : `${parent.path}/${normalized}`;
  }, [name, parent.path]);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (open) nameInput.current?.focus();
  }, [open]);

  function close() {
    if (busy) return;
    controller.current?.abort();
    setOpen(false);
    setName("");
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
        'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
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
    if (!name.trim() || busy) return;
    const nextController = new AbortController();
    controller.current?.abort();
    controller.current = nextController;
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewGoogleWorkspaceOrganizationalUnitCreation(
        organizationId,
        parent.id,
        name,
        description.trim() || null,
        nextController.signal
      ));
    } catch (requestError) {
      if (!nextController.signal.aborted) setError(createErrorMessage(requestError));
    } finally {
      if (controller.current === nextController) {
        controller.current = null;
        setBusy(false);
      }
    }
  }

  async function confirmCreation() {
    if (!preview || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await executeGoogleWorkspaceOrganizationalUnitCreation(
        organizationId,
        preview.confirmation_token
      );
      setSuccess(result.message);
      await onCreated();
      closeAfterSuccess();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.reconciliationAvailable) {
        try {
          const reconciled = await reconcileGoogleWorkspaceOrganizationalUnitCreation(
            organizationId,
            preview.confirmation_token
          );
          if (reconciled.status === "verified") {
            setSuccess(reconciled.message);
            await onCreated();
            closeAfterSuccess();
            return;
          }
          setError("Google's result is still unknown. Refresh the hierarchy before considering another creation.");
        } catch (reconciliationError) {
          setError(createErrorMessage(reconciliationError));
        }
      } else {
        setError(createErrorMessage(requestError));
      }
    } finally {
      setBusy(false);
    }
  }

  function closeAfterSuccess() {
    setOpen(false);
    setName("");
    setDescription("");
    setPreview(null);
    setError(null);
    trigger.current?.focus();
  }

  return (
    <>
      <button ref={trigger} type="button" className="primary-button" onClick={() => { setSuccess(null); setOpen(true); }}>
        <Plus aria-hidden="true" /> Create child OU
      </button>
      {success && <p className="ou-create-success" role="status"><CheckCircle2 aria-hidden="true" /> {success}</p>}
      {open && (
        <div className="confirmation-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
          <section ref={dialog} className="confirmation-dialog ou-create-dialog" role="dialog" aria-modal="true" aria-labelledby="ou-create-heading" aria-describedby="ou-create-policy-warning" onKeyDown={handleDialogKeyDown}>
            <button type="button" className="dialog-close" aria-label="Close creation dialog" onClick={close} disabled={busy}><X aria-hidden="true" /></button>
            <div>
              <span className="eyebrow">Selected parent</span>
              <h3 id="ou-create-heading">Create Organizational Unit</h3>
              <p><strong>{parent.name}</strong> · {parent.path}</p>
            </div>
            {!preview ? (
              <form className="ou-create-form" onSubmit={(event) => void requestPreview(event)}>
                <label>Name<input ref={nameInput} value={name} maxLength={256} required onChange={(event) => setName(event.target.value)} /></label>
                <label>Description <span>(optional)</span><textarea value={description} maxLength={4096} rows={3} onChange={(event) => setDescription(event.target.value)} /></label>
                <div className="ou-create-path"><span>Resulting path</span><strong>{expectedPath ?? "Enter a name"}</strong></div>
                <p id="ou-create-policy-warning" className="ou-create-warning"><AlertTriangle aria-hidden="true" /> New child units normally inherit settings from their parent. The Directory API does not verify effective policy inheritance.</p>
                {error && <p className="form-error" role="alert">{error}</p>}
                <div className="confirmation-actions">
                  <button type="button" className="secondary-button" onClick={close}>Cancel</button>
                  <button type="submit" className="primary-button" disabled={busy || !name.trim() || name.includes("/")}>{busy && <Loader2 className="spin" aria-hidden="true" />} Review creation</button>
                </div>
              </form>
            ) : (
              <div className="ou-create-confirmation">
                <dl className="confirmation-identities">
                  <div><dt>Parent</dt><dd>{preview.parent_path}</dd></div>
                  <div><dt>New path</dt><dd>{preview.expected_path}</dd></div>
                  <div><dt>Description</dt><dd>{preview.description ?? "No description"}</dd></div>
                </dl>
                <p id="ou-create-policy-warning" className="ou-create-warning"><AlertTriangle aria-hidden="true" /> {preview.effect}</p>
                {error && <p className="form-error" role="alert">{error}</p>}
                <div className="confirmation-actions">
                  <button type="button" className="secondary-button" onClick={() => { setPreview(null); setError(null); }} disabled={busy}>Back</button>
                  <button type="button" className="primary-button" onClick={() => void confirmCreation()} disabled={busy}>{busy && <Loader2 className="spin" aria-hidden="true" />} Confirm and create once</button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
