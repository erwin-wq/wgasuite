import {
  AlertCircle,
  AtSign,
  Building2,
  CheckCircle2,
  FolderTree,
  Mail,
  MailCheck,
  Search,
  ShieldCheck,
  UserRound,
  X
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { lookupGoogleWorkspaceUser } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Feedback";
import { Input } from "../../components/ui/FormControls";
import type { ConnectorConfig, GoogleWorkspaceUser } from "../../types";
import { MailboxDelegates } from "./MailboxDelegates";
import { UserGroupMemberships } from "./UserGroupMemberships";
import { UserOrgUnitMove } from "./UserOrgUnitMove";
import { UserStatusManagement } from "./UserStatusManagement";
import {
  administratorLabel,
  googleWorkspaceUserLookupError,
  mailboxSetupLabel
} from "./googleWorkspaceUserPresentation";

interface UserLookupProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canSearch: boolean;
  canManageDelegates: boolean;
  initialEmail?: string | null;
  onOpenGroup: (groupEmail: string) => void;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const matchLabels = {
  primary_email: "Matched primary email",
  alias: "Matched editable alias",
  non_editable_alias: "Matched non-editable alias"
};

function formatDirectoryTime(value: string | null): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export function UserLookup({
  organizationId,
  organizationName,
  connectorConfig,
  canSearch,
  canManageDelegates,
  initialEmail = null,
  onOpenGroup
}: UserLookupProps) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<GoogleWorkspaceUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestSequence = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const connectorReady = connectorConfig?.status === "connected";

  const runLookup = useCallback(async (email: string) => {
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
      const user = await lookupGoogleWorkspaceUser(organizationId, email, controller.signal);
      if (requestSequence.current === sequence) setResult(user);
    } catch (lookupError) {
      if (controller.signal.aborted || requestSequence.current !== sequence) return;
      setError(googleWorkspaceUserLookupError(lookupError));
    } finally {
      if (requestSequence.current === sequence) {
        requestController.current = null;
        setIsLoading(false);
      }
    }
  }, [canSearch, connectorReady, organizationId]);

  useEffect(() => {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setQuery("");
    setResult(null);
    setError(null);
    setIsLoading(false);
  }, [organizationId]);

  useEffect(() => {
    if (!initialEmail) return;
    const normalizedEmail = initialEmail.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) return;
    setQuery(normalizedEmail);
    void runLookup(normalizedEmail);
  }, [initialEmail, runLookup]);

  useEffect(() => {
    if (result) resultHeading.current?.focus();
  }, [result]);

  function clearLookup() {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setQuery("");
    setResult(null);
    setError(null);
    setIsLoading(false);
    searchInput.current?.focus();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedQuery)) {
      setResult(null);
      setError("Enter a valid full email address.");
      return;
    }
    await runLookup(normalizedQuery);
  }

  const announcement = isLoading
    ? "Searching the Google Workspace Directory."
    : error
      ? error
      : result
        ? `User found: ${result.full_name ?? result.primary_email}.`
        : "";

  return (
    <div className="user-lookup">
      <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>

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
          Connect and successfully test Google Workspace for {organizationName ?? "this organization"}{" "}
          before searching.
        </div>
      ) : (
        <>
          <form className="user-lookup-form" onSubmit={handleSubmit} noValidate>
            <Input
              ref={searchInput}
              id="workspace-user-query"
              className="user-lookup-field"
              label="Primary email or user alias"
              hint="Enter one complete address. Partial names, wildcards, and bulk searches are not supported."
              leadingIcon={<AtSign />}
              type="email"
              autoComplete="off"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                if (error) setError(null);
              }}
              placeholder="person@example.com"
              disabled={isLoading}
            />
            <div className="user-lookup-actions">
              <Button type="submit" loading={isLoading} loadingLabel="" disabled={!query.trim()}>
                {isLoading ? null : <Search aria-hidden="true" />}
                {isLoading ? "Searching" : "Look up user"}
              </Button>
              <Button type="button" variant="secondary" onClick={clearLookup} disabled={!query && !result && !error}>
                <X aria-hidden="true" /> Clear
              </Button>
            </div>
          </form>

          {error ? (
            <div className="user-lookup-state error" role="alert">
              <AlertCircle aria-hidden="true" />
              {error}
            </div>
          ) : null}

          {result ? (
            <article className="user-result-card" aria-label="Google Workspace user result">
              <header className="user-result-heading">
                <div className="user-result-avatar" aria-hidden="true"><UserRound /></div>
                <div className="user-result-identity">
                  <h3 ref={resultHeading} tabIndex={-1}>{result.full_name ?? "Name unavailable"}</h3>
                  <span>{result.primary_email}</span>
                </div>
                <div className="user-result-summary-item">
                  <span>Account status</span>
                  <Badge
                    variant={result.suspended ? "danger" : "success"}
                    icon={result.suspended ? <AlertCircle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
                  >
                    {result.suspended ? "Suspended" : "Active"}
                  </Badge>
                </div>
                <div className="user-result-summary-item user-result-match">
                  <span>Match evidence</span>
                  <strong>{matchLabels[result.matched_by]}</strong>
                </div>
              </header>

              <div className="user-detail-layout">
                <div className="user-detail-primary">
                  <section className="user-detail-section" aria-labelledby="lookup-identity-heading">
                    <div className="user-detail-section-heading">
                      <ShieldCheck aria-hidden="true" />
                      <h4 id="lookup-identity-heading">Identity &amp; status</h4>
                    </div>
                    <dl className="user-result-details user-result-details--columns">
                      <div><dt>Administrator role</dt><dd>{administratorLabel(result)}</dd></div>
                      <div><dt>Archived</dt><dd>{result.archived === null ? "Unknown" : result.archived ? "Yes" : "No"}</dd></div>
                      {result.suspended ? <div><dt>Suspension reason</dt><dd>{result.suspension_reason ?? "Not verified"}</dd></div> : null}
                      <div><dt>Created</dt><dd>{formatDirectoryTime(result.creation_time)}</dd></div>
                      <div><dt>Last sign-in</dt><dd>{formatDirectoryTime(result.last_login_time)}</dd></div>
                    <div><dt>Gmail status</dt><dd>{mailboxSetupLabel(result.is_mailbox_setup)}</dd></div>
                    </dl>
                  </section>

                  <section className="user-detail-section" aria-labelledby="lookup-aliases-heading">
                    <div className="user-detail-section-heading">
                      <Mail aria-hidden="true" />
                      <h4 id="lookup-aliases-heading">Email addresses</h4>
                    </div>
                    <div className="user-email-groups">
                      <div><strong>Primary email</strong><div className="alias-list"><span>{result.primary_email}</span></div></div>
                      <div>
                        <strong>User aliases</strong>
                        <div className="alias-list">
                          {result.aliases.length > 0 ? result.aliases.map((alias) => <span key={alias}>{alias}</span>) : <em>No editable aliases</em>}
                        </div>
                      </div>
                      <div>
                        <strong>Non-editable aliases</strong>
                        <div className="alias-list">
                          {result.non_editable_aliases.length > 0 ? result.non_editable_aliases.map((alias) => <span key={alias}>{alias}</span>) : <em>No non-editable aliases</em>}
                        </div>
                      </div>
                    </div>
                  </section>

                  <section className="user-detail-section" aria-labelledby="lookup-workspace-heading">
                    <div className="user-detail-section-heading">
                      <FolderTree aria-hidden="true" />
                      <h4 id="lookup-workspace-heading">Organizational unit</h4>
                    </div>
                    <dl className="user-result-details">
                      <div><dt>Current path</dt><dd>{result.org_unit_path ?? "Not available"}</dd></div>
                    </dl>
                  </section>

                  <UserGroupMemberships organizationId={organizationId} user={result} onOpenGroup={onOpenGroup} />
                </div>

                <aside className="user-administration-actions" aria-labelledby="user-actions-heading">
                  <div className="user-administration-heading">
                    <ShieldCheck aria-hidden="true" />
                    <div>
                      <h4 id="user-actions-heading">Administration actions</h4>
                      <p>Protected workflows revalidate this account before making a change.</p>
                    </div>
                  </div>
                  <UserStatusManagement
                    organizationId={organizationId}
                    connectorConfig={connectorConfig}
                    user={result}
                    canMutate={canManageDelegates}
                    onRefresh={() => runLookup(result.primary_email)}
                  />
                  <UserOrgUnitMove
                    organizationId={organizationId}
                    connectorConfig={connectorConfig}
                    user={result}
                    canMutate={canManageDelegates}
                    onRefresh={() => runLookup(result.primary_email)}
                  />
                </aside>
              </div>

              <div className="user-result-note">
                <MailCheck aria-hidden="true" />
                Live Directory result. Mailbox setup does not imply Gmail delegation or access.
              </div>

              <MailboxDelegates organizationId={organizationId} owner={result} canMutate={canManageDelegates} />
            </article>
          ) : null}
        </>
      )}
    </div>
  );
}
