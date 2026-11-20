import {
  AtSign,
  Building2,
  FolderTree,
  MailCheck,
  Search,
  ShieldCheck,
  UserRound
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { lookupGoogleWorkspaceUser } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Badge, Alert, EmptyState } from "../../components/ui/Feedback";
import { Input } from "../../components/ui/FormControls";
import type { ConnectorConfig, GoogleWorkspaceUser } from "../../types";
import { MailboxDelegates } from "./MailboxDelegates";
import {
  administratorLabel,
  googleWorkspaceUserLookupError,
  mailboxSetupLabel
} from "./googleWorkspaceUserPresentation";

interface GmailDelegationManagementProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canSearch: boolean;
  canManageDelegates: boolean;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function GmailDelegationManagement({
  organizationId,
  organizationName,
  connectorConfig,
  canSearch,
  canManageDelegates
}: GmailDelegationManagementProps) {
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState<GoogleWorkspaceUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestSequence = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const ownerHeadingRef = useRef<HTMLHeadingElement>(null);
  const connectorReady = connectorConfig?.status === "connected";

  const runLookup = useCallback(async (email: string) => {
    if (!organizationId || !connectorReady || !canSearch) return;
    requestController.current?.abort();
    const controller = new AbortController();
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    requestController.current = controller;
    setOwner(null);
    setError(null);
    setIsLoading(true);
    try {
      const result = await lookupGoogleWorkspaceUser(organizationId, email, controller.signal);
      if (requestSequence.current === sequence) setOwner(result);
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
    setOwner(null);
    setError(null);
    setIsLoading(false);
  }, [organizationId]);

  useEffect(() => {
    if (owner) ownerHeadingRef.current?.focus();
  }, [owner]);

  function clearLookup() {
    requestSequence.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setQuery("");
    setOwner(null);
    setError(null);
    setIsLoading(false);
    inputRef.current?.focus();
  }

  function submitLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = query.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalized)) {
      setOwner(null);
      setError("Enter a valid full email address.");
      return;
    }
    void runLookup(normalized);
  }

  const announcement = isLoading
    ? "Searching the Google Workspace Directory."
    : error
      ? error
      : owner
        ? `Mailbox selected: ${owner.full_name ?? owner.primary_email}.`
        : "";

  return (
    <section className="gmail-delegation-management" aria-label="Gmail delegation workflow">
      <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
      {!organizationId ? (
        <Alert variant="warning" icon={<Building2 />}>
          Select an organization before searching for a mailbox.
        </Alert>
      ) : !canSearch ? (
        <Alert variant="warning" title="Search unavailable">
          Administrator access is required to search Directory users.
        </Alert>
      ) : !connectorReady ? (
        <Alert variant="warning" title="Connection required">
          Connect and successfully test Google Workspace for {organizationName ?? "this organization"} before searching.
        </Alert>
      ) : (
        <>
          <section className="gmail-mailbox-lookup" aria-labelledby="mailbox-lookup-heading">
            <div>
              <h3 id="mailbox-lookup-heading">Mailbox lookup</h3>
              <p>Use a complete primary email address or user alias. Mailbox addresses never enter the URL.</p>
            </div>
            <form onSubmit={submitLookup} noValidate>
              <Input
                ref={inputRef}
                label="Primary email or user alias"
                hint="Enter one complete address. Partial names, wildcards, and bulk searches are not supported."
                leadingIcon={<AtSign />}
                type="email"
                autoComplete="off"
                value={query}
                error={error ?? undefined}
                onChange={(event) => {
                  setQuery(event.target.value);
                  if (error) setError(null);
                }}
              />
              <div className="gmail-mailbox-lookup-actions">
                <Button type="submit" loading={isLoading} loadingLabel="Finding mailbox" disabled={!query.trim()}>
                  <Search aria-hidden="true" /> Find mailbox
                </Button>
                <Button variant="secondary" onClick={clearLookup} disabled={!query && !owner && !error}>
                  Clear
                </Button>
              </div>
            </form>
          </section>

          {owner ? (
            <div className="gmail-selected-mailbox">
              <section className="gmail-mailbox-identity" aria-labelledby="selected-mailbox-heading">
                <div className="gmail-mailbox-owner">
                  <span className="gmail-mailbox-owner-icon"><UserRound aria-hidden="true" /></span>
                  <div>
                    <h3 ref={ownerHeadingRef} id="selected-mailbox-heading" tabIndex={-1}>
                      {owner.full_name ?? "Name unavailable"}
                    </h3>
                    <p>{owner.primary_email}</p>
                  </div>
                  <Badge variant={owner.suspended ? "warning" : "success"}>
                    {owner.suspended ? "Suspended" : "Active"}
                  </Badge>
                </div>
                <dl className="gmail-mailbox-facts">
                  <div><dt><MailCheck aria-hidden="true" /> Mailbox</dt><dd>{mailboxSetupLabel(owner.is_mailbox_setup)}</dd></div>
                  <div><dt><ShieldCheck aria-hidden="true" /> Access level</dt><dd>{administratorLabel(owner)}</dd></div>
                  <div><dt><FolderTree aria-hidden="true" /> Organizational unit</dt><dd>{owner.org_unit_path ?? "Not available"}</dd></div>
                </dl>
              </section>
              <MailboxDelegates organizationId={organizationId} owner={owner} canMutate={canManageDelegates} />
            </div>
          ) : !error && !isLoading ? (
            <EmptyState title="Select a mailbox" icon={<MailCheck aria-hidden="true" />}>
              Look up one internal Google Workspace user to view and manage direct Gmail delegates.
            </EmptyState>
          ) : null}
        </>
      )}
    </section>
  );
}
