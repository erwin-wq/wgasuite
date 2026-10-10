import {
  AlertCircle,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  FileKey2,
  Loader2,
  PlayCircle,
  ServerCog,
  ShieldCheck,
  Upload
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  importGoogleWorkspaceCredential,
  selectExternalGoogleWorkspaceCredential
} from "../../api/client";
import type { ConnectorConfig } from "../../types";

export const DIRECTORY_USER_READONLY_SCOPE =
  "https://www.googleapis.com/auth/admin.directory.user.readonly";

type Feedback = { type: "success" | "error"; message: string } | null;

interface ConnectionWizardProps {
  connectorConfig: ConnectorConfig | null;
  organizationSelected: boolean;
  canManageCredentials: boolean;
  displayName: string;
  primaryDomain: string;
  adminSubjectEmail: string;
  notes: string;
  isSaving: boolean;
  isTesting: boolean;
  feedback: Feedback;
  onDisplayNameChange: (value: string) => void;
  onPrimaryDomainChange: (value: string) => void;
  onAdminSubjectEmailChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onSave: () => Promise<ConnectorConfig | null>;
  onTest: () => Promise<void>;
  onReload: () => Promise<void>;
  onCredentialFeedback: (feedback: Feedback) => void;
}

const steps = [
  "Google Cloud",
  "Credentials",
  "Domain delegation",
  "Admin subject",
  "Test connection"
];

function initialStep(config: ConnectorConfig | null): number {
  if (config?.last_tested_at) return 5;
  if (config?.admin_subject_email && config.credentials_configured) return 5;
  if (config?.service_account_client_id) return 3;
  if (config) return 2;
  return 1;
}

function formatDateTime(value: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value)
  );
}

