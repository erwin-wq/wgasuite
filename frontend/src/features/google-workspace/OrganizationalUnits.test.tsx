import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, listGoogleWorkspaceOrganizationalUnits } from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceOrganizationalUnitHierarchy
} from "../../types";
import { DIRECTORY_ORGUNIT_READONLY_SCOPE, OrganizationalUnits } from "./OrganizationalUnits";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, listGoogleWorkspaceOrganizationalUnits: vi.fn() };
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
  created_at: "2026-10-30T08:00:00Z",
  updated_at: "2026-10-30T08:00:00Z",
  last_tested_at: "2026-10-30T08:00:00Z",
  last_error_code: null,
  last_error: null
};

const hierarchy: GoogleWorkspaceOrganizationalUnitHierarchy = {
  total: 3,
  roots: [
    {
      id: "id:root",
      name: "Example Workspace",
      description: null,
      path: "/",
      parent_id: null,
      parent_path: null,
      read_only: true,
      user_move_protected: false,
      children: [
        {
          id: "id:engineering",
          name: "Engineering",
          description: "Product builders",
          path: "/Engineering",
          parent_id: "id:root",
          parent_path: "/",
          read_only: true,
          user_move_protected: false,
          children: [
            {
              id: "id:platform",
              name: "Platform",
              description: null,
              path: "/Engineering/Platform",
              parent_id: "id:engineering",
              parent_path: "/Engineering",
              read_only: true,
              user_move_protected: false,
              children: []
            }
          ]
        }
      ]
    }
  ]
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

function renderOrganizationalUnits(overrides = {}) {
  const props = {
    organizationId: "organization-1",
    organizationName: "Northstar Workspace",
    connectorConfig: connectedConfig,
    canRead: true,
    canCreate: false,
    ...overrides
  };
  return { ...render(<OrganizationalUnits {...props} />), props };
}

describe("OrganizationalUnits", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listGoogleWorkspaceOrganizationalUnits).mockResolvedValue(hierarchy);
  });

  it("loads the full hierarchy, expands nodes and shows read-only details", async () => {
    const user = userEvent.setup();
    renderOrganizationalUnits();

    expect(await screen.findByRole("tree", { name: "Organizational Units hierarchy" })).toBeVisible();
    expect(screen.getByText("3 organizational units")).toBeVisible();
    expect(screen.getByRole("treeitem", { name: "Example Workspace (/)" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(screen.queryByRole("treeitem", { name: "Platform (/Engineering/Platform)" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Expand Engineering" }));
    await user.click(screen.getByRole("treeitem", { name: "Engineering (/Engineering)" }));

    expect(screen.getByRole("treeitem", { name: "Platform (/Engineering/Platform)" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Engineering" })).toBeVisible();
    expect(screen.getByText("Product builders")).toBeVisible();
    expect(screen.getByText(/Rename, reparent, delete/)).toBeVisible();
    expect(listGoogleWorkspaceOrganizationalUnits).toHaveBeenCalledWith(
      "organization-1",
      expect.any(AbortSignal)
    );
  });

  it("supports arrow-key tree navigation", async () => {
    renderOrganizationalUnits();
    const root = await screen.findByRole("treeitem", { name: "Example Workspace (/)" });
    root.focus();

    fireEvent.keyDown(root, { key: "ArrowDown" });

    await waitFor(() =>
      expect(screen.getByRole("treeitem", { name: "Engineering (/Engineering)" })).toHaveFocus()
    );
    expect(screen.getByRole("heading", { name: "Engineering" })).toBeVisible();
  });

  it("preserves the selected parent when a refreshed hierarchy still contains it", async () => {
    const user = userEvent.setup();
    renderOrganizationalUnits();
    await user.click(
      await screen.findByRole("treeitem", { name: "Engineering (/Engineering)" })
    );

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() =>
      expect(listGoogleWorkspaceOrganizationalUnits).toHaveBeenCalledTimes(2)
    );
    expect(screen.getByRole("heading", { name: "Engineering" })).toBeVisible();
  });

  it.each(["missing_scope_or_permission", "delegation_rejected"])(
    "shows exact DWD instructions for %s",
    async (code) => {
    vi.mocked(listGoogleWorkspaceOrganizationalUnits).mockRejectedValue(
      new ApiError("safe", 403, code)
    );
    renderOrganizationalUnits();

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent(DIRECTORY_ORGUNIT_READONLY_SCOPE);
    expect(alert).toHaveTextContent("Domain-Wide Delegation");
    expect(alert).not.toHaveTextContent("safe");
    }
  );

  it("renders loading and empty states without demo units", async () => {
    const pending = deferred<GoogleWorkspaceOrganizationalUnitHierarchy>();
    vi.mocked(listGoogleWorkspaceOrganizationalUnits).mockReturnValue(pending.promise);
    renderOrganizationalUnits();
    expect(screen.getByText("Loading Organizational Units…")).toBeVisible();

    pending.resolve({ roots: [], total: 0 });
    expect(await screen.findByText("Google returned no Organizational Units.")).toBeVisible();
    expect(screen.queryByText("Engineering")).not.toBeInTheDocument();
  });

  it("discards a stale hierarchy after organization switching", async () => {
    const first = deferred<GoogleWorkspaceOrganizationalUnitHierarchy>();
    const second = deferred<GoogleWorkspaceOrganizationalUnitHierarchy>();
    vi.mocked(listGoogleWorkspaceOrganizationalUnits)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const view = renderOrganizationalUnits();

    view.rerender(<OrganizationalUnits {...view.props} organizationId="organization-2" />);
    second.resolve({
      roots: [{ ...hierarchy.roots[0], id: "id:second", name: "Second Workspace" }],
      total: 1
    });
    expect(await screen.findByRole("heading", { name: "Second Workspace" })).toBeVisible();

    first.resolve({
      roots: [{ ...hierarchy.roots[0], id: "id:first", name: "Stale Workspace" }],
      total: 1
    });
    await Promise.resolve();
    expect(screen.queryByText("Stale Workspace")).not.toBeInTheDocument();
  });

  it("does not call Google-backed APIs without connector access", () => {
    renderOrganizationalUnits({ canRead: false });

    expect(screen.getByText("Connector-operation access is required.")).toBeVisible();
    expect(listGoogleWorkspaceOrganizationalUnits).not.toHaveBeenCalled();
  });

  it("disables creation for Workspace Guests and descendants without false positives", async () => {
    const user = userEvent.setup();
    vi.mocked(listGoogleWorkspaceOrganizationalUnits).mockResolvedValue({
      total: 4,
      roots: [
        {
          ...hierarchy.roots[0],
          children: [
            {
              ...hierarchy.roots[0].children[0],
              id: "id:guests",
              name: "Workspace Guests",
              path: "/Workspace Guests",
              user_move_protected: true,
              children: [
                {
                  ...hierarchy.roots[0].children[0],
                  id: "id:guest-child",
                  name: "Contractors",
                  path: "/Workspace Guests/Contractors",
                  parent_id: "id:guests",
                  parent_path: "/Workspace Guests",
                  user_move_protected: false,
                  children: []
                }
              ]
            },
            {
              ...hierarchy.roots[0].children[0],
              id: "id:training",
              name: "Workspace Guests Training",
              path: "/Workspace Guests Training",
              user_move_protected: false,
              children: []
            }
          ]
        }
      ]
    });
    renderOrganizationalUnits({ canCreate: true });

    await user.click(await screen.findByRole("treeitem", { name: "Workspace Guests (/Workspace Guests)" }));
    expect(screen.queryByRole("button", { name: "Create child OU" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit description" })).not.toBeInTheDocument();
    expect(screen.getByText(/Workspace Guests and its descendants are protected/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Expand Workspace Guests" }));
    await user.click(screen.getByRole("treeitem", { name: "Contractors (/Workspace Guests/Contractors)" }));
    expect(screen.queryByRole("button", { name: "Create child OU" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit description" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("treeitem", { name: "Workspace Guests Training (/Workspace Guests Training)" }));
    expect(screen.getByRole("button", { name: "Create child OU" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Edit description" })).toBeVisible();
  });

  it("protects the root description while allowing ordinary child descriptions", async () => {
    const user = userEvent.setup();
    renderOrganizationalUnits({ canCreate: true });

    expect(await screen.findByRole("heading", { name: "Example Workspace" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Edit description" })).not.toBeInTheDocument();
    expect(screen.getByText(/root Organizational Unit description is protected/)).toBeVisible();

    await user.click(screen.getByRole("treeitem", { name: "Engineering (/Engineering)" }));
    expect(screen.getByRole("button", { name: "Edit description" })).toBeVisible();
  });

  it("hides creation from non-administrators", async () => {
    renderOrganizationalUnits({ canCreate: false });
    expect(await screen.findByRole("tree")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create child OU" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit description" })).not.toBeInTheDocument();
  });
});
