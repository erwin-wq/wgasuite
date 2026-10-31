import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  executeGoogleWorkspaceUserOrgUnitMove,
  listGoogleWorkspaceOrganizationalUnits,
  previewGoogleWorkspaceUserOrgUnitMove,
  reconcileGoogleWorkspaceUserOrgUnitMove
} from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceOrganizationalUnitHierarchy,
  GoogleWorkspaceUser
} from "../../types";
import { UserOrgUnitMove } from "./UserOrgUnitMove";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    executeGoogleWorkspaceUserOrgUnitMove: vi.fn(),
    listGoogleWorkspaceOrganizationalUnits: vi.fn(),
    previewGoogleWorkspaceUserOrgUnitMove: vi.fn(),
    reconcileGoogleWorkspaceUserOrgUnitMove: vi.fn()
  };
});

const connector = {
  id: "connector-1",
  organization_id: "organization-1",
  connector_type: "google_workspace",
  display_name: "Google Workspace",
  status: "connected",
  auth_method: "service_account_domain_wide_delegation",
  primary_domain: "example.test",
  admin_subject_email: "admin@example.test",
  service_account_email: "service@example.test"
} as ConnectorConfig;

const user: GoogleWorkspaceUser = {
  id: "user-1",
  full_name: "Example User",
  primary_email: "person@example.test",
  aliases: [],
  non_editable_aliases: [],
  suspended: false,
  archived: false,
  org_unit_path: "/",
  is_mailbox_setup: true,
  is_super_admin: false,
  is_delegated_admin: false,
  creation_time: null,
  last_login_time: null,
  matched_by: "primary_email"
};

const hierarchy: GoogleWorkspaceOrganizationalUnitHierarchy = {
  total: 2,
  roots: [
    {
      id: "id:root",
      name: "Root",
      description: null,
      path: "/",
      parent_id: null,
      parent_path: null,
      read_only: true,
      children: [
        {
          id: "id:engineering",
          name: "Engineering",
          description: null,
          path: "/Engineering",
          parent_id: "id:root",
          parent_path: "/",
          read_only: true,
          children: []
        }
      ]
    }
  ]
};

