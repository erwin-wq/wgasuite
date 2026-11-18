import type { ComponentProps } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { appRoutes } from "../../app/routes";
import type { ConnectorConfig } from "../../types";
import { DashboardOverview } from "./DashboardOverview";

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
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T10:00:00Z",
  last_tested_at: "2026-10-10T10:00:00Z",
  last_error_code: null,
  last_error: null
};

const failedConfig: ConnectorConfig = {
  ...connectedConfig,
  status: "connection_failed",
  last_error_code: "google_forbidden",
  last_error: "Directory access could not be verified."
};

const defaultProps: ComponentProps<typeof DashboardOverview> = {
  customerName: "Northstar Demo",
  organizationName: "Northstar Workspace",
  connectorConfig: connectedConfig,
  isLoading: false,
  hasLoadError: false,
  canOperateWorkspace: true,
  canViewConnections: true
};

function LocationProbe() {
  return <output aria-label="Current path">{useLocation().pathname}</output>;
}

function renderDashboard(props = defaultProps) {
  return render(
    <MemoryRouter initialEntries={[appRoutes.overview.path]}>
      <DashboardOverview {...props} />
      <LocationProbe />
    </MemoryRouter>
  );
}

describe("DashboardOverview", () => {
  it("shows truthful connected state and routes every supported quick action", async () => {
    const user = userEvent.setup();
    renderDashboard();

    expect(screen.getAllByText("Connected")).toHaveLength(2);
    expect(screen.getByText(/Last verified/i)).toBeVisible();
    expect(screen.queryByText(/assessment|security score|user count/i)).not.toBeInTheDocument();

    const actions = [
      ["Find a user", appRoutes.userLookup.path],
      ["Manage groups", appRoutes.groups.path],
      ["View organizational units", appRoutes.orgUnits.path],
      ["Gmail delegations", appRoutes.delegations.path]
    ] as const;
    const actionNavigation = screen.getByRole("navigation", { name: "Common Workspace tasks" });

    for (const [name, path] of actions) {
      await user.click(within(actionNavigation).getByRole("link", { name: new RegExp(name, "i") }));
      expect(screen.getByLabelText("Current path")).toHaveTextContent(path);
    }
  });

  it("shows the failed connector state and offers connection settings", async () => {
    const user = userEvent.setup();
    renderDashboard({ ...defaultProps, connectorConfig: failedConfig });

    expect(screen.getAllByText("Connection failed")).toHaveLength(2);
    expect(screen.getAllByText(/latest connector test did not verify/i)).toHaveLength(2);

    await user.click(screen.getByRole("link", { name: "Review connection" }));
    expect(screen.getByLabelText("Current path")).toHaveTextContent(appRoutes.connections.path);
  });

  it("distinguishes saved but unverified configuration from no configuration", () => {
    renderDashboard({
      ...defaultProps,
      connectorConfig: { ...connectedConfig, status: "configured", last_tested_at: null }
    });

    expect(screen.getAllByText("Disconnected")).toHaveLength(2);
    expect(screen.getAllByText(/settings are saved, but Directory access is not verified/i)).toHaveLength(2);
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });

  it("renders a loading state without briefly claiming the connector is unconfigured", () => {
    renderDashboard({ ...defaultProps, connectorConfig: null, isLoading: true });

    expect(screen.getByLabelText("Loading connection status")).toBeVisible();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Common Workspace tasks" })).not.toBeInTheDocument();
  });

  it("does not present an API failure as an unconfigured connector", () => {
    renderDashboard({
      ...defaultProps,
      connectorConfig: null,
      hasLoadError: true
    });

    expect(screen.getAllByText("Status unavailable")).toHaveLength(2);
    expect(screen.getAllByText(/Connection status could not be loaded/i)).toHaveLength(2);
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });

  it("explains missing tenant context without duplicating customer details", () => {
    renderDashboard({
      ...defaultProps,
      customerName: null,
      organizationName: null,
      connectorConfig: null,
      canOperateWorkspace: false,
      canViewConnections: false
    });

    expect(screen.getAllByText("No customer selected")).toHaveLength(2);
    expect(screen.getByText(/Select a workspace to see available/i)).toBeVisible();
    expect(screen.queryByRole("link", { name: /Connection settings/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Northstar Demo")).not.toBeInTheDocument();
  });

  it("keeps read-only connection information visible while hiding operator actions", () => {
    renderDashboard({ ...defaultProps, canOperateWorkspace: false });

    expect(screen.getAllByText("Connected")).toHaveLength(2);
    expect(screen.getByText(/current role does not provide/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /Connection settings/i })).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Common Workspace tasks" })).not.toBeInTheDocument();
  });

  it("updates cleanly when the selected tenant changes", () => {
    const { rerender } = renderDashboard();

    rerender(
      <MemoryRouter initialEntries={[appRoutes.overview.path]}>
        <DashboardOverview
          {...defaultProps}
          organizationName="Second Workspace"
          connectorConfig={null}
        />
        <LocationProbe />
      </MemoryRouter>
    );

    expect(screen.getAllByText("Not configured")).toHaveLength(2);
    expect(screen.queryByText(/Directory access is available/i)).not.toBeInTheDocument();
  });

  it("supports keyboard navigation to a quick action", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.tab();
    expect(screen.getByRole("link", { name: /Connection settings/i })).toHaveFocus();
    await user.tab();
    expect(document.activeElement).toHaveAttribute("href", appRoutes.userLookup.path);
    await user.keyboard("{Enter}");
    expect(screen.getByLabelText("Current path")).toHaveTextContent(appRoutes.userLookup.path);
  });
});
