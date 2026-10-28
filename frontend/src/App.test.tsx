import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConnectorConfig } from "./types";
import App from "./App";

const api = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  getStoredAuthToken: vi.fn(),
  listCustomers: vi.fn(),
  listGoogleWorkspaceUsers: vi.fn(),
  listOrganizationConnectorConfigs: vi.fn(),
  listOrganizations: vi.fn(),
  testConnectorConfig: vi.fn()
}));

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, ...api };
});

const connector: ConnectorConfig = {
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
  created_at: "2026-10-28T10:00:00Z",
  updated_at: "2026-10-28T10:00:00Z",
  last_tested_at: "2026-10-28T10:00:00Z",
  last_error_code: null,
  last_error: null
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("App Google Workspace connection refresh", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getStoredAuthToken.mockReturnValue("test-session");
    api.getCurrentUser.mockResolvedValue({
      id: "user-1",
      email: "operator@example.test",
      full_name: "Test Operator",
      role: "platform_admin",
      is_active: true,
      created_at: "2026-10-28T09:00:00Z",
      customer_memberships: []
    });
    api.listCustomers.mockResolvedValue([
      {
        id: "customer-1",
        name: "Example Customer",
        slug: "example-customer",
        contact_name: null,
        contact_email: null,
        status: "active",
        notes: null,
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z"
      }
    ]);
    api.listOrganizations.mockResolvedValue([
      {
        id: "organization-1",
        customer_id: "customer-1",
        name: "Example Workspace",
        description: null,
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z"
      }
    ]);
    api.listGoogleWorkspaceUsers.mockResolvedValue({ users: [], next_page_token: null });
    api.testConnectorConfig.mockResolvedValue({
      status: "connected",
      tested_at: "2026-10-28T10:05:00Z",
      message: "Connected with read-only Directory access.",
      error_code: null,
      error_category: null,
      retryable: false,
      persisted: true
    });
  });

  it("keeps the wizard and successful feedback mounted while refreshing the same connector", async () => {
    const refresh = deferred<ConnectorConfig[]>();
    api.listOrganizationConnectorConfigs
      .mockResolvedValueOnce([connector])
      .mockReturnValueOnce(refresh.promise);
    const user = userEvent.setup();

    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Google Workspace" }));
    await user.click(await screen.findByRole("button", { name: "Manage connection" }));
    expect(
      await screen.findByRole("heading", { name: "Test the real Google Workspace connection" })
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: /^Test connection$/ }));
    await waitFor(() => expect(api.listOrganizationConnectorConfigs).toHaveBeenCalledTimes(2));

    expect(
      screen.getByRole("heading", { name: "Test the real Google Workspace connection" })
    ).toBeVisible();
    refresh.resolve([{ ...connector, last_tested_at: "2026-10-28T10:05:00Z" }]);

    expect(await screen.findByText("Connected with read-only Directory access.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Close configuration" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
  });
});
