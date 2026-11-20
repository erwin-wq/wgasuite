import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import App from "./App";
import { routeList } from "./app/routes";

const api = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  getPlatformAdminOverview: vi.fn(),
  getStoredAuthToken: vi.fn(),
  listCustomers: vi.fn(),
  listOrganizationConnectorConfigs: vi.fn(),
  listOrganizations: vi.fn()
}));

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, ...api };
});

describe("App URL routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getStoredAuthToken.mockReturnValue("test-session");
    api.getCurrentUser.mockResolvedValue({
      id: "user-1",
      email: "operator@example.test",
      full_name: "Test Operator",
      role: "platform_admin",
      is_active: true,
      created_at: "2026-11-14T08:00:00Z",
      customer_memberships: []
    });
    api.listCustomers.mockResolvedValue([{ id: "customer-1", name: "Example Customer", slug: "example", contact_name: null, contact_email: null, status: "active", notes: null, created_at: "2026-11-14T08:00:00Z", updated_at: "2026-11-14T08:00:00Z" }]);
    api.listOrganizations.mockResolvedValue([{ id: "organization-1", customer_id: "customer-1", name: "Example Workspace", description: null, created_at: "2026-11-14T08:00:00Z", updated_at: "2026-11-14T08:00:00Z" }]);
    api.listOrganizationConnectorConfigs.mockResolvedValue([]);
    api.getPlatformAdminOverview.mockResolvedValue({
      counts: { customers: 1, organizations: 1, users: 1, connector_configs: 0, audit_events: 0 },
      customers: [],
      users: [],
      recent_scan_runs: [],
      recent_audit_events: []
    });
  });

  afterEach(() => cleanup());

  for (const route of routeList) {
    it(`renders the ${route.path} direct URL`, async () => {
      render(<MemoryRouter initialEntries={[route.path]}><App /></MemoryRouter>);
      expect(await screen.findByRole("heading", { level: 1, name: route.title })).toBeVisible();
      expect(screen.queryByRole("heading", { name: "Page not found" })).not.toBeInTheDocument();
    });
  }

  it("renders a safe 404 without interpreting path segments as identifiers", async () => {
    render(<MemoryRouter initialEntries={["/directory/users/private@example.test"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeVisible();
    expect(screen.queryByText("private@example.test")).not.toBeInTheDocument();
  });

  it("redirects unauthenticated direct URLs to login", async () => {
    api.getStoredAuthToken.mockReturnValue(null);
    render(<MemoryRouter initialEntries={["/directory/groups"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "WGASuite" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Inloggen" })).toBeVisible();
  });

  it("enforces platform authorization on a direct URL", async () => {
    api.getCurrentUser.mockResolvedValue({
      id: "user-2",
      email: "customer-user@example.test",
      full_name: "Customer User",
      role: "customer_user",
      is_active: true,
      created_at: "2026-11-14T08:00:00Z",
      customer_memberships: [{
        customer_id: "customer-1",
        customer_name: "Example Customer",
        role: "customer_user",
        is_active: true
      }]
    });

    render(<MemoryRouter initialEntries={["/platform"]}><App /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Access unavailable" })).toBeVisible();
    expect(api.getPlatformAdminOverview).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Read-only support overview" })).not.toBeInTheDocument();
  });

  it("falls back safely when a tenant switch invalidates route access", async () => {
    api.getCurrentUser.mockResolvedValue({
      id: "user-2",
      email: "customer-user@example.test",
      full_name: "Customer User",
      role: "customer_user",
      is_active: true,
      created_at: "2026-11-14T08:00:00Z",
      customer_memberships: [{
        customer_id: "customer-1",
        customer_name: "Example Customer",
        role: "customer_user",
        is_active: true
      }]
    });
    api.listCustomers.mockResolvedValue([
      { id: "customer-1", name: "Example Customer", slug: "example", contact_name: null, contact_email: null, status: "active", notes: null, created_at: "2026-11-14T08:00:00Z", updated_at: "2026-11-14T08:00:00Z" },
      { id: "customer-2", name: "Other Customer", slug: "other", contact_name: null, contact_email: null, status: "active", notes: null, created_at: "2026-11-14T08:00:00Z", updated_at: "2026-11-14T08:00:00Z" }
    ]);
    api.listOrganizations.mockResolvedValue([
      { id: "organization-1", customer_id: "customer-1", name: "Example Workspace", description: null, created_at: "2026-11-14T08:00:00Z", updated_at: "2026-11-14T08:00:00Z" },
      { id: "organization-2", customer_id: "customer-2", name: "Other Workspace", description: null, created_at: "2026-11-14T08:00:00Z", updated_at: "2026-11-14T08:00:00Z" }
    ]);
    const events = userEvent.setup();
    render(<MemoryRouter initialEntries={["/directory/users"]}><App /></MemoryRouter>);
    await screen.findByRole("heading", { level: 1, name: "User directory" });
    await events.click(screen.getByRole("button", { name: /Active workspace/i }));
    await events.selectOptions(screen.getByLabelText("Customer"), "customer-2");
    expect(await screen.findByRole("heading", { level: 1, name: "Workspace overview" })).toBeVisible();
    expect(screen.queryByText("Access unavailable")).not.toBeInTheDocument();
  });
});
