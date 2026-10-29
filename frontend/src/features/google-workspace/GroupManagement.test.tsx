import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  GoogleWorkspaceGroup,
  GoogleWorkspaceGroupMemberList,
  GoogleWorkspaceGroupSearchResult,
  GroupMembershipPreview
} from "../../types";
import { GroupManagement } from "./GroupManagement";

const api = vi.hoisted(() => ({
  searchGoogleWorkspaceGroups: vi.fn(),
  getGoogleWorkspaceGroup: vi.fn(),
  listGoogleWorkspaceGroupMembers: vi.fn(),
  previewGroupMembershipChange: vi.fn(),
  executeGroupMembershipChange: vi.fn(),
  reconcileGroupMembershipChange: vi.fn()
}));

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, ...api };
});

const group: GoogleWorkspaceGroup = {
  id: "group-1",
  primary_email: "team@primary.example",
  name: "Team",
  description: "A customer-wide team",
  aliases: ["team@secondary.example"],
  non_editable_aliases: [],
  direct_members_count: 3,
  membership_mutable: true,
  restriction_reason: null
};

const searchResult: GoogleWorkspaceGroupSearchResult = {
  groups: [group],
  next_page_token: "groups-next"
};

const memberResult: GoogleWorkspaceGroupMemberList = {
  group,
  members: [
    {
      id: "user-1",
      email: "person@primary.example",
      type: "USER",
      role: "MEMBER",
      status: "ACTIVE",
      direct: true,
      mutation_supported: true,
      restriction_reason: null
    },
    {
      id: "group-2",
      email: "nested@primary.example",
      type: "GROUP",
      role: "MEMBER",
      status: "ACTIVE",
      direct: true,
      mutation_supported: false,
      restriction_reason: "Nested group memberships are visible but must be managed separately."
    },
    {
      id: "owner-1",
      email: "owner@primary.example",
      type: "USER",
      role: "OWNER",
      status: "ACTIVE",
      direct: true,
      mutation_supported: false,
      restriction_reason: "Owner memberships are protected from removal in WGASuite."
    }
  ],
  next_page_token: "members-next"
};

const preview: GroupMembershipPreview = {
  operation: "add",
  group_primary_email: "team@primary.example",
  member_primary_email: "canonical@primary.example",
  member_role: "MEMBER",
  confirmation_token: "confirmation-token-with-enough-characters-123",
  expires_at: "2026-10-11T12:00:00Z",
  effect: "The existing internal user will be added as a direct MEMBER. No role is changed."
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.searchGoogleWorkspaceGroups.mockResolvedValue(searchResult);
  api.getGoogleWorkspaceGroup.mockResolvedValue(group);
  api.listGoogleWorkspaceGroupMembers.mockResolvedValue(memberResult);
  api.previewGroupMembershipChange.mockResolvedValue(preview);
  api.executeGroupMembershipChange.mockResolvedValue({
    operation: "add",
    group_primary_email: group.primary_email,
    member_primary_email: preview.member_primary_email,
    outcome: "added",
    message: "Member added."
  });
  api.reconcileGroupMembershipChange.mockResolvedValue({
    operation: "add",
    group_primary_email: group.primary_email,
    member_primary_email: preview.member_primary_email,
    status: "verified",
    observed_state: "present",
    attempts: 1,
    correlation_id: "correlation-1",
    message: "Current state verified; causation is not proven."
  });
});

