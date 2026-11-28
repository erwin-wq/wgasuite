import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listGoogleWorkspaceUserAdminRoleAssignments } from "../../api/client";
import type {
  GoogleWorkspaceUser,
  GoogleWorkspaceUserRoleAssignmentInventory
} from "../../types";
import { UserAdminRoleAssignments } from "./UserAdminRoleAssignments";

vi.mock("../../api/client", () => ({
  listGoogleWorkspaceUserAdminRoleAssignments: vi.fn()
}));

const selectedUser: GoogleWorkspaceUser = {
  id: "109999999999999999999",
  full_name: "Selected User",
  primary_email: "selected@example.test",
  aliases: [],
  non_editable_aliases: [],
  suspended: false,
  archived: false,
  org_unit_path: "/",
  is_mailbox_setup: true,
  is_super_admin: false,
  is_delegated_admin: true,
  is_guest_user: false,
  creation_time: null,
  last_login_time: null,
  matched_by: "primary_email"
};

const inventory: GoogleWorkspaceUserRoleAssignmentInventory = {
  user: {
    id: selectedUser.id,
    primary_email: selectedUser.primary_email,
    display_name: selectedUser.full_name,
    account_status: "ACTIVE"
  },
  assignments: [
    {
      assignment: {
        assignment_id: "2001",
        role_id: "1001",
        assigned_to: "108888888888888888888",
        assignee_type: "GROUP",
        scope_type: "ORG_UNIT",
        org_unit_id: "03ph8a2z1z3e34p",
        condition: "securityGroup",
        expires_at: null,
        expired: false
      },
      role: {
        role_id: "1001",
        name: "Groups Administrator",
        description: null,
        is_system_role: true,
        is_super_admin_role: false,
        privileges: []
      },
      provenance: "GROUP_DERIVED",
      principal: {
        outcome: "verified",
        identity_type: "GROUP",
        principal_id: "108888888888888888888",
        primary_email: "admins@example.test",
        display_name: "Administrators",
        account_status: null,
        reason: null
      }
    }
  ],
  assignment_count: 1,
  direct_count: 0,
  group_derived_count: 1,
  unknown_count: 0,
  google_reported_indirect_included: true,
  effective_permissions_included: false,
  read_only: true
};

describe("UserAdminRoleAssignments", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads only on demand and presents verified group-derived evidence", async () => {
    vi.mocked(listGoogleWorkspaceUserAdminRoleAssignments).mockResolvedValue(inventory);
    const actor = userEvent.setup();
    render(<UserAdminRoleAssignments organizationId="organization-1" user={selectedUser} />);

    expect(listGoogleWorkspaceUserAdminRoleAssignments).not.toHaveBeenCalled();
    expect(screen.getByText(/does not calculate effective administrator permissions/i)).toBeVisible();
    await actor.click(screen.getByRole("button", { name: "Load assignments" }));

    expect(await screen.findByText("Groups Administrator")).toBeVisible();
    expect(screen.getByText("Google-reported indirect assignment")).toBeVisible();
    expect(screen.getByText("Administrators")).toBeVisible();
    expect(listGoogleWorkspaceUserAdminRoleAssignments).toHaveBeenCalledWith(
      "organization-1",
      selectedUser.id,
      expect.any(AbortSignal)
    );
  });

  it("clears stale results and aborts when the tenant changes", async () => {
    vi.mocked(listGoogleWorkspaceUserAdminRoleAssignments).mockResolvedValue(inventory);
    const actor = userEvent.setup();
    const { rerender } = render(
      <UserAdminRoleAssignments organizationId="organization-1" user={selectedUser} />
    );
    await actor.click(screen.getByRole("button", { name: "Load assignments" }));
    expect(await screen.findByText("Groups Administrator")).toBeVisible();

    rerender(<UserAdminRoleAssignments organizationId="organization-2" user={selectedUser} />);

    expect(screen.queryByText("Groups Administrator")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load assignments" })).toBeVisible();
  });

  it("shows an explicit empty result without inventing indirect access", async () => {
    vi.mocked(listGoogleWorkspaceUserAdminRoleAssignments).mockResolvedValue({
      ...inventory,
      assignments: [],
      assignment_count: 0,
      group_derived_count: 0
    });
    const actor = userEvent.setup();
    render(<UserAdminRoleAssignments organizationId="organization-1" user={selectedUser} />);
    await actor.click(screen.getByRole("button", { name: "Load assignments" }));

    expect(await screen.findByText(/Google returned no direct or indirect/i)).toBeVisible();
    expect(screen.getAllByText("0")).toHaveLength(3);
  });
});
