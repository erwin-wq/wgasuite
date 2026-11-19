import {
  ArrowLeft,
  ArrowRight,
  AtSign,
  Mail,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  UsersRound
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  executeGroupMembershipChange,
  getGoogleWorkspaceGroup,
  listGoogleWorkspaceGroupMembers,
  previewGroupMembershipChange,
  reconcileGroupMembershipChange,
  searchGoogleWorkspaceGroups
} from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { DataTable, DataTablePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { Alert, Badge, EmptyState } from "../../components/ui/Feedback";
import { Input, SearchField } from "../../components/ui/FormControls";
import { Modal } from "../../components/ui/Modal";
import type {
  GoogleWorkspaceGroup,
  GoogleWorkspaceGroupMember,
  GroupMembershipPreview
} from "../../types";

interface GroupManagementProps {
  organizationId: string;
  canSearch: boolean;
  canMutate: boolean;
  initialGroupEmail?: string | null;
  navigationRequestId?: number;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const AMBIGUOUS_CODES = new Set([
  "google_timeout",
  "google_network_error",
  "google_service_unavailable"
]);

function groupErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The Google Groups request could not be completed. Check the connection and try again.";
  }
  const messages: Record<string, string> = {
    google_group_not_found: "This group no longer exists in the selected Workspace customer.",
    google_tenant_mismatch: "The group or user does not belong to the selected Workspace customer.",
    group_member_already_exists: "That user is already a direct member. Refresh the member list.",
    group_member_not_found: "That direct membership no longer exists. Refresh the member list.",
    group_member_unsupported: "Only direct, internal users can be changed. External and nested members are read-only.",
    group_owner_protected: "Owner memberships are protected. Manage ownership in Google Admin first.",
    group_membership_unsupported: "Google does not allow this group membership to be changed through the Directory API.",
    group_confirmation_invalid: "The confirmation is no longer valid. Review the operation again.",
    group_confirmation_expired: "The confirmation expired. Review the operation again.",
    group_confirmation_used: "This change was already submitted. Refresh members before continuing.",
    missing_scope_or_permission: "Authorize the Directory group scope and verify the delegated administrator's Groups privilege.",
    google_rate_limited: "Google rate-limited this request. Wait before trying again."
  };
  if (error.code && messages[error.code]) return messages[error.code];
  if (AMBIGUOUS_CODES.has(error.code ?? "")) {
    return "Google did not return a reliable result. The change was not retried.";
  }
  if (error.status === 403) return "Administrator access is required for this organization.";
  return error.message;
}

function memberLabel(member: GoogleWorkspaceGroupMember): string {
  if (member.type === "GROUP") return "Nested group";
  if (member.type === "CUSTOMER") return "Entire customer";
  if (member.type === "EXTERNAL") return "External";
  if (member.type === "USER") return "User";
  return "Unsupported";
}

function roleVariant(role: GoogleWorkspaceGroupMember["role"]): "neutral" | "info" | "warning" {
  if (role === "OWNER") return "warning";
  if (role === "MANAGER") return "info";
  return "neutral";
}

function statusVariant(status: string | null): "neutral" | "success" | "warning" {
  if (status === "ACTIVE") return "success";
  if (status === "SUSPENDED") return "warning";
  return "neutral";
}