describe("GroupManagement", () => {
  it("opens a requested customer group through the existing detail view", async () => {
    render(
      <GroupManagement
        organizationId="organization-1"
        canSearch
        canMutate
        initialGroupEmail="team@primary.example"
        navigationRequestId={1}
      />
    );

    expect(await screen.findByRole("heading", { name: "Direct members" })).toBeVisible();
    expect(api.getGoogleWorkspaceGroup).toHaveBeenCalledWith(
      "organization-1",
      "team@primary.example",
      expect.any(AbortSignal)
    );
    expect(api.listGoogleWorkspaceGroupMembers).toHaveBeenCalledWith(
      "organization-1",
      "team@primary.example",
      null,
      expect.any(AbortSignal)
    );
  });

  it("searches customer groups and paginates without using a domain", async () => {
    const user = userEvent.setup();
    render(<GroupManagement organizationId="organization-1" canSearch canMutate />);

    expect(await screen.findByText("team@primary.example")).toBeVisible();
    expect(api.searchGoogleWorkspaceGroups).toHaveBeenCalledWith(
      "organization-1",
      "",
      null,
      expect.any(AbortSignal)
    );

    await user.clear(screen.getByLabelText("Group name or full email"));
    await user.type(screen.getByLabelText("Group name or full email"), "finance@example.com");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(api.searchGoogleWorkspaceGroups).toHaveBeenLastCalledWith(
      "organization-1",
      "finance@example.com",
      null,
      expect.any(AbortSignal)
    );

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(api.searchGoogleWorkspaceGroups).toHaveBeenLastCalledWith(
      "organization-1",
      "finance@example.com",
      "groups-next",
      expect.any(AbortSignal)
    );
  });

  it("shows group details and direct member limitations", async () => {
    const user = userEvent.setup();
    render(<GroupManagement organizationId="organization-1" canSearch canMutate />);

    await user.click(await screen.findByRole("button", { name: "View members" }));

    expect(await screen.findByText("A customer-wide team")).toBeVisible();
    expect(screen.getByText("Nested group")).toBeVisible();
    expect(screen.getByText("OWNER")).toBeVisible();
    expect(api.listGoogleWorkspaceGroupMembers).toHaveBeenCalledWith(
      "organization-1",
      "team@primary.example",
      null,
      expect.any(AbortSignal)
    );
    const removeButtons = screen.getAllByRole("button", { name: "Remove" });
    expect(removeButtons[0]).toBeEnabled();
    expect(removeButtons[1]).toBeDisabled();
    expect(removeButtons[2]).toBeDisabled();
  });

  it("canonicalizes through preview and requires explicit add confirmation", async () => {
    const user = userEvent.setup();
    render(<GroupManagement organizationId="organization-1" canSearch canMutate />);
    await user.click(await screen.findByRole("button", { name: "View members" }));
    await screen.findByText("person@primary.example");

    await user.type(
      screen.getByLabelText("Add an existing internal user by primary email or alias"),
      "alias@secondary.example"
    );
    await user.click(screen.getByRole("button", { name: "Review add" }));

    expect(await screen.findByRole("dialog")).toHaveTextContent("canonical@primary.example");
    expect(api.executeGroupMembershipChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm add" }));

    await waitFor(() => expect(api.executeGroupMembershipChange).toHaveBeenCalledTimes(1));
    expect(api.executeGroupMembershipChange).toHaveBeenCalledWith(
      "organization-1",
      "add",
      preview.confirmation_token
    );
  });

  it("prevents duplicate membership writes while confirmation is pending", async () => {
    const pending = deferred<never>();
    api.executeGroupMembershipChange.mockReturnValue(pending.promise);
    const user = userEvent.setup();
    render(<GroupManagement organizationId="organization-1" canSearch canMutate />);
    await user.click(await screen.findByRole("button", { name: "View members" }));
    await screen.findByText("person@primary.example");
    await user.type(
      screen.getByLabelText("Add an existing internal user by primary email or alias"),
      "alias@secondary.example"
    );
    await user.click(screen.getByRole("button", { name: "Review add" }));

    const confirm = await screen.findByRole("button", { name: "Confirm add" });
    await user.click(confirm);
    expect(confirm).toBeDisabled();
    await user.click(confirm);

    expect(api.executeGroupMembershipChange).toHaveBeenCalledTimes(1);
  });

  it("renders read-only controls for viewers", async () => {
    const user = userEvent.setup();
    render(<GroupManagement organizationId="organization-1" canSearch canMutate={false} />);
    await user.click(await screen.findByRole("button", { name: "View members" }));

    expect(await screen.findByText(/only customer administrators can change it/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Review add" })).toBeDisabled();
    for (const button of screen.getAllByRole("button", { name: "Remove" })) {
      expect(button).toBeDisabled();
    }
  });

  it("discards stale group results after organization switching", async () => {
    let resolveOld: ((value: GoogleWorkspaceGroupSearchResult) => void) | undefined;
    const oldRequest = new Promise<GoogleWorkspaceGroupSearchResult>((resolve) => {
      resolveOld = resolve;
    });
    const newGroup = { ...group, id: "group-new", name: "New tenant", primary_email: "new@tenant.example" };
    api.searchGoogleWorkspaceGroups
      .mockReset()
      .mockReturnValueOnce(oldRequest)
      .mockResolvedValueOnce({ groups: [newGroup], next_page_token: null });
    const view = render(
      <GroupManagement organizationId="organization-old" canSearch canMutate />
    );

    view.rerender(<GroupManagement organizationId="organization-new" canSearch canMutate />);
    expect(await screen.findByText("new@tenant.example")).toBeVisible();
    resolveOld?.({ groups: [group], next_page_token: null });

    await waitFor(() => expect(screen.queryByText("team@primary.example")).not.toBeInTheDocument());
  });
});
