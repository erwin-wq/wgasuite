import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { appRoutes, routeList } from "../../app/routes";
import type { Customer, Organization, User } from "../../types";
import { AppShell } from "./AppShell";

const user: User = {
  id: "user-1",
  email: "operator@example.test",
  full_name: "Test Operator",
  role: "platform_admin",
  is_active: true,
  created_at: "2026-11-14T08:00:00Z",
  customer_memberships: []
};
const customers: Customer[] = [{
  id: "customer-1",
  name: "Example Customer",
  slug: "example",
  contact_name: null,
  contact_email: null,
  status: "active",
  notes: null,
  created_at: "2026-11-14T08:00:00Z",
  updated_at: "2026-11-14T08:00:00Z"
}];
const organizations: Organization[] = [{
  id: "organization-1",
  customer_id: "customer-1",
  name: "Example Workspace",
  description: null,
  created_at: "2026-11-14T08:00:00Z",
  updated_at: "2026-11-14T08:00:00Z"
}];

function renderShell(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  const props: React.ComponentProps<typeof AppShell> = {
    currentUser: user,
    currentRoute: appRoutes.users,
    navigationRoutes: routeList,
    customers,
    organizations,
    selectedCustomerId: "customer-1",
    selectedOrganizationId: "organization-1",
    isLoading: false,
    isConnected: true,
    onCustomerChange: vi.fn(),
    onOrganizationChange: vi.fn(),
    onLogout: vi.fn(),
    children: <p>Route content</p>,
    ...overrides
  };
  return render(<MemoryRouter initialEntries={[appRoutes.users.path]}><AppShell {...props} /></MemoryRouter>);
}

describe("premium AppShell", () => {
  it("renders grouped route navigation, breadcrumbs and the active route", () => {
    renderShell();
    expect(screen.getByRole("link", { name: "Users" })).toHaveClass("active");
    expect(screen.getByRole("heading", { name: "User directory" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Directory/Users");
    expect(screen.getByText("Route content")).toBeVisible();
  });

  it("collapses the sidebar and exposes the global tenant controls", async () => {
    const onOrganizationChange = vi.fn();
    const userEvents = userEvent.setup();
    renderShell({ onOrganizationChange });
    await userEvents.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
    await userEvents.click(screen.getByRole("button", { name: /Active workspace/i }));
    await userEvents.selectOptions(screen.getByLabelText("Organization"), "organization-1");
    expect(onOrganizationChange).toHaveBeenCalledWith("organization-1");
  });

  it("shows only routes supplied by role-aware filtering and logs out explicitly", async () => {
    const onLogout = vi.fn();
    const userEvents = userEvent.setup();
    renderShell({ navigationRoutes: [appRoutes.overview, appRoutes.users], onLogout });
    expect(screen.queryByRole("link", { name: "Platform" })).not.toBeInTheDocument();
    await userEvents.click(screen.getByRole("button", { name: "Logout" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("opens and closes the mobile drawer with Escape", async () => {
    const userEvents = userEvent.setup();
    renderShell();
    const openButton = screen.getByRole("button", { name: "Open navigation" });
    await userEvents.click(openButton);
    expect(openButton).toHaveAttribute("aria-expanded", "true");
    await userEvents.keyboard("{Escape}");
    expect(openButton).toHaveAttribute("aria-expanded", "false");
  });
});