describe("UserOrgUnitMove", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listGoogleWorkspaceOrganizationalUnits).mockResolvedValue(hierarchy);
  });

  it("selects a valid destination, previews, confirms, and refreshes", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    vi.mocked(previewGoogleWorkspaceUserOrgUnitMove).mockResolvedValue({
      organization_id: "organization-1",
      customer_id: "customer-1",
      target_google_id: "user-1",
      target_primary_email: "person@example.test",
      source_org_unit_path: "/",
      destination_org_unit_id: "id:engineering",
      destination_org_unit_path: "/Engineering",
      confirmation_token: "confirmation-token-12345678901234567890",
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      effect: "Applicable services and policies may change."
    });
    vi.mocked(executeGoogleWorkspaceUserOrgUnitMove).mockResolvedValue({
      target_google_id: "user-1",
      target_primary_email: "person@example.test",
      previous_org_unit_path: "/",
      org_unit_path: "/Engineering",
      outcome: "moved",
      message: "User moved."
    });

    render(
      <UserOrgUnitMove
        organizationId="organization-1"
        connectorConfig={connector}
        user={user}
        canMutate
        onRefresh={onRefresh}
      />
    );
    const operator = userEvent.setup();
    await operator.click(screen.getByRole("button", { name: /move to organizational unit/i }));
    await operator.click(await screen.findByRole("treeitem", { name: /engineering/i }));
    await operator.click(screen.getByRole("button", { name: /review move/i }));
    expect(await screen.findByText(/applicable services and policies/i)).toBeInTheDocument();
    await operator.click(screen.getByRole("checkbox"));
    await operator.click(screen.getByRole("button", { name: /confirm move/i }));

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
    expect(previewGoogleWorkspaceUserOrgUnitMove).toHaveBeenCalledWith(
      "organization-1",
      "user-1",
      "id:engineering",
      expect.any(AbortSignal)
    );
    expect(executeGoogleWorkspaceUserOrgUnitMove).toHaveBeenCalledTimes(1);
    expect(reconcileGoogleWorkspaceUserOrgUnitMove).not.toHaveBeenCalled();
  });

  it("disables the current unit and protects administrators", async () => {
    const view = render(
      <UserOrgUnitMove
        organizationId="organization-1"
        connectorConfig={connector}
        user={user}
        canMutate
        onRefresh={vi.fn()}
      />
    );
    const operator = userEvent.setup();
    await operator.click(screen.getByRole("button", { name: /move to organizational unit/i }));
    expect(await screen.findByRole("treeitem", { name: /root.*current/i })).toBeDisabled();

    view.rerender(
      <UserOrgUnitMove
        organizationId="organization-1"
        connectorConfig={connector}
        user={{ ...user, is_super_admin: true }}
        canMutate
        onRefresh={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: /move to organizational unit/i })).not.toBeInTheDocument();
    expect(screen.getByText(/administrator accounts are protected/i)).toBeInTheDocument();
  });

  it("clears the picker when the organization changes", async () => {
    const view = render(
      <UserOrgUnitMove
        organizationId="organization-1"
        connectorConfig={connector}
        user={user}
        canMutate
        onRefresh={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /move to organizational unit/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    view.rerender(
      <UserOrgUnitMove
        organizationId="organization-2"
        connectorConfig={{ ...connector, organization_id: "organization-2" }}
        user={user}
        canMutate
        onRefresh={vi.fn()}
      />
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("supports keyboard focus navigation between available destinations", async () => {
    const nestedHierarchy: GoogleWorkspaceOrganizationalUnitHierarchy = {
      ...hierarchy,
      total: 3,
      roots: [
        {
          ...hierarchy.roots[0],
          children: [
            ...hierarchy.roots[0].children,
            {
              id: "id:sales",
              name: "Sales",
              description: null,
              path: "/Sales",
              parent_id: "id:root",
              parent_path: "/",
              read_only: true,
              children: []
            }
          ]
        }
      ]
    };
    vi.mocked(listGoogleWorkspaceOrganizationalUnits).mockResolvedValue(nestedHierarchy);
    render(
      <UserOrgUnitMove
        organizationId="organization-1"
        connectorConfig={connector}
        user={user}
        canMutate
        onRefresh={vi.fn()}
      />
    );
    const operator = userEvent.setup();
    await operator.click(screen.getByRole("button", { name: /move to organizational unit/i }));
    const engineering = await screen.findByRole("treeitem", { name: /engineering/i });
    const sales = screen.getByRole("treeitem", { name: /sales/i });
    engineering.focus();
    await operator.keyboard("{ArrowDown}");
    expect(sales).toHaveFocus();
    await operator.keyboard("{Home}");
    expect(engineering).toHaveFocus();
  });

  it("shows a safe preview failure and never enables a write", async () => {
    vi.mocked(previewGoogleWorkspaceUserOrgUnitMove).mockRejectedValue(
      new ApiError(
        "Google reported that the delegated account lacks the required scope or permission.",
        403,
        "missing_scope_or_permission"
      )
    );
    render(
      <UserOrgUnitMove
        organizationId="organization-1"
        connectorConfig={connector}
        user={user}
        canMutate
        onRefresh={vi.fn()}
      />
    );
    const operator = userEvent.setup();
    await operator.click(screen.getByRole("button", { name: /move to organizational unit/i }));
    await operator.click(await screen.findByRole("treeitem", { name: /engineering/i }));
    await operator.click(screen.getByRole("button", { name: /review move/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/verify the directory user write scope/i);
    expect(screen.queryByRole("button", { name: /confirm move/i })).not.toBeInTheDocument();
    expect(executeGoogleWorkspaceUserOrgUnitMove).not.toHaveBeenCalled();
  });
});
