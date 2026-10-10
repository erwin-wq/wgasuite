import { CheckCircle2, Clipboard, ExternalLink, MailCheck, ShieldAlert } from "lucide-react";
import { useState } from "react";

import type { ConnectorConfig } from "../../types";
import { DIRECTORY_USER_READONLY_SCOPE } from "./ConnectionWizard";

export const GMAIL_DELEGATE_READ_SCOPE =
  "https://www.googleapis.com/auth/gmail.settings.basic";
export const GMAIL_DELEGATE_WRITE_SCOPE =
  "https://www.googleapis.com/auth/gmail.settings.sharing";

interface GmailDelegationAuthorizationProps {
  connectorConfig: ConnectorConfig | null;
}

type CopyTarget = "client" | "directory" | "read" | "write" | "all";

export function GmailDelegationAuthorization({
  connectorConfig
}: GmailDelegationAuthorizationProps) {
  const [copied, setCopied] = useState<CopyTarget | null>(null);
  const [copyError, setCopyError] = useState(false);
  const allScopes = [
    DIRECTORY_USER_READONLY_SCOPE,
    GMAIL_DELEGATE_READ_SCOPE,
    GMAIL_DELEGATE_WRITE_SCOPE
  ].join(",");

  async function copy(value: string, target: CopyTarget) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyError(false);
      setCopied(target);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopyError(true);
    }
  }

  const fields: Array<{ label: string; value: string; target: CopyTarget }> = [
    {
      label: "Directory user lookup (preserve)",
      value: DIRECTORY_USER_READONLY_SCOPE,
      target: "directory"
    },
    { label: "Read Gmail delegates", value: GMAIL_DELEGATE_READ_SCOPE, target: "read" },
    { label: "Create and remove Gmail delegates", value: GMAIL_DELEGATE_WRITE_SCOPE, target: "write" }
  ];

  return (
    <section className="gmail-authorization" aria-labelledby="gmail-authorization-heading">
      <div className="workspace-section-heading">
        <div>
          <span className="eyebrow">Separate authorization</span>
          <h2 id="gmail-authorization-heading">Gmail delegation authorization</h2>
          <p>
            Directory connection, Gmail delegate reads, and Gmail delegate writes are independent
            capabilities.
          </p>
        </div>
      </div>

      <div className="gmail-capability-grid">
        <div className={connectorConfig?.status === "connected" ? "verified" : "unverified"}>
          <CheckCircle2 aria-hidden="true" />
          <span>Directory user lookup</span>
          <strong>{connectorConfig?.status === "connected" ? "Verified" : "Not verified"}</strong>
        </div>
        <div className="unverified">
          <MailCheck aria-hidden="true" />
          <span>Gmail delegates readable</span>
          <strong>Verify by loading a mailbox</strong>
        </div>
        <div className="unverified">
          <ShieldAlert aria-hidden="true" />
          <span>Gmail delegate writes</span>
          <strong>Not tested automatically</strong>
        </div>
      </div>

      <ol className="wizard-instructions">
        <li>Enable the Gmail API in the same Google Cloud project.</li>
        <li>Open Security → Access and data control → API controls in Google Admin.</li>
        <li>Open Manage Domain Wide Delegation and edit the existing numeric client ID.</li>
        <li>Add both Gmail scopes below and preserve the Directory read-only scope.</li>
        <li>Look up a mailbox owner and load delegates to verify read access.</li>
      </ol>

      <div className="copy-field">
        <span>Existing service-account numeric client ID</span>
        <code>{connectorConfig?.service_account_client_id ?? "Validate a credential first"}</code>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void copy(connectorConfig?.service_account_client_id ?? "", "client")}
          disabled={!connectorConfig?.service_account_client_id}
        >
          <Clipboard aria-hidden="true" />{copied === "client" ? "Copied" : "Copy"}
        </button>
      </div>

      {fields.map((field) => (
        <div className="copy-field" key={field.value}>
          <span>{field.label}</span>
          <code>{field.value}</code>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void copy(field.value, field.target)}
          >
            <Clipboard aria-hidden="true" />{copied === field.target ? "Copied" : "Copy"}
          </button>
        </div>
      ))}

      <div className="copy-field emphasized">
        <span>All required scopes (comma-separated)</span>
        <code>{allScopes}</code>
        <button type="button" className="secondary-button" onClick={() => void copy(allScopes, "all")}>
          <Clipboard aria-hidden="true" />{copied === "all" ? "Copied" : "Copy all"}
        </button>
      </div>

      {copyError && (
        <p className="message error" role="alert">
          Clipboard access is unavailable. Select and copy the value manually.
        </p>
      )}
      <div className="wizard-links">
        <a
          href="https://developers.google.com/workspace/gmail/api/guides/delegate_settings"
          target="_blank"
          rel="noreferrer"
        >
          Gmail delegate guide <ExternalLink aria-hidden="true" />
        </a>
        <a href="https://support.google.com/a/answer/162106" target="_blank" rel="noreferrer">
          Domain-wide delegation guide <ExternalLink aria-hidden="true" />
        </a>
      </div>
      <p className="connector-disclaimer">
        WGASuite never changes Google Admin domain-wide delegation grants. A successful Directory
        test does not prove either Gmail capability.
      </p>
    </section>
  );
}
