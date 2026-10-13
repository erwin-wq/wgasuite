import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceDirectoryUser,
  GoogleWorkspaceUserDirectoryResult
} from "../../types";
import { UserDirectory } from "./UserDirectory";

const api = vi.hoisted(() => ({
  listGoogleWorkspaceUsers: vi.fn()
}));

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return { ...actual, ...api };
});

const connectedConfig: ConnectorConfig = {
  id: "connector-1",
  organization_id: "organization-1",
  connector_type: "google_workspace",
  auth_method: "service_account_domain_wide_delegation",
  status: "connected",
  display_name: "Google Workspace",
  primary_domain: "primary.example",
  admin_subject_email: "admin@primary.example",
  credential_provider: "managed_file",
  credentials_configured: true,
  service_account_email: "synthetic@project.iam.gserviceaccount.com",
  service_account_client_id: "123456789012345678901",
  notes: null,
  created_at: "2026-10-10T08:00:00Z",
  updated_at: "2026-10-10T08:00:00Z",
  last_tested_at: "2026-10-10T08:01:00Z",
  last_error_code: null,
  last_error: null
};

const directoryUser: GoogleWorkspaceDirectoryUser = {
  id: "user-1",
  full_name: "Alex Example",
  given_name: "Alex",
  family_name: "Example",
  primary_email: "alex@primary.example",
  org_unit_path: "/Engineering",
  suspended: false,
  archived: false,
  is_super_admin: true,
  is_delegated_admin: false,
  creation_time: "2024-01-02T03:04:05Z",
  last_login_time: "2026-09-10T11:12:13Z"
};