export function GroupManagement({
  organizationId,
  canSearch,
  canMutate,
  initialGroupEmail = null,
  navigationRequestId
}: GroupManagementProps) {
  const [query, setQuery] = useState("");
  const [groups, setGroups] = useState<GoogleWorkspaceGroup[]>([]);
  const [groupTokens, setGroupTokens] = useState<Array<string | null>>([null]);
  const [groupPage, setGroupPage] = useState(0);
  const [groupNextToken, setGroupNextToken] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<GoogleWorkspaceGroup | null>(null);
  const [members, setMembers] = useState<GoogleWorkspaceGroupMember[]>([]);
  const [memberTokens, setMemberTokens] = useState<Array<string | null>>([null]);
  const [memberPage, setMemberPage] = useState(0);
  const [memberNextToken, setMemberNextToken] = useState<string | null>(null);
  const [memberEmail, setMemberEmail] = useState("");
  const [pendingPreview, setPendingPreview] = useState<GroupMembershipPreview | null>(null);
  const [ambiguousPreview, setAmbiguousPreview] = useState<GroupMembershipPreview | null>(null);
  const [groupError, setGroupError] = useState<string | null>(null);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<
    { type: "success" | "error" | "warning" | "info"; message: string } | null
  >(null);
  const [isGroupsLoading, setIsGroupsLoading] = useState(false);
  const [isMembersLoading, setIsMembersLoading] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [isReconciling, setIsReconciling] = useState(false);
  const requestSequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const reconciliationInFlight = useRef(false);
  const mutationInFlight = useRef(false);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const confirmationTrigger = useRef<HTMLElement | null>(null);

  const loadGroups = useCallback(
    async (searchQuery: string, pageToken: string | null, pageIndex: number) => {
      controller.current?.abort();
      const nextController = new AbortController();
      controller.current = nextController;
      const sequence = requestSequence.current + 1;
      requestSequence.current = sequence;
      setIsGroupsLoading(true);
      setGroupError(null);
      try {
        const result = await searchGoogleWorkspaceGroups(
          organizationId,
          searchQuery,
          pageToken,
          nextController.signal
        );
        if (requestSequence.current !== sequence) return;
        setGroups(result.groups);
        setGroupPage(pageIndex);
        setGroupNextToken(result.next_page_token);
      } catch (error) {
        if (nextController.signal.aborted || requestSequence.current !== sequence) return;
        setGroups([]);
        setGroupError(groupErrorMessage(error));
      } finally {
        if (requestSequence.current === sequence) setIsGroupsLoading(false);
      }
    },
    [organizationId]
  );

  const loadMembers = useCallback(
    async (
      group: GoogleWorkspaceGroup,
      pageToken: string | null,
      pageIndex: number,
      preserveFeedback = false
    ) => {
      controller.current?.abort();
      const nextController = new AbortController();
      controller.current = nextController;
      const sequence = requestSequence.current + 1;
      requestSequence.current = sequence;
      setIsMembersLoading(true);
      setMemberError(null);
      if (!preserveFeedback) setFeedback(null);
      try {
        const result = await listGoogleWorkspaceGroupMembers(
          organizationId,
          group.primary_email,
          pageToken,
          nextController.signal
        );
        if (requestSequence.current !== sequence) return;
        setSelectedGroup(result.group);
        setMembers(result.members);
        setMemberPage(pageIndex);
        setMemberNextToken(result.next_page_token);
      } catch (error) {
        if (nextController.signal.aborted || requestSequence.current !== sequence) return;
        setMembers([]);
        setMemberError(groupErrorMessage(error));
      } finally {
        if (requestSequence.current === sequence) setIsMembersLoading(false);
      }
    },
    [organizationId]
  );

  const openRequestedGroup = useCallback(
    async (groupEmail: string) => {
      controller.current?.abort();
      const nextController = new AbortController();
      controller.current = nextController;
      const sequence = requestSequence.current + 1;
      requestSequence.current = sequence;
      setIsGroupsLoading(false);
      setIsMembersLoading(true);
      setGroupError(null);
      setMemberError(null);
      setFeedback(null);
      setMembers([]);
      setMemberTokens([null]);
      setMemberPage(0);
      setMemberNextToken(null);
      try {
        const group = await getGoogleWorkspaceGroup(
          organizationId,
          groupEmail,
          nextController.signal
        );
        if (requestSequence.current !== sequence) return;
        setSelectedGroup(group);
        const result = await listGoogleWorkspaceGroupMembers(
          organizationId,
          group.primary_email,
          null,
          nextController.signal
        );
        if (requestSequence.current !== sequence) return;
        setSelectedGroup(result.group);
        setMembers(result.members);
        setMemberNextToken(result.next_page_token);
      } catch (error) {
        if (nextController.signal.aborted || requestSequence.current !== sequence) return;
        setSelectedGroup(null);
        setMembers([]);
        setGroupError(groupErrorMessage(error));
      } finally {
        if (requestSequence.current === sequence) {
          controller.current = null;
          setIsMembersLoading(false);
        }
      }
    },
    [organizationId]
  );

  useEffect(() => {
    requestSequence.current += 1;
    controller.current?.abort();
    setQuery("");
    setGroups([]);
    setGroupTokens([null]);
    setGroupPage(0);
    setGroupNextToken(null);
    setSelectedGroup(null);
    setMembers([]);
    setMemberTokens([null]);
    setMemberPage(0);
    setMemberNextToken(null);
    setMemberEmail("");
    setPendingPreview(null);
    setAmbiguousPreview(null);
    setGroupError(null);
    setMemberError(null);
    setFeedback(null);
    reconciliationInFlight.current = false;
    mutationInFlight.current = false;
    if (canSearch && organizationId) void loadGroups("", null, 0);
    return () => controller.current?.abort();
  }, [canSearch, loadGroups, organizationId]);

  useEffect(() => {
    if (!canSearch || !initialGroupEmail || navigationRequestId === undefined) return;
    void openRequestedGroup(initialGroupEmail);
  }, [canSearch, initialGroupEmail, navigationRequestId, openRequestedGroup]);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSelectedGroup(null);
    setMembers([]);
    setGroupTokens([null]);
    await loadGroups(query.trim(), null, 0);
  }

  async function selectGroup(group: GoogleWorkspaceGroup) {
    setSelectedGroup(group);
    setMembers([]);
    setMemberTokens([null]);
    setMemberEmail("");
    setPendingPreview(null);
    setAmbiguousPreview(null);
    await loadMembers(group, null, 0);
    detailHeading.current?.focus();
  }

  function returnToGroups() {
    requestSequence.current += 1;
    controller.current?.abort();
    setSelectedGroup(null);
    setMembers([]);
    setMemberError(null);
    setPendingPreview(null);
    setAmbiguousPreview(null);
    setFeedback(null);
    setIsMembersLoading(false);
  }

  async function previewChange(operation: "add" | "remove", email: string) {
    if (!selectedGroup || !canMutate || isPreviewing || isMutating || ambiguousPreview) return;
    const normalized = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalized)) {
      setFeedback({ type: "error", message: "Enter a valid full email address." });
      return;
    }
    confirmationTrigger.current = document.activeElement as HTMLElement | null;
    const sequence = requestSequence.current;
    setIsPreviewing(true);
    setFeedback(null);
    try {
      const preview = await previewGroupMembershipChange(
        organizationId,
        operation,
        selectedGroup.primary_email,
        normalized
      );
      if (requestSequence.current === sequence) setPendingPreview(preview);
    } catch (error) {
      if (requestSequence.current === sequence) {
        setFeedback({ type: "error", message: groupErrorMessage(error) });
      }
    } finally {
      if (requestSequence.current === sequence) setIsPreviewing(false);
    }
  }

  async function reconcile(preview: GroupMembershipPreview, sequence: number) {
    if (reconciliationInFlight.current) return;
    reconciliationInFlight.current = true;
    setIsReconciling(true);
    setFeedback({
      type: "info",
      message: "The write result was ambiguous. Checking direct membership without resubmitting the change…"
    });
    try {
      const result = await reconcileGroupMembershipChange(
        organizationId,
        preview.operation,
        preview.confirmation_token
      );
      if (requestSequence.current !== sequence) return;
      if (result.status === "verified") {
        setAmbiguousPreview(null);
        setFeedback({ type: "success", message: result.message });
        setIsReconciling(false);
        reconciliationInFlight.current = false;
        if (selectedGroup) {
          await loadMembers(selectedGroup, memberTokens[memberPage] ?? null, memberPage, true);
        }
      } else {
        setFeedback({ type: "warning", message: result.message });
      }
    } catch (error) {
      if (requestSequence.current === sequence) {
        setFeedback({
          type: "warning",
          message: `The outcome remains unknown. ${groupErrorMessage(error)} Refresh before another change.`
        });
      }
    } finally {
      if (requestSequence.current === sequence) {
        setIsReconciling(false);
        reconciliationInFlight.current = false;
      }
    }
  }

  async function confirmChange() {
    if (
      !pendingPreview ||
      !selectedGroup ||
      mutationInFlight.current ||
      isMutating ||
      isReconciling
    ) return;
    mutationInFlight.current = true;
    const preview = pendingPreview;
    const sequence = requestSequence.current;
    setIsMutating(true);
    setFeedback(null);
    try {
      const result = await executeGroupMembershipChange(
        organizationId,
        preview.operation,
        preview.confirmation_token
      );
      if (requestSequence.current !== sequence) return;
      setPendingPreview(null);
      setMemberEmail("");
      setFeedback({ type: "success", message: result.message });
      setIsMutating(false);
      await loadMembers(selectedGroup, memberTokens[memberPage] ?? null, memberPage, true);
    } catch (error) {
      if (requestSequence.current !== sequence) return;
      setPendingPreview(null);
      if (
        error instanceof ApiError &&
        error.reconciliationAvailable &&
        AMBIGUOUS_CODES.has(error.code ?? "")
      ) {
        setAmbiguousPreview(preview);
        setIsMutating(false);
        await reconcile(preview, sequence);
      } else {
        setFeedback({ type: "error", message: groupErrorMessage(error) });
      }
    } finally {
      mutationInFlight.current = false;
      if (requestSequence.current === sequence) setIsMutating(false);
    }
  }

  function nextGroupPage() {
    if (!groupNextToken) return;
    const tokens = groupTokens.slice(0, groupPage + 1);
    tokens.push(groupNextToken);
    setGroupTokens(tokens);
    void loadGroups(query.trim(), groupNextToken, groupPage + 1);
  }

  function nextMemberPage() {
    if (!memberNextToken || !selectedGroup) return;
    const tokens = memberTokens.slice(0, memberPage + 1);
    tokens.push(memberNextToken);
    setMemberTokens(tokens);
    void loadMembers(selectedGroup, memberNextToken, memberPage + 1);
  }

  const writeLocked = isPreviewing || isMutating || isReconciling || ambiguousPreview !== null;
  const groupAliases = selectedGroup
    ? [...selectedGroup.aliases, ...selectedGroup.non_editable_aliases]
    : [];
  const announcement = isGroupsLoading
    ? "Loading Google Workspace groups."
    : isMembersLoading
      ? "Loading direct group members."
      : groupError ?? memberError ?? feedback?.message ?? "";
  const groupColumns: DataTableColumn<GoogleWorkspaceGroup>[] = [
    { id: "group", header: "Group", cell: (group) => <span className="group-primary-cell"><strong>{group.name}</strong><span>{group.primary_email}</span></span> },
    { id: "aliases", header: "Aliases", cell: (group) => group.aliases.length + group.non_editable_aliases.length || "—" },
    { id: "members", header: "Direct members", cell: (group) => group.direct_members_count ?? "Unknown" },
    { id: "actions", header: <span className="sr-only">Open group</span>, cell: (group) => <Button variant="secondary" size="sm" onClick={() => void selectGroup(group)}>View members <ArrowRight aria-hidden="true" /></Button> }
  ];
  const memberColumns: DataTableColumn<GoogleWorkspaceGroupMember>[] = [
    { id: "member", header: "Member", cell: (member) => <span className="group-primary-cell"><strong>{member.email ?? member.id}</strong>{member.restriction_reason ? <span>{member.restriction_reason}</span> : null}</span> },
    { id: "type", header: "Type", cell: memberLabel },
    { id: "role", header: "Role", cell: (member) => <Badge variant={roleVariant(member.role)}>{member.role}</Badge> },
    { id: "status", header: "Status", cell: (member) => <Badge variant={statusVariant(member.status)}>{member.status ?? "Unknown"}</Badge> },
    { id: "actions", header: <span className="sr-only">Membership actions</span>, cell: (member) => <Button variant="danger" size="sm" disabled={!canMutate || !selectedGroup?.membership_mutable || !member.mutation_supported || writeLocked || !member.email} onClick={() => member.email && void previewChange("remove", member.email)} title={member.restriction_reason ?? (canMutate ? "Review removal" : "Administrator access required")}><Trash2 aria-hidden="true" /> Remove</Button> }
  ];

  return (
    <section className="group-management" aria-labelledby="groups-heading">
      <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
      <h2 id="groups-heading" className="sr-only">Google Workspace Groups</h2>

      {!canSearch ? (
        <EmptyState
          className="groups-permission-state"
          title="Groups are not available"
          icon={<ShieldAlert aria-hidden="true" />}
        >
          Customer administrator access is required to search groups and inspect direct membership.
        </EmptyState>
      ) : !selectedGroup ? (
        <div className="groups-overview">
          <form className="group-search-form" onSubmit={handleSearch}>
            <SearchField
              id="group-search"
              label="Group name or full email"
              hideLabel
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onClear={() => setQuery("")}
              placeholder="Search by group name or full email"
              maxLength={100}
              disabled={isGroupsLoading}
            />
            <Button type="submit" loading={isGroupsLoading} loadingLabel="Searching groups">
              {isGroupsLoading ? null : <Search aria-hidden="true" />} Search
            </Button>
          </form>
          <section className="groups-results" aria-labelledby="groups-results-heading">
            <div className="groups-results-heading">
              <div>
                <h3 id="groups-results-heading">Workspace groups</h3>
                <p>Search results include group names, addresses, aliases, and direct-member totals when Google provides them.</p>
              </div>
            </div>
            <DataTable ariaLabel="Workspace groups" columns={groupColumns} rows={groups} rowKey={(group) => group.id} loading={isGroupsLoading} error={groupError} errorTitle="Groups could not be loaded" onRetry={() => void loadGroups(query.trim(), null, 0)} emptyTitle="No groups found" emptyDescription={query.trim() ? "No Workspace groups matched this name or email." : "No groups are available in the selected Workspace customer."} minWidth="50rem" className="group-data-table" />
          </section>
          <DataTablePagination ariaLabel="Group result pages" page={groupPage} onPrevious={() => void loadGroups(query.trim(), groupTokens[groupPage - 1] ?? null, groupPage - 1)} onNext={nextGroupPage} previousDisabled={groupPage === 0} nextDisabled={!groupNextToken} disabled={isGroupsLoading} />
        </div>
      ) : (
        <div className="group-detail">
          <Button className="group-back-action" variant="ghost" size="sm" onClick={returnToGroups}>
            <ArrowLeft aria-hidden="true" /> Back to groups
          </Button>
          <header className="group-identity">
            <div className="group-identity-title">
              <span className="group-identity-icon" aria-hidden="true"><UsersRound /></span>
              <div>
                <h3 ref={detailHeading} tabIndex={-1}>{selectedGroup.name}</h3>
                <p><Mail aria-hidden="true" /> {selectedGroup.primary_email}</p>
              </div>
            </div>
            <p className="group-description">{selectedGroup.description ?? "No description is available."}</p>
            <dl className="group-identity-facts">
              <div><dt>Primary address</dt><dd>{selectedGroup.primary_email}</dd></div>
              <div><dt>Aliases</dt><dd>{groupAliases.join(", ") || "None"}</dd></div>
              <div><dt>Direct members</dt><dd>{selectedGroup.direct_members_count ?? "Unknown"}</dd></div>
            </dl>
          </header>
          {!selectedGroup.membership_mutable && (
            <Alert variant="warning" title="Membership changes unavailable">{selectedGroup.restriction_reason}</Alert>
          )}
          <div className="member-toolbar">
            <div><h3>Direct members</h3><p>Indirect and derived memberships are excluded.</p></div>
            <Button variant="secondary" size="sm" loading={isMembersLoading} loadingLabel="Refreshing members" onClick={() => void loadMembers(selectedGroup, memberTokens[memberPage] ?? null, memberPage)}><RefreshCw aria-hidden="true" /> Refresh</Button>
          </div>
          <DataTable ariaLabel={`Direct members of ${selectedGroup.name}`} columns={memberColumns} rows={members} rowKey={(member) => member.id} loading={isMembersLoading} error={memberError} errorTitle="Members could not be loaded" onRetry={() => void loadMembers(selectedGroup, memberTokens[memberPage] ?? null, memberPage)} emptyTitle="No direct members" emptyDescription="This group has no direct members." minWidth="50rem" className="group-data-table member-data-table" />
          <DataTablePagination ariaLabel="Member result pages" page={memberPage} onPrevious={() => void loadMembers(selectedGroup, memberTokens[memberPage - 1] ?? null, memberPage - 1)} onNext={nextMemberPage} previousDisabled={memberPage === 0} nextDisabled={!memberNextToken} disabled={isMembersLoading} />
          <Card as="section" className="group-add-panel" padding="md" aria-labelledby="add-member-heading">
            <div className="group-add-heading"><h3 id="add-member-heading">Add a direct member</h3><p>Add an existing internal user by primary email or alias.</p></div>
            <form className="group-add-form" onSubmit={(event) => { event.preventDefault(); void previewChange("add", memberEmail); }}>
              <Input label="Add an existing internal user by primary email or alias" hideLabel leadingIcon={<AtSign />} id="group-member-email" type="email" autoComplete="off" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} placeholder="person@example.com" disabled={!canMutate || !selectedGroup.membership_mutable || writeLocked} />
              <Button type="submit" loading={isPreviewing} loadingLabel="Validating member" disabled={!canMutate || !selectedGroup.membership_mutable || !memberEmail.trim() || writeLocked}>{isPreviewing ? null : <Plus aria-hidden="true" />}{isPreviewing ? "Validating" : "Review add"}</Button>
            </form>
            <p className="group-safety-note"><ShieldAlert aria-hidden="true" />Membership changes require review and explicit confirmation before they are submitted.</p>
          </Card>
          {!canMutate && <Alert variant="info">You can inspect direct membership, but only customer administrators can change it.</Alert>}
          {feedback && <Alert variant={feedback.type === "error" ? "danger" : feedback.type}>{feedback.message}</Alert>}
          {ambiguousPreview && !isReconciling && <div className="group-reconciliation"><div><strong>Outcome still unknown</strong><span>The original write remains consumed and will not be sent again.</span></div><button type="button" className="secondary-button" onClick={() => void reconcile(ambiguousPreview, requestSequence.current)}>Check current state</button></div>}
        </div>
      )}

      <Modal
        open={pendingPreview !== null}
        onClose={() => setPendingPreview(null)}
        title={`Confirm membership ${pendingPreview?.operation ?? "change"}`}
        description={pendingPreview?.effect}
        closeDisabled={isMutating}
        restoreFocusRef={confirmationTrigger}
        footer={pendingPreview ? <><Button variant="secondary" onClick={() => setPendingPreview(null)} disabled={isMutating}>Cancel</Button><Button variant={pendingPreview.operation === "remove" ? "danger" : "primary"} loading={isMutating} loadingLabel={`Confirming ${pendingPreview.operation}`} onClick={() => void confirmChange()}>Confirm {pendingPreview.operation}</Button></> : undefined}
      >
        {pendingPreview ? <div className="group-confirmation-content"><dl className="confirmation-identities"><div><dt>Group</dt><dd>{pendingPreview.group_primary_email}</dd></div><div><dt>User</dt><dd>{pendingPreview.member_primary_email}</dd></div><div><dt>Role</dt><dd>{pendingPreview.member_role}</dd></div></dl><Alert variant="warning">This single-use approval expires at {new Date(pendingPreview.expires_at).toLocaleTimeString()}.</Alert></div> : null}
      </Modal>
    </section>
  );
}
