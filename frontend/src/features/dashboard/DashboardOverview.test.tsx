import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

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

describe("DashboardOverview", () => {
  it("shows active context and recommends user lookup when Workspace is connected", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(
      <DashboardOverview
        customerName="Northstar Demo"
        organizationName="Northstar Workspace"
        connectorConfig={connectedConfig}
        onNavigate={onNavigate}
      />
    );

    expect(screen.getByText("Northstar Demo")).toBeVisible();
    expect(screen.getByText("Northstar Workspace")).toBeVisible();
    expect(screen.getByText("Connected")).toBeVisible();
    expect(screen.getByText("Not assessed")).toBeVisible();
    expect(screen.queryByText(/zero risk/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/mock scan/i)).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Open User Lookup" })[0]);
    expect(onNavigate).toHaveBeenCalledWith("google-workspace");
  });

  it("recommends the missing real context instead of an assessment", () => {
    render(
      <DashboardOverview
        customerName="Northstar Demo"
        organizationName={null}
        connectorConfig={null}
        onNavigate={vi.fn()}
      />
    );

    expect(screen.getByText("Select or create an organization")).toBeVisible();
    expect(screen.getByRole("button", { name: "Open Organizations" })).toBeVisible();
    expect(screen.queryByText(/assessment workspace/i)).not.toBeInTheDocument();
  });
});
