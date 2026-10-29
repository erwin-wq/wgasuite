import {
  AlertCircle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  UsersRound,
  X
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

  return (
    <section className="group-management" aria-labelledby="groups-heading">
      <div className="workspace-section-heading group-heading">
        <div>
          <span className="eyebrow">Directory administration</span>
          <h2 id="groups-heading">Groups</h2>
          <p>Search every domain in the verified Workspace customer and manage direct internal users.</p>
        </div>
        {selectedGroup && (
          <button type="button" className="secondary-button" onClick={returnToGroups}>
            <ArrowLeft aria-hidden="true" /> Back to groups
          </button>
        )}
      </div>

      {!canSearch ? (
        <div className="group-state warning" role="status">
          <ShieldAlert aria-hidden="true" /> Customer administrator access is required to use Groups.
        </div>
      ) : !selectedGroup ? (
        <>
          <form className="group-search-form" onSubmit={handleSearch}>
            <label htmlFor="group-search">
              Group name or full email
              <input
                id="group-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Finance or finance@example.com"
                maxLength={100}
              />
            </label>
            <button type="submit" disabled={isGroupsLoading}>
              {isGroupsLoading ? <Loader2 className="spin" aria-hidden="true" /> : <Search aria-hidden="true" />}
              Search
            </button>
          </form>
          {groupError ? (
            <div className="group-state error" role="alert"><AlertCircle aria-hidden="true" />{groupError}</div>
          ) : isGroupsLoading ? (
            <div className="group-state" role="status"><Loader2 className="spin" aria-hidden="true" />Loading groups…</div>
          ) : groups.length === 0 ? (
            <div className="group-state" role="status"><UsersRound aria-hidden="true" />No groups matched this search.</div>
          ) : (
            <div className="group-table-wrap">
              <table className="group-table">
                <thead><tr><th>Group</th><th>Aliases</th><th>Direct members</th><th><span className="sr-only">Open</span></th></tr></thead>
                <tbody>
                  {groups.map((group) => (
                    <tr key={group.id}>
                      <td><strong>{group.name}</strong><span>{group.primary_email}</span></td>
                      <td>{group.aliases.length + group.non_editable_aliases.length || "—"}</td>
                      <td>{group.direct_members_count ?? "Unknown"}</td>
                      <td><button type="button" className="secondary-button" onClick={() => void selectGroup(group)}>View members</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination-controls" aria-label="Group result pages">
            <button type="button" className="secondary-button" disabled={groupPage === 0 || isGroupsLoading} onClick={() => void loadGroups(query.trim(), groupTokens[groupPage - 1] ?? null, groupPage - 1)}><ChevronLeft aria-hidden="true" /> Previous</button>
            <span>Page {groupPage + 1}</span>
            <button type="button" className="secondary-button" disabled={!groupNextToken || isGroupsLoading} onClick={nextGroupPage}>Next <ChevronRight aria-hidden="true" /></button>
          </div>
        </>
      ) : (
        <div className="group-detail">
          <div className="group-detail-card">
            <div><span>Name</span><strong>{selectedGroup.name}</strong></div>
            <div><span>Primary email</span><strong>{selectedGroup.primary_email}</strong></div>
            <div><span>Aliases</span><strong>{[...selectedGroup.aliases, ...selectedGroup.non_editable_aliases].join(", ") || "None"}</strong></div>
            <div><span>Direct members</span><strong>{selectedGroup.direct_members_count ?? "Unknown"}</strong></div>
            <p>{selectedGroup.description ?? "No description is available."}</p>
          </div>
          {!selectedGroup.membership_mutable && (
            <div className="group-state warning" role="status"><ShieldAlert aria-hidden="true" />{selectedGroup.restriction_reason}</div>
          )}
          <div className="member-toolbar">
            <div><h3>Direct members</h3><p>Indirect and derived memberships are excluded.</p></div>
            <button type="button" className="secondary-button" disabled={isMembersLoading} onClick={() => void loadMembers(selectedGroup, memberTokens[memberPage] ?? null, memberPage)}><RefreshCw className={isMembersLoading ? "spin" : ""} aria-hidden="true" /> Refresh</button>
          </div>
          {memberError ? (
            <div className="group-state error" role="alert"><AlertCircle aria-hidden="true" />{memberError}</div>
          ) : isMembersLoading ? (
            <div className="group-state" role="status"><Loader2 className="spin" aria-hidden="true" />Loading direct members…</div>
          ) : members.length === 0 ? (
            <div className="group-state" role="status"><UsersRound aria-hidden="true" />This group has no direct members.</div>
          ) : (
            <div className="group-table-wrap">
              <table className="group-table member-table">
                <thead><tr><th>Member</th><th>Type</th><th>Role</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {members.map((member) => (
                    <tr key={member.id}>
                      <td><strong>{member.email ?? member.id}</strong>{member.restriction_reason && <span>{member.restriction_reason}</span>}</td>
                      <td>{memberLabel(member)}</td><td>{member.role}</td><td>{member.status ?? "Unknown"}</td>
                      <td><button type="button" className="danger-button" disabled={!canMutate || !selectedGroup.membership_mutable || !member.mutation_supported || writeLocked || !member.email} onClick={() => member.email && void previewChange("remove", member.email)} title={member.restriction_reason ?? (canMutate ? "Review removal" : "Administrator access required")}><Trash2 aria-hidden="true" /> Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination-controls" aria-label="Member result pages">
            <button type="button" className="secondary-button" disabled={memberPage === 0 || isMembersLoading} onClick={() => void loadMembers(selectedGroup, memberTokens[memberPage - 1] ?? null, memberPage - 1)}><ChevronLeft aria-hidden="true" /> Previous</button>
            <span>Page {memberPage + 1}</span>
            <button type="button" className="secondary-button" disabled={!memberNextToken || isMembersLoading} onClick={nextMemberPage}>Next <ChevronRight aria-hidden="true" /></button>
          </div>
          <form className="group-add-form" onSubmit={(event) => { event.preventDefault(); void previewChange("add", memberEmail); }}>
            <label htmlFor="group-member-email">Add an existing internal user by primary email or alias<input id="group-member-email" type="email" autoComplete="off" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} placeholder="person@example.com" disabled={!canMutate || !selectedGroup.membership_mutable || writeLocked} /></label>
            <button type="submit" disabled={!canMutate || !selectedGroup.membership_mutable || !memberEmail.trim() || writeLocked}>{isPreviewing ? <Loader2 className="spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}{isPreviewing ? "Validating" : "Review add"}</button>
          </form>
          {!canMutate && <p className="group-readonly-note"><ShieldAlert aria-hidden="true" />You can inspect direct membership, but only customer administrators can change it.</p>}
          {feedback && <div className={`group-state ${feedback.type}`} role={feedback.type === "error" ? "alert" : "status"}>{feedback.type === "error" ? <AlertCircle aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}{feedback.message}</div>}
          {ambiguousPreview && !isReconciling && <div className="group-reconciliation"><div><strong>Outcome still unknown</strong><span>The original write remains consumed and will not be sent again.</span></div><button type="button" className="secondary-button" onClick={() => void reconcile(ambiguousPreview, requestSequence.current)}>Check current state</button></div>}
        </div>
      )}

      {pendingPreview && (
        <div className="confirmation-backdrop" role="presentation">
          <section className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="group-confirmation-heading">
            <button type="button" className="dialog-close" aria-label="Close confirmation" onClick={() => setPendingPreview(null)} disabled={isMutating}><X aria-hidden="true" /></button>
            <h3 id="group-confirmation-heading">Confirm membership {pendingPreview.operation}</h3>
            <p>{pendingPreview.effect}</p>
            <dl className="confirmation-identities"><div><dt>Group</dt><dd>{pendingPreview.group_primary_email}</dd></div><div><dt>User</dt><dd>{pendingPreview.member_primary_email}</dd></div><div><dt>Role</dt><dd>{pendingPreview.member_role}</dd></div></dl>
            <p>This single-use approval expires at {new Date(pendingPreview.expires_at).toLocaleTimeString()}.</p>
            <div className="confirmation-actions"><button type="button" className="secondary-button" onClick={() => setPendingPreview(null)} disabled={isMutating}>Cancel</button><button type="button" className={pendingPreview.operation === "remove" ? "danger-button" : ""} onClick={() => void confirmChange()} disabled={isMutating}>{isMutating && <Loader2 className="spin" aria-hidden="true" />}Confirm {pendingPreview.operation}</button></div>
          </section>
        </div>
      )}
    </section>
  );
}
