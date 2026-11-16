import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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
    theme: "navy-teal",
    density: "comfortable",
    onThemeChange: vi.fn(),
    onDensityChange: vi.fn(),
    onCustomerChange: vi.fn(),
    onOrganizationChange: vi.fn(),
    onLogout: vi.fn(),
    children: <p>Route content</p>,
    ...overrides
  };
  return render(<MemoryRouter initialEntries={[appRoutes.users.path]}><AppShell {...props} /></MemoryRouter>);
}

function ThemeSwitchHarness() {
  const [theme, setTheme] = useState<React.ComponentProps<typeof AppShell>["theme"]>("navy-teal");
  const [density, setDensity] = useState<React.ComponentProps<typeof AppShell>["density"]>("comfortable");
  return (
    <MemoryRouter initialEntries={[appRoutes.users.path]}>
      <AppShell
        currentUser={user}
        currentRoute={appRoutes.users}
        navigationRoutes={routeList}
        customers={customers}
        organizations={organizations}
        selectedCustomerId="customer-1"
        selectedOrganizationId="organization-1"
        isLoading={false}
        isConnected
        theme={theme}
        density={density}
        onThemeChange={setTheme}
        onDensityChange={setDensity}
        onCustomerChange={vi.fn()}
        onOrganizationChange={vi.fn()}
        onLogout={vi.fn()}
      >
        <label>Workflow draft<input defaultValue="Preserve this value" /></label>
      </AppShell>
    </MemoryRouter>
  );
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
    await userEvents.click(screen.getByRole("button", { name: /Test Operator/i }));
    await userEvents.click(screen.getByRole("menuitem", { name: "Logout" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("offers all themes with keyboard navigation and exposes the current selection", async () => {
    const onThemeChange = vi.fn();
    const userEvents = userEvent.setup();
    renderShell({ theme: "cobalt-ice", onThemeChange });

    await userEvents.click(screen.getByRole("button", { name: /Test Operator/i }));
    const selected = screen.getByRole("menuitemradio", { name: /Cobalt & Ice/i });
    expect(selected).toHaveAttribute("aria-checked", "true");
    expect(selected).toHaveFocus();

    await userEvents.keyboard("{ArrowDown}{Enter}");
    expect(onThemeChange).toHaveBeenCalledWith("graphite-copper");
  });

  it("offers both density modes and exposes the current selection", async () => {
    const onDensityChange = vi.fn();
    const userEvents = userEvent.setup();
    renderShell({ density: "compact", onDensityChange });

    await userEvents.click(screen.getByRole("button", { name: /Test Operator/i }));
    expect(screen.getByRole("menuitemradio", { name: /Compact/i })).toHaveAttribute(
      "aria-checked",
      "true"
    );
    await userEvents.click(screen.getByRole("menuitemradio", { name: /Comfortable/i }));
    expect(onDensityChange).toHaveBeenCalledWith("comfortable");
  });

  it("changes themes without remounting the active workflow", async () => {
    const userEvents = userEvent.setup();
    render(<ThemeSwitchHarness />);
    const workflowDraft = screen.getByLabelText("Workflow draft");
    await userEvents.clear(workflowDraft);
    await userEvents.type(workflowDraft, "Unsaved domain state");

    await userEvents.click(screen.getByRole("button", { name: /Account and appearance/i }));
    await userEvents.click(screen.getByRole("menuitemradio", { name: /Graphite & Copper/i }));
    await userEvents.click(screen.getByRole("menuitemradio", { name: /Compact/i }));

    expect(screen.getByLabelText("Workflow draft")).toHaveValue("Unsaved domain state");
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
