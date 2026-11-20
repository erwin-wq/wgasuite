import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Customer, Organization, PlatformAdminOverview } from "../../types";
import { CustomerAdministration } from "./CustomerAdministration";
import { OrganizationAdministration } from "./OrganizationAdministration";
import { PlatformAdministration } from "./PlatformAdministration";

const customer: Customer = {
  id: "customer-1",
  name: "Northstar Labs",
  slug: "northstar-labs",
  contact_name: "Alex Morgan",
  contact_email: "alex@example.test",
  status: "active",
  notes: null,
  created_at: "2026-11-20T10:00:00Z",
  updated_at: "2026-11-20T10:00:00Z"
};

const organization: Organization = {
  id: "organization-1",
  customer_id: customer.id,
  name: "Northstar Workspace",
  description: "Primary tenant",
  created_at: "2026-11-20T10:00:00Z",
  updated_at: "2026-11-20T10:00:00Z"
};

const overview: PlatformAdminOverview = {
  totals: {
    customers_count: 1,
    organizations_count: 1,
    assessments_count: 0,
    connector_configs_count: 1,
    scan_runs_count: 0,
    audit_events_count: 12
  },
  customers: [{
    id: customer.id,
    name: customer.name,
    slug: customer.slug,
    status: customer.status,
    organization_count: 1,
    connector_config_count: 1,
    last_scan_run_at: null,
    last_audit_event_at: "2026-11-20T10:00:00Z"
  }],
  connector_configs: [{
    id: "connector-1",
    customer_id: customer.id,
    customer_name: customer.name,
    organization_id: organization.id,
    organization_name: organization.name,
    connector_type: "google_workspace",
    status: "connected",
    auth_method: "service_account_domain_wide_delegation",
    primary_domain: "example.test",
    last_tested_at: "2026-11-20T10:00:00Z",
    last_error: null
  }],
  recent_scan_runs: [],
  recent_audit_events: [{
    id: "audit-1",
    created_at: "2026-11-20T10:00:00Z",
    actor_email: "operator@example.test",
    actor_role: "platform_admin",
    customer_id: customer.id,
    customer_name: customer.name,
    action: "connector_config.viewed",
    object_type: "connector_config",
    object_id: "connector-1",
    outcome: "success"
  }]
};

const customerFormProps = {
  name: "",
  slug: "",
  contactName: "",
  contactEmail: "",
  status: "active",
  notes: "",
  onNameChange: vi.fn(),
  onSlugChange: vi.fn(),
  onContactNameChange: vi.fn(),
  onContactEmailChange: vi.fn(),
  onStatusChange: vi.fn(),
  onNotesChange: vi.fn(),
  onCreate: vi.fn(async () => true)
};

describe("premium administration pages", () => {
  it("shows customer relationships and restores focus after closing create", async () => {
    const user = userEvent.setup();
    const onSelectCustomer = vi.fn();
    render(
      <CustomerAdministration
        {...customerFormProps}
        customers={[customer]}
        organizations={[organization]}
        selectedCustomerId=""
        isLoading={false}
        isSaving={false}
        onSelectCustomer={onSelectCustomer}
      />
    );

    expect(screen.getByRole("table", { name: "Platform customers" })).toHaveTextContent("Northstar Labs");
    expect(screen.getByRole("table", { name: "Platform customers" })).toHaveTextContent("1");
    await user.click(screen.getByRole("button", { name: "Use context" }));
    expect(onSelectCustomer).toHaveBeenCalledWith(customer.id);

    const trigger = screen.getByRole("button", { name: "Create customer" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Create customer" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(trigger).toHaveFocus();
  });

  it("uses global customer context and hides unauthorized organization creation", () => {
    render(
      <OrganizationAdministration
        customer={customer}
        organizations={[organization]}
        selectedOrganizationId={organization.id}
        isLoading={false}
        canCreate={false}
        isSaving={false}
        name=""
        description=""
        onNameChange={vi.fn()}
        onDescriptionChange={vi.fn()}
        onCreate={vi.fn(async () => true)}
        onSelectOrganization={vi.fn()}
      />
    );

    expect(screen.getByText(/Change customer context in the global header/)).toBeVisible();
    expect(screen.queryByLabelText("Customer")).not.toBeInTheDocument();
    expect(screen.getByText("Active workspace")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create organization" })).not.toBeInTheDocument();
  });

  it("renders real platform totals and non-secret support tables", () => {
    render(
      <PlatformAdministration
        overview={overview}
        loading={false}
        error={null}
        demoFeaturesEnabled={false}
        onRefresh={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Platform totals")).toHaveTextContent("12");
    expect(screen.getByRole("table", { name: "Platform connector status" })).toHaveTextContent("example.test");
    expect(screen.getByRole("table", { name: "Recent platform audit events" })).toHaveTextContent("connector_config.viewed");
    expect(screen.queryByText(/credential/i)).not.toBeInTheDocument();
  });

  it("keeps platform API failures distinct and retryable", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    render(
      <PlatformAdministration
        overview={null}
        loading={false}
        error="The platform support overview could not be loaded."
        demoFeaturesEnabled={false}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getByRole("heading", { name: "Platform overview unavailable" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