const result: GoogleWorkspaceUserDirectoryResult = {
  users: [directoryUser],
  next_page_token: "next-users"
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function renderDirectory(overrides = {}) {
  const props = {
    organizationId: "organization-1",
    organizationName: "Primary Workspace",
    connectorConfig: connectedConfig,
    canSearch: true,
    onSelectUser: vi.fn(),
    ...overrides
  };
  return { ...render(<UserDirectory {...props} />), props };
}

describe("UserDirectory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listGoogleWorkspaceUsers.mockResolvedValue(result);
  });

  it("loads the first customer-wide page with bounded server options", async () => {
    renderDirectory();

    expect(await screen.findByText("alex@primary.example")).toBeVisible();
    expect(api.listGoogleWorkspaceUsers).toHaveBeenCalledWith(
      "organization-1",
      {
        search: "",
        search_field: "all",
        org_unit_path: null,
        suspended: "all",
        admin_status: "all",
        archived: "all",
        order_by: "email",
        sort_direction: "ascending",
        page_size: 50,
        page_token: null
      },
      expect.any(AbortSignal)
    );
    expect(screen.getByText("Super administrator")).toBeVisible();
    expect(document.querySelector(".directory-table-wrap")).not.toBeNull();
  });

  it("applies search, OU, status, administrator and archive filters server-side", async () => {
    const user = userEvent.setup();
    renderDirectory();
    await screen.findByText("alex@primary.example");

    await user.type(screen.getByLabelText("Search users"), "Alex Example");
    await user.selectOptions(screen.getByLabelText("Search field"), "full_name");
    await user.selectOptions(screen.getByLabelText("Account status"), "active");
    await user.selectOptions(screen.getByLabelText("Administrator"), "delegated_admin");
    await user.selectOptions(screen.getByLabelText("Archive status"), "not_archived");
    await user.type(
      screen.getByRole("textbox", { name: /Organizational unit path/ }),
      "/Engineering"
    );
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(api.listGoogleWorkspaceUsers).toHaveBeenLastCalledWith(
      "organization-1",
      expect.objectContaining({
        search: "Alex Example",
        search_field: "full_name",
        org_unit_path: "/Engineering",
        suspended: "active",
        admin_status: "delegated_admin",
        archived: "not_archived",
        page_token: null
      }),
      expect.any(AbortSignal)
    );
    expect(screen.getByText(/Includes users in descendant/)).toBeVisible();
  });

  it("sorts supported columns and keeps opaque next/previous token history", async () => {
    const user = userEvent.setup();
    renderDirectory();
    await screen.findByText("alex@primary.example");

    await user.click(screen.getByRole("button", { name: "Primary email" }));
    expect(api.listGoogleWorkspaceUsers).toHaveBeenLastCalledWith(
      "organization-1",
      expect.objectContaining({ order_by: "email", sort_direction: "descending" }),
      expect.any(AbortSignal)
    );

    await user.selectOptions(screen.getByLabelText("Sort by"), "family_name");
    await user.selectOptions(screen.getByLabelText("Direction"), "ascending");
    expect(api.listGoogleWorkspaceUsers).toHaveBeenLastCalledWith(
      "organization-1",
      expect.objectContaining({ order_by: "family_name", sort_direction: "ascending" }),
      expect.any(AbortSignal)
    );

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(api.listGoogleWorkspaceUsers).toHaveBeenLastCalledWith(
      "organization-1",
      expect.objectContaining({ page_token: "next-users" }),
      expect.any(AbortSignal)
    );
    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(api.listGoogleWorkspaceUsers).toHaveBeenLastCalledWith(
      "organization-1",
      expect.objectContaining({ page_token: null }),
      expect.any(AbortSignal)
    );
  });

  it("shows empty pages, missing metadata and safe errors", async () => {
    api.listGoogleWorkspaceUsers.mockResolvedValueOnce({
      users: [{
        ...directoryUser,
        full_name: null,
        given_name: null,
        family_name: null,
        org_unit_path: null,
        suspended: null,
        archived: null,
        is_super_admin: null,
        is_delegated_admin: null,
        creation_time: null,
        last_login_time: null
      }],
      next_page_token: null
    });
    const { rerender, props } = renderDirectory();
    expect(await screen.findByText("Name unavailable")).toBeVisible();
    expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(2);

    api.listGoogleWorkspaceUsers.mockResolvedValueOnce({ users: [], next_page_token: "empty-next" });
    rerender(<UserDirectory {...props} organizationId="organization-2" />);
    expect(await screen.findByText(/No users were returned/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();

    api.listGoogleWorkspaceUsers.mockRejectedValueOnce(
      new ApiError("safe token failure", 400, "google_page_token_invalid")
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/page expired/i);
  });

  it("opens the existing exact detail flow with the canonical primary email", async () => {
    const onSelectUser = vi.fn();
    const user = userEvent.setup();
    renderDirectory({ onSelectUser });

    await user.click(await screen.findByRole("button", { name: /Open details/ }));

    expect(onSelectUser).toHaveBeenCalledWith("alex@primary.example");
  });

  it("discards stale results when the selected organization changes", async () => {
    const oldRequest = deferred<GoogleWorkspaceUserDirectoryResult>();
    api.listGoogleWorkspaceUsers
      .mockReset()
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce({
        users: [{ ...directoryUser, id: "user-2", primary_email: "new@secondary.example" }],
        next_page_token: null
      });
    const view = renderDirectory();

    view.rerender(
      <UserDirectory
        {...view.props}
        organizationId="organization-2"
        organizationName="Secondary Workspace"
      />
    );
    expect(await screen.findByText("new@secondary.example")).toBeVisible();
    oldRequest.resolve(result);

    await waitFor(() => expect(screen.queryByText("alex@primary.example")).not.toBeInTheDocument());
  });

  it("renders permission and connector readiness states without requests", () => {
    const view = renderDirectory({ canSearch: false });
    expect(screen.getByText(/Customer administrator access is required/)).toBeVisible();
    expect(api.listGoogleWorkspaceUsers).not.toHaveBeenCalled();

    view.rerender(
      <UserDirectory
        {...view.props}
        canSearch
        connectorConfig={{ ...connectedConfig, status: "configured" }}
      />
    );
    expect(screen.getByText(/successfully test Google Workspace/)).toBeVisible();
    expect(api.listGoogleWorkspaceUsers).not.toHaveBeenCalled();
  });
});
