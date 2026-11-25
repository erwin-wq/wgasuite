import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, listGoogleWorkspaceAdminRoles } from "../../api/client";
import type { ConnectorConfig, GoogleWorkspaceAdminRoleInventory } from "../../types";
import { AdminRolesInventory } from "./AdminRolesInventory";
import { DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE } from "./scopes";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, listGoogleWorkspaceAdminRoles: vi.fn() };
});

const connectedConfig: ConnectorConfig = {
  id: "connector-1",
  organization_id: "organization-1",
  connector_type: "google_workspace",
  auth_method: "service_account_domain_wide_delegation",
  status: "connected",
  display_name: "Google Workspace",
  primary_domain: "example.test",
  admin_subject_email: "admin@example.test",
  credential_provider: "managed_file",
  credentials_configured: true,
  service_account_email: "service@example.test",
  service_account_client_id: "1234567890",
  notes: null,
  created_at: "2026-11-25T08:00:00Z",
  updated_at: "2026-11-25T08:00:00Z",
  last_tested_at: "2026-11-25T08:00:00Z",
  last_error_code: null,
  last_error: null
};

const inventory: GoogleWorkspaceAdminRoleInventory = {
  roles: [
    {
      role_id: "role-1",
      name: "Help Desk",
      description: "Limited user support",
      is_system_role: true,
      is_super_admin_role: false,
      privileges: [{ service_id: "02", privilege_name: "USERS_RETRIEVE" }]
    },
    {
      role_id: "role-2",
      name: "Custom Security Reader",
      description: null,
      is_system_role: false,
      is_super_admin_role: false,
      privileges: []
    }
  ],
  assignments: [
    {
      assignment_id: "assignment-1",
      role_id: "role-1",
      assigned_to: "109999999999999999999",
      assignee_type: "USER",
      scope_type: "ORG_UNIT",
      org_unit_id: "id:ou-1",
      condition: "securityGroup"
    }
  ],
  role_count: 2,
  assignment_count: 1,
  direct_assignments_only: true,
  effective_permissions_included: false,
  read_only: true
};

function renderInventory(overrides = {}) {
  return render(
    <AdminRolesInventory
      organizationId="organization-1"
      organizationName="Example Workspace"
      connectorConfig={connectedConfig}
      canRead
      {...overrides}
    />
  );
}

describe("AdminRolesInventory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listGoogleWorkspaceAdminRoles).mockResolvedValue(inventory);
  });

  it("renders direct-only roles without claiming effective permissions", async () => {
    renderInventory();
    expect(await screen.findByRole("table", { name: "Administrator roles" })).toBeVisible();
    expect(screen.getByText("Direct assignments, not effective permissions")).toBeVisible();
    expect(screen.getByText("Help Desk")).toBeVisible();
    expect(screen.getByText("Custom role")).toBeVisible();
    expect(screen.queryByText(/effective access granted/i)).not.toBeInTheDocument();
    expect(listGoogleWorkspaceAdminRoles).toHaveBeenCalledWith(
      "organization-1",
      expect.any(AbortSignal)
    );
  });

  it("searches roles and opens accessible detail with opaque assignment data", async () => {
    const user = userEvent.setup();
    renderInventory();
    await screen.findByText("Help Desk");
    await user.type(screen.getByRole("searchbox", { name: "Search roles" }), "help");
    expect(screen.queryByText("Custom Security Reader")).not.toBeInTheDocument();
    const button = screen.getByRole("button", { name: "View details for Help Desk" });
    button.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Help Desk", level: 3 })).toBeVisible();
    expect(screen.getByText("109999999999999999999")).toBeVisible();
    expect(screen.getByText(/OU ID:/)).toBeVisible();
    expect(screen.getByText(/Condition: securityGroup/)).toBeVisible();
    expect(screen.queryByText(/@example/)).not.toBeInTheDocument();
  });

  it("filters by role type and direct-assignment presence", async () => {
    const user = userEvent.setup();
    renderInventory();
    await screen.findByText("Help Desk");
    await user.selectOptions(screen.getByLabelText("Role type"), "custom");
    expect(screen.getByText("Custom Security Reader")).toBeVisible();
    expect(screen.queryByText("Help Desk")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Role type"), "all");
    await user.selectOptions(screen.getByLabelText("Direct assignments"), "assigned");
    expect(screen.getByText("Help Desk")).toBeVisible();
    expect(screen.queryByText("Custom Security Reader")).not.toBeInTheDocument();
  });

  it("explains the exact least-privilege scope on authorization failure", async () => {
    vi.mocked(listGoogleWorkspaceAdminRoles).mockRejectedValue(
      new ApiError("Denied", 403, "delegation_rejected")
    );
    renderInventory();
    expect(await screen.findByRole("heading", { name: "Admin roles unavailable" })).toBeVisible();
    expect(screen.getByText(new RegExp(DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE))).toBeVisible();
  });

  it("enforces tenant, connector and actor preconditions", () => {
    const { rerender } = render(
      <AdminRolesInventory organizationId="" organizationName={null} connectorConfig={null} canRead />
    );
    expect(screen.getByRole("heading", { name: "Select an organization" })).toBeVisible();
    rerender(<AdminRolesInventory organizationId="organization-1" organizationName="Example" connectorConfig={connectedConfig} canRead={false} />);
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    rerender(<AdminRolesInventory organizationId="organization-1" organizationName="Example" connectorConfig={{ ...connectedConfig, status: "configured" }} canRead />);
    expect(screen.getByRole("heading", { name: "Connect Google Workspace" })).toBeVisible();
    expect(listGoogleWorkspaceAdminRoles).not.toHaveBeenCalled();
  });

  it("drops stale tenant responses", async () => {
    let resolveFirst!: (value: GoogleWorkspaceAdminRoleInventory) => void;
    const first = new Promise<GoogleWorkspaceAdminRoleInventory>((resolve) => { resolveFirst = resolve; });
    vi.mocked(listGoogleWorkspaceAdminRoles)
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({ ...inventory, roles: [{ ...inventory.roles[0], role_id: "current", name: "Current tenant role" }] });
    const { rerender } = renderInventory();
    rerender(<AdminRolesInventory organizationId="organization-2" organizationName="Current" connectorConfig={{ ...connectedConfig, organization_id: "organization-2" }} canRead />);
    expect(await screen.findByText("Current tenant role")).toBeVisible();
    resolveFirst({ ...inventory, roles: [{ ...inventory.roles[0], role_id: "stale", name: "Stale tenant role" }] });
    await waitFor(() => expect(screen.queryByText("Stale tenant role")).not.toBeInTheDocument());
  });

  it("renders authoritative empty state", async () => {
    vi.mocked(listGoogleWorkspaceAdminRoles).mockResolvedValue({
      roles: [], assignments: [], role_count: 0, assignment_count: 0,
      direct_assignments_only: true, effective_permissions_included: false, read_only: true
    });
    renderInventory();
    expect(await screen.findByRole("heading", { name: "No roles returned" })).toBeVisible();
  });
});
