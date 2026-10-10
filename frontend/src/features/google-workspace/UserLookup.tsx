import {
  AlertCircle,
  AtSign,
  Building2,
  CheckCircle2,
  Loader2,
  MailCheck,
  Search,
  UserRound,
  X
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, lookupGoogleWorkspaceUser } from "../../api/client";
import type { ConnectorConfig, GoogleWorkspaceUser } from "../../types";

interface UserLookupProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canSearch: boolean;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const matchLabels = {
  primary_email: "Matched primary email",
  alias: "Matched editable alias",
  non_editable_alias: "Matched non-editable alias"
};

function lookupErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The lookup could not be completed. Check your connection and try again.";
  }

  if (error.status === 404 || error.code === "google_user_not_found") {
    return "No Directory user was found for that address. Google Group addresses are not included.";
  }
  if (error.code === "missing_scope_or_permission" || error.code === "google_forbidden") {
    return "Google denied this lookup. Verify the delegated administrator and the authorized read-only Directory scope.";
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited the lookup. Wait a moment and try again.";
  }
  if (
    error.code === "google_service_unavailable" ||
    error.code === "google_network_error" ||
    error.code === "google_timeout"
  ) {
    return "Google is temporarily unavailable. Try the lookup again shortly.";
  }
  if (
    error.status === 409 ||
    error.code === "connector_not_configured" ||
    error.code === "credentials_not_found"
  ) {
    return "The Google Workspace connector is not ready. Complete and test the connection first.";
  }
  if (error.status === 403) {
    return "You do not have permission to search users for this organization.";
  }
  return error.message;
}

function mailboxLabel(value: boolean | null): string {
  if (value === true) return "Gmail mailbox set up";
  if (value === false) return "Gmail mailbox not set up";
  return "Mailbox setup unknown";
}

export function UserLookup({
  organizationId,
  organizationName,
  connectorConfig,
  canSearch
}: UserLookupProps) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<GoogleWorkspaceUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestSequence = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const connectorReady = connectorConfig?.status === "connected";

  useEffect(() => {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setQuery("");
    setResult(null);
    setError(null);
    setIsLoading(false);
  }, [organizationId]);

  function clearLookup() {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setQuery("");
    setResult(null);
    setError(null);
    setIsLoading(false);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedQuery)) {
      setResult(null);
      setError("Enter a valid full email address.");
      return;
    }
    if (!organizationId || !connectorReady || !canSearch) return;

    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setResult(null);
    setError(null);
    setIsLoading(true);

    try {
      const user = await lookupGoogleWorkspaceUser(
        organizationId,
        normalizedQuery,
        controller.signal
      );
      if (requestSequence.current === sequence) setResult(user);
    } catch (lookupError) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setError(lookupErrorMessage(lookupError));
    } finally {
      if (requestSequence.current === sequence) {
        requestController.current = null;
        setIsLoading(false);
      }
    }
  }

  return (
    <div className="user-lookup">
      <div className="panel-heading">
        <div>
          <h2>User &amp; Alias Lookup</h2>
          <p>
            Search by a primary email address or user alias to view the canonical Directory account.
          </p>
        </div>
      </div>

      {!organizationId ? (
        <div className="user-lookup-state" role="status">
          <Building2 aria-hidden="true" />
          Select an organization before searching.
        </div>
      ) : !canSearch ? (
        <div className="user-lookup-state warning" role="status">
          <AlertCircle aria-hidden="true" />
          Administrator access is required to search Directory users.
        </div>
      ) : !connectorReady ? (
        <div className="user-lookup-state warning" role="status">
          <AlertCircle aria-hidden="true" />
          Connect and successfully test Google Workspace for {organizationName ?? "this organization"}
          {" "}before searching.
        </div>
      ) : (
        <>
          <form className="user-lookup-form" onSubmit={handleSubmit} noValidate>
            <label htmlFor="workspace-user-query">
              Primary email or user alias
              <span className="user-lookup-input-row">
                <AtSign aria-hidden="true" />
                <input
                  id="workspace-user-query"
                  type="email"
                  autoComplete="off"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    if (error) setError(null);
                  }}
                  placeholder="alias@example.com"
                  disabled={isLoading}
                />
              </span>
            </label>
            <div className="user-lookup-actions">
              <button type="submit" disabled={isLoading || !query.trim()}>
                {isLoading ? <Loader2 className="spin" aria-hidden="true" /> : <Search aria-hidden="true" />}
                {isLoading ? "Searching" : "Look up user"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={clearLookup}
                disabled={!query && !result && !error}
              >
                <X aria-hidden="true" />
                Clear
              </button>
            </div>
          </form>

          {error && (
            <div className="user-lookup-state error" role="alert">
              <AlertCircle aria-hidden="true" />
              {error}
            </div>
          )}

          {result && (
            <article className="user-result-card" aria-label="Google Workspace user result">
              <div className="user-result-heading">
                <div className="user-result-avatar" aria-hidden="true">
                  <UserRound />
                </div>
                <div>
                  <h3>{result.full_name ?? "Name unavailable"}</h3>
                  <a href={`mailto:${result.primary_email}`}>{result.primary_email}</a>
                </div>
                <div className="user-result-badges">
                  <span className="status-neutral">{matchLabels[result.matched_by]}</span>
                </div>
              </div>

              <div className="user-result-grid">
                <section aria-labelledby="lookup-identity-heading">
                  <h4 id="lookup-identity-heading">Identity &amp; status</h4>
                  <dl className="user-result-details">
                    <div>
                      <dt>Account status</dt>
                      <dd>
                        <span className={result.suspended ? "status-danger" : "status-success"}>
                          {result.suspended ? "Suspended" : "Active"}
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt>Archived</dt>
                      <dd>{result.archived === null ? "Unknown" : result.archived ? "Yes" : "No"}</dd>
                    </div>
                  </dl>
                </section>

                <section aria-labelledby="lookup-aliases-heading">
                  <h4 id="lookup-aliases-heading">Email addresses &amp; aliases</h4>
                  <strong>Primary address</strong>
                  <div className="alias-list">
                    <span>{result.primary_email}</span>
                  </div>
                  <strong>Editable in Google Workspace</strong>
                  <div className="alias-list">
                    {result.aliases.length > 0 ? (
                      result.aliases.map((alias) => <span key={alias}>{alias}</span>)
                    ) : (
                      <em>No editable aliases</em>
                    )}
                  </div>
                  <strong>Non-editable aliases</strong>
                  <div className="alias-list">
                    {result.non_editable_aliases.length > 0 ? (
                      result.non_editable_aliases.map((alias) => <span key={alias}>{alias}</span>)
                    ) : (
                      <em>No non-editable aliases</em>
                    )}
                  </div>
                </section>

                <section aria-labelledby="lookup-workspace-heading">
                  <h4 id="lookup-workspace-heading">Workspace details</h4>
                  <dl className="user-result-details">
                    <div>
                      <dt><Building2 aria-hidden="true" /> Organizational unit</dt>
                      <dd>{result.org_unit_path ?? "Not available"}</dd>
                    </div>
                    <div>
                      <dt><MailCheck aria-hidden="true" /> Gmail status</dt>
                      <dd>{mailboxLabel(result.is_mailbox_setup)}</dd>
                    </div>
                  </dl>
                </section>
              </div>

              <div className="user-result-note">
                <CheckCircle2 aria-hidden="true" />
                Read-only Directory result. Mailbox setup does not imply Gmail delegation or access.
              </div>
            </article>
          )}
        </>
      )}
    </div>
  );
}
