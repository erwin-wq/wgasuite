import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ConnectorConfig } from "../../types";
import { GoogleWorkspaceAdministration } from "./GoogleWorkspaceAdministration";

const connectedConfig: ConnectorConfig = {
  id: "connector-1",
  organization_id: "organization-1",
  connector_type: "google_workspace",
  auth_method: "service_account_domain_wide_delegation",
  status: "connected",
  display_name: "Preserved connector name",
  primary_domain: "example.test",
  admin_subject_email: "admin@example.test",
  credential_provider: "managed_file",
  credentials_configured: true,
  service_account_email: "service@example.test",
  service_account_client_id: "1234567890",
  notes: "Preserved notes",
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T10:00:00Z",
  last_tested_at: "2026-10-10T10:00:00Z",
  last_error_code: null,
  last_error: null
};

function renderAdministration(connectorConfig: ConnectorConfig | null = connectedConfig) {
  return render(
    <GoogleWorkspaceAdministration
      organizationId="organization-1"
      organizationName="Northstar Workspace"
      connectorConfig={connectorConfig}
      canManageConnection
      connectionWizard={
        <div data-testid="connection-wizard">{connectorConfig?.display_name ?? "New connection"}</div>
      }
      userLookup={<div data-testid="user-lookup">User lookup tool</div>}
    />
  );
}

describe("GoogleWorkspaceAdministration", () => {
  it("keeps the connected status compact and opens the existing wizard on demand", async () => {
    const user = userEvent.setup();
    renderAdministration();

    expect(screen.getByText("Connected")).toBeVisible();
    expect(screen.getByText("Directory users · read only")).toBeVisible();
    expect(screen.getByTestId("user-lookup")).toBeVisible();
    expect(screen.queryByTestId("connection-wizard")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Manage connection" }));
    expect(screen.getByTestId("connection-wizard")).toHaveTextContent("Preserved connector name");
    expect(screen.getByRole("button", { name: "Close configuration" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
  });

  it("shows setup prominently when no connector is configured", () => {
    renderAdministration(null);

    expect(screen.getByRole("heading", { name: "Connect Google Workspace" })).toBeVisible();
    expect(screen.getByTestId("connection-wizard")).toBeVisible();
    expect(screen.getByTestId("user-lookup")).toBeVisible();
  });

  it("shows the persisted connection failure and an inspection action", async () => {
    const user = userEvent.setup();
    const failedConfig: ConnectorConfig = {
      ...connectedConfig,
      status: "connection_failed",
      last_error_code: "google_forbidden",
      last_error: "Google denied the delegated Directory request."
    };
    renderAdministration(failedConfig);

    expect(screen.getByText("Connection failed")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Google denied");
    await user.click(screen.getByRole("button", { name: "Inspect configuration" }));
    expect(screen.getByTestId("connection-wizard")).toBeVisible();
  });
});