export function ConnectionWizard({
  connectorConfig,
  organizationSelected,
  canManageCredentials,
  displayName,
  primaryDomain,
  adminSubjectEmail,
  notes,
  isSaving,
  isTesting,
  feedback,
  onDisplayNameChange,
  onPrimaryDomainChange,
  onAdminSubjectEmailChange,
  onNotesChange,
  onSave,
  onTest,
  onReload,
  onCredentialFeedback
}: ConnectionWizardProps) {
  const [step, setStep] = useState(() => initialStep(connectorConfig));
  const [credentialMode, setCredentialMode] = useState<"upload" | "external">("upload");
  const [credentialFile, setCredentialFile] = useState<File | null>(null);
  const [externalReference, setExternalReference] = useState("");
  const [isCredentialSaving, setIsCredentialSaving] = useState(false);
  const [copied, setCopied] = useState<"client" | "scope" | null>(null);
  const initializedConfigId = useRef<string | null>(connectorConfig?.id ?? null);

  useEffect(() => {
    if (connectorConfig && initializedConfigId.current !== connectorConfig.id) {
      initializedConfigId.current = connectorConfig.id;
      setStep(initialStep(connectorConfig));
    }
  }, [connectorConfig]);

  async function ensureConfig(): Promise<ConnectorConfig | null> {
    return connectorConfig ?? onSave();
  }

  async function uploadCredential() {
    if (!credentialFile) {
      onCredentialFeedback({ type: "error", message: "Select a JSON service-account key file." });
      return;
    }
    setIsCredentialSaving(true);
    onCredentialFeedback(null);
    try {
      const config = await ensureConfig();
      if (!config) return;
      await importGoogleWorkspaceCredential(config.id, credentialFile);
      await onReload();
      onCredentialFeedback({
        type: "success",
        message: "Credential validated and stored. The connection must still be tested."
      });
      setStep(3);
    } catch (error) {
      onCredentialFeedback({ type: "error", message: (error as Error).message });
    } finally {
      setIsCredentialSaving(false);
    }
  }

  async function selectExternalCredential() {
    if (!externalReference.trim()) return;
    setIsCredentialSaving(true);
    onCredentialFeedback(null);
    try {
      const config = await ensureConfig();
      if (!config) return;
      await selectExternalGoogleWorkspaceCredential(config.id, externalReference.trim());
      await onReload();
      onCredentialFeedback({
        type: "success",
        message: "Provisioned credential validated. The connection must still be tested."
      });
      setStep(3);
    } catch (error) {
      onCredentialFeedback({ type: "error", message: (error as Error).message });
    } finally {
      setIsCredentialSaving(false);
    }
  }

  async function copy(value: string, target: "client" | "scope") {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(target);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      onCredentialFeedback({
        type: "error",
        message: "Clipboard access is unavailable. Select and copy the value manually."
      });
    }
  }

  async function saveAdminSubject() {
    const config = await onSave();
    if (config) setStep(5);
  }

  const testDisabled =
    !connectorConfig?.credentials_configured || !adminSubjectEmail.trim() || isTesting || isSaving;
  const canOpenStep = (number: number) => {
    if (!organizationSelected) return false;
    if (number <= 2) return true;
    if (number <= 4) return Boolean(connectorConfig?.service_account_client_id);
    return Boolean(connectorConfig?.credentials_configured && connectorConfig.admin_subject_email);
  };

  return (
    <div className="connection-wizard">
      <nav className="wizard-steps" aria-label="Google Workspace setup progress">
        {steps.map((label, index) => {
          const number = index + 1;
          return (
            <button
              type="button"
              key={label}
              className={number === step ? "active" : number < step ? "complete" : ""}
              aria-current={number === step ? "step" : undefined}
              onClick={() => setStep(number)}
              disabled={!canOpenStep(number)}
            >
              <span>{number < step ? "✓" : number}</span>
              {label}
            </button>
          );
        })}
      </nav>

      <section className="wizard-body" aria-labelledby={`wizard-step-${step}`}>
        {step === 1 && (
          <div className="wizard-section">
            <p className="eyebrow">Step 1 of 5</p>
            <h3 id="wizard-step-1">Prepare a Google Cloud project</h3>
            <ol className="wizard-instructions">
              <li>Select or create the Google Cloud project used for this connector.</li>
              <li>Enable the Admin SDK API.</li>
              <li>Create a service account and enable domain-wide delegation.</li>
              <li>Create and download a JSON key. WGASuite cannot create this in Google Cloud.</li>
            </ol>
            <div className="wizard-links">
              <a href="https://developers.google.com/workspace/guides/enable-apis" target="_blank" rel="noreferrer">
                Enable Workspace APIs <ExternalLink aria-hidden="true" />
              </a>
              <a href="https://developers.google.com/workspace/guides/create-credentials#service-account" target="_blank" rel="noreferrer">
                Create service-account credentials <ExternalLink aria-hidden="true" />
              </a>
            </div>
            <div className="wizard-footer">
              <span />
              <button type="button" onClick={() => setStep(2)} disabled={!organizationSelected}>
                Continue to credentials
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="wizard-section">
            <p className="eyebrow">Step 2 of 5</p>
            <h3 id="wizard-step-2">Provide the service-account credential</h3>
            <p className="wizard-lead">
              Only customer admins can change credentials. Private key content is never returned by
              the API or shown again in the browser.
            </p>
            {!canManageCredentials && (
              <div className="helper-note"><ShieldCheck aria-hidden="true" />Customer admin access is required.</div>
            )}
            <fieldset className="credential-options" disabled={!canManageCredentials}>
              <legend>Credential source</legend>
              <label className={credentialMode === "upload" ? "selected" : ""}>
                <input type="radio" name="credential-mode" checked={credentialMode === "upload"} onChange={() => setCredentialMode("upload")} />
                <Upload aria-hidden="true" />
                <span><strong>Upload JSON key</strong><small>Recommended. Stored in WGASuite's protected backend volume.</small></span>
              </label>
              <label className={credentialMode === "external" ? "selected" : ""}>
                <input type="radio" name="credential-mode" checked={credentialMode === "external"} onChange={() => setCredentialMode("external")} />
                <ServerCog aria-hidden="true" />
                <span><strong>Existing server file</strong><small>Use a file provisioned by an operator outside the application.</small></span>
              </label>
            </fieldset>

            {credentialMode === "upload" ? (
              <div className="credential-entry">
                <label>
                  Service-account JSON file
                  <input type="file" accept="application/json,.json" onChange={(event) => setCredentialFile(event.target.files?.[0] ?? null)} disabled={!canManageCredentials || isCredentialSaving} />
                </label>
                <button type="button" onClick={uploadCredential} disabled={!credentialFile || !canManageCredentials || isCredentialSaving}>
                  {isCredentialSaving ? <Loader2 className="spin" aria-hidden="true" /> : <FileKey2 aria-hidden="true" />}
                  Validate and store
                </button>
              </div>
            ) : (
              <div className="credential-entry">
                <label>
                  Provisioned credential reference
                  <input value={externalReference} onChange={(event) => setExternalReference(event.target.value)} placeholder="workspace-production" pattern="[A-Za-z0-9][A-Za-z0-9._-]*" maxLength={128} disabled={!canManageCredentials || isCredentialSaving} />
                </label>
                <button type="button" onClick={selectExternalCredential} disabled={!externalReference.trim() || !canManageCredentials || isCredentialSaving}>
                  {isCredentialSaving ? <Loader2 className="spin" aria-hidden="true" /> : <ServerCog aria-hidden="true" />}
                  Validate and use reference
                </button>
              </div>
            )}
            <div className="wizard-footer">
              <button type="button" className="secondary-button" onClick={() => setStep(1)}>Back</button>
              <button type="button" onClick={() => setStep(3)} disabled={!connectorConfig?.service_account_client_id}>Continue</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="wizard-section">
            <p className="eyebrow">Step 3 of 5</p>
            <h3 id="wizard-step-3">Authorize domain-wide delegation</h3>
            <ol className="wizard-instructions">
              <li>Sign in to the Google Admin console as a super administrator.</li>
              <li>Open Security → Access and data control → API controls.</li>
              <li>Open Manage Domain Wide Delegation and choose Add new.</li>
              <li>Paste the numeric client ID and exact OAuth scope below, then authorize.</li>
            </ol>
            <div className="copy-field">
              <span>Numeric client ID</span>
              <code>{connectorConfig?.service_account_client_id ?? "Upload or validate a credential first"}</code>
              <button type="button" className="secondary-button" onClick={() => copy(connectorConfig?.service_account_client_id ?? "", "client")} disabled={!connectorConfig?.service_account_client_id}>
                <Clipboard aria-hidden="true" />{copied === "client" ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="copy-field">
              <span>OAuth scope (exact value)</span>
              <code>{DIRECTORY_USER_READONLY_SCOPE}</code>
              <button type="button" className="secondary-button" onClick={() => copy(DIRECTORY_USER_READONLY_SCOPE, "scope")}>
                <Clipboard aria-hidden="true" />{copied === "scope" ? "Copied" : "Copy"}
              </button>
            </div>
            <a className="inline-doc-link" href="https://support.google.com/a/answer/162106" target="_blank" rel="noreferrer">
              Google Admin domain-wide delegation guide <ExternalLink aria-hidden="true" />
            </a>
            <div className="wizard-footer">
              <button type="button" className="secondary-button" onClick={() => setStep(2)}>Back</button>
              <button type="button" onClick={() => setStep(4)} disabled={!connectorConfig?.service_account_client_id}>Delegation is authorized</button>
            </div>
          </div>
        )}

        {step === 4 && (
          <form className="wizard-section form-stack" onSubmit={(event) => { event.preventDefault(); void saveAdminSubject(); }}>
            <p className="eyebrow">Step 4 of 5</p>
            <h3 id="wizard-step-4">Choose the delegated administrator</h3>
            <p className="wizard-lead">Use an active Google Workspace administrator allowed to read users. Any valid Workspace domain is accepted.</p>
            <label>Display name<input value={displayName} onChange={(event) => onDisplayNameChange(event.target.value)} required /></label>
            <label>Primary domain (optional)<input value={primaryDomain} onChange={(event) => onPrimaryDomainChange(event.target.value)} placeholder="example.com" /></label>
            <label>Admin subject email<input type="email" value={adminSubjectEmail} onChange={(event) => onAdminSubjectEmailChange(event.target.value)} placeholder="workspace-admin@example.com" required /></label>
            <label>Notes (optional)<textarea value={notes} onChange={(event) => onNotesChange(event.target.value)} rows={3} /></label>
            <div className="wizard-footer">
              <button type="button" className="secondary-button" onClick={() => setStep(3)}>Back</button>
              <button type="submit" disabled={!displayName.trim() || !adminSubjectEmail.trim() || isSaving}>
                {isSaving && <Loader2 className="spin" aria-hidden="true" />}Save and continue
              </button>
            </div>
          </form>
        )}

        {step === 5 && (
          <div className="wizard-section">
            <p className="eyebrow">Step 5 of 5</p>
            <h3 id="wizard-step-5">Test the real Google Workspace connection</h3>
            <div className="connector-summary">
              <div><span>Status</span><strong><span className={`connector-status connector-status-${connectorConfig?.status.replace("_", "-") ?? "not-configured"}`}>{connectorConfig?.status === "configured" && !connectorConfig.last_tested_at ? "untested" : connectorConfig?.status.replace("_", " ") ?? "not configured"}</span></strong></div>
              <div><span>Last tested</span><strong>{formatDateTime(connectorConfig?.last_tested_at ?? null)}</strong></div>
              <div><span>Service account</span><strong title={connectorConfig?.service_account_email ?? ""}>{connectorConfig?.service_account_email ?? "-"}</strong></div>
              <div><span>Admin subject</span><strong>{connectorConfig?.admin_subject_email ?? "-"}</strong></div>
            </div>
            <p className="connector-disclaimer">This manual test makes one read-only Admin SDK Directory API request for the configured administrator. It does not run automatically and does not test Gmail or write access.</p>
            {connectorConfig?.last_error && (
              <div className="message error" aria-live="polite"><AlertCircle aria-hidden="true" /><span><strong>{connectorConfig.last_error_code}</strong>: {connectorConfig.last_error}</span></div>
            )}
            <div className="wizard-footer">
              <button type="button" className="secondary-button" onClick={() => setStep(4)}>Back</button>
              <button type="button" onClick={() => void onTest()} disabled={testDisabled} aria-busy={isTesting}>
                {isTesting ? <Loader2 className="spin" aria-hidden="true" /> : <PlayCircle aria-hidden="true" />}{isTesting ? "Testing…" : "Test connection"}
              </button>
            </div>
          </div>
        )}
      </section>

      {feedback && (
        <section className={`message connector-message ${feedback.type}`} aria-live="polite">
          {feedback.type === "error" ? <AlertCircle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
          <span>{feedback.message}</span>
        </section>
      )}
    </div>
  );
}
