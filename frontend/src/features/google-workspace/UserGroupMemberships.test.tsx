import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import type {
  GoogleWorkspaceUser,
  GoogleWorkspaceUserGroupMembershipResult
} from "../../types";
import { UserGroupMemberships } from "./UserGroupMemberships";

const api = vi.hoisted(() => ({
  listGoogleWorkspaceUserGroupMemberships: vi.fn()
}));

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, ...api };
});

const user: GoogleWorkspaceUser = {
  id: "user-1",
  full_name: "Example User",
  primary_email: "person@primary.example",
  aliases: ["alias@primary.example"],
  non_editable_aliases: [],
  suspended: false,
  archived: false,
  org_unit_path: "/People",
  is_mailbox_setup: true,
  is_super_admin: false,
  is_delegated_admin: false,
  creation_time: "2020-01-02T03:04:05Z",
  last_login_time: "2026-10-12T08:30:00Z",
  matched_by: "alias"
};

const populatedResult: GoogleWorkspaceUserGroupMembershipResult = {
  user_id: user.id,
  user_primary_email: user.primary_email,
  matched_by: "primary_email",
  memberships: [
    {
      group_id: "group-1",
      group_name: "Engineering",
      group_primary_email: "engineering@primary.example",
      role: "MANAGER",
      member_type: "USER",
      status: "ACTIVE"
    },
    {
      group_id: "group-2",
      group_name: "Owners",
      group_primary_email: "owners@secondary.example",
      role: "OWNER",
      member_type: "USER",
      status: null
    }
  ],
  next_page_token: "opaque-next-token",
  verification_complete: true,
  candidates_examined: 4,
  omitted_external_count: 1,
  omitted_indirect_count: 1
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("UserGroupMemberships", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listGoogleWorkspaceUserGroupMemberships.mockResolvedValue(populatedResult);
  });

  it("loads canonical user memberships, displays roles, and opens the existing group tool", async () => {
    const onOpenGroup = vi.fn();
    const interaction = userEvent.setup();
    render(
      <UserGroupMemberships
        organizationId="organization-1"
        user={user}
        onOpenGroup={onOpenGroup}
      />
    );

    expect(await screen.findByText("engineering@primary.example")).toBeVisible();
    expect(screen.getByText("MANAGER")).toBeVisible();
    expect(screen.getByText("OWNER")).toBeVisible();
    expect(screen.getByText(/1 outside this customer and 1 indirect/)).toBeVisible();
    expect(api.listGoogleWorkspaceUserGroupMemberships).toHaveBeenCalledWith(
      "organization-1",
      "person@primary.example",
      10,
      null,
      expect.any(AbortSignal)
    );

    await interaction.click(screen.getAllByRole("button", { name: "Open group" })[0]);
    expect(onOpenGroup).toHaveBeenCalledWith("engineering@primary.example");
  });

  it("paginates with opaque tokens, changes the safe page size, and refreshes", async () => {
    const interaction = userEvent.setup();
    api.listGoogleWorkspaceUserGroupMemberships
      .mockResolvedValueOnce(populatedResult)
      .mockResolvedValueOnce({ ...populatedResult, memberships: [], next_page_token: null })
      .mockResolvedValue({ ...populatedResult, next_page_token: null });
    render(
      <UserGroupMemberships organizationId="organization-1" user={user} onOpenGroup={vi.fn()} />
    );

    await screen.findByText("engineering@primary.example");
    await interaction.click(screen.getByRole("button", { name: "Next" }));
    expect(api.listGoogleWorkspaceUserGroupMemberships).toHaveBeenLastCalledWith(
      "organization-1",
      user.primary_email,
      10,
      "opaque-next-token",
      expect.any(AbortSignal)
    );
    expect(await screen.findByText("This user has no verified direct group memberships.")).toBeVisible();

    await interaction.selectOptions(screen.getByLabelText("Rows"), "25");
    await waitFor(() =>
      expect(api.listGoogleWorkspaceUserGroupMemberships).toHaveBeenLastCalledWith(
        "organization-1",
        user.primary_email,
        25,
        null,
        expect.any(AbortSignal)
      )
    );
    await interaction.click(screen.getByRole("button", { name: "Refresh" }));
    expect(api.listGoogleWorkspaceUserGroupMemberships).toHaveBeenLastCalledWith(
      "organization-1",
      user.primary_email,
      25,
      null,
      expect.any(AbortSignal)
    );
  });

  it("shows safe errors and explains an empty filtered page with a continuation", async () => {
    api.listGoogleWorkspaceUserGroupMemberships.mockRejectedValueOnce(
      new ApiError("unsafe detail", 502, "google_operation_budget_exceeded")
    );
    const view = render(
      <UserGroupMemberships organizationId="organization-1" user={user} onOpenGroup={vi.fn()} />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("safe verification limit");
    expect(screen.queryByText("unsafe detail")).not.toBeInTheDocument();

    api.listGoogleWorkspaceUserGroupMemberships.mockResolvedValue({
      ...populatedResult,
      memberships: [],
      next_page_token: "continue-token"
    });
    view.unmount();
    render(
      <UserGroupMemberships organizationId="organization-1" user={user} onOpenGroup={vi.fn()} />
    );
    expect(await screen.findByText(/No verified direct memberships are on this page/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("discards a stale tenant response when the organization and user change", async () => {
    const stale = deferred<GoogleWorkspaceUserGroupMembershipResult>();
    api.listGoogleWorkspaceUserGroupMemberships
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce({
        ...populatedResult,
        user_id: "user-2",
        user_primary_email: "second@other.example",
        memberships: [{
          ...populatedResult.memberships[0],
          group_id: "group-new",
          group_name: "New tenant group",
          group_primary_email: "new@other.example"
        }]
      });
    const view = render(
      <UserGroupMemberships organizationId="organization-1" user={user} onOpenGroup={vi.fn()} />
    );

    view.rerender(
      <UserGroupMemberships
        organizationId="organization-2"
        user={{ ...user, id: "user-2", primary_email: "second@other.example" }}
        onOpenGroup={vi.fn()}
      />
    );
    expect(await screen.findByText("new@other.example")).toBeVisible();
    stale.resolve(populatedResult);
    await waitFor(() => expect(screen.queryByText("engineering@primary.example")).not.toBeInTheDocument());
    expect(screen.getByText("new@other.example")).toBeVisible();
  });
});
