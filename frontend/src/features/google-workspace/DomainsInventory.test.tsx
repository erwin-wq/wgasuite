import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, listGoogleWorkspaceDomains } from "../../api/client";
import type { ConnectorConfig, GoogleWorkspaceDomainInventory } from "../../types";
import { DIRECTORY_DOMAIN_READONLY_SCOPE } from "./scopes";
import { DomainsInventory } from "./DomainsInventory";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, listGoogleWorkspaceDomains: vi.fn() };
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
  created_at: "2026-11-23T08:00:00Z",
  updated_at: "2026-11-23T08:00:00Z",
  last_tested_at: "2026-11-23T08:00:00Z",
  last_error_code: null,
  last_error: null
};

const inventory: GoogleWorkspaceDomainInventory = {
  domains: [
    { name: "example.test", kind: "primary", verified: true, creation_time: 1700000000 },
    { name: "secondary.example.test", kind: "secondary", verified: false, creation_time: null },
    { name: "unknown.example.test", kind: "domain", verified: null, creation_time: null }
  ],
  aliases: [
    {
      name: "alias.example.test",
      parent_domain: "example.test",
      kind: "alias",
      verified: true,
      creation_time: 1700000001
    }
  ],
  domain_count: 3,
  alias_count: 1,
  read_only: true
};

function renderInventory(overrides = {}) {
  return render(
    <DomainsInventory
      organizationId="organization-1"
      organizationName="Example Workspace"
      connectorConfig={connectedConfig}
      canRead
      {...overrides}
    />
  );
}

describe("DomainsInventory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listGoogleWorkspaceDomains).mockResolvedValue(inventory);
  });

  it("renders domains, aliases, classifications and authoritative metadata", async () => {
    renderInventory();

    expect(await screen.findByRole("table", { name: "Google Workspace domains and aliases" })).toBeVisible();
    expect(screen.getByText("3", { selector: "strong" })).toBeVisible();
    expect(screen.getAllByText("1", { selector: "strong" })).toHaveLength(2);
    expect(screen.getByText("Primary domain")).toBeVisible();
    expect(screen.getByText("Secondary domain")).toBeVisible();
    expect(screen.getByText("Alias")).toBeVisible();
    expect(screen.getByText("alias.example.test")).toBeVisible();
    expect(screen.getByText("Not verified")).toBeVisible();
    expect(screen.getByText("Unknown")).toBeVisible();
    expect(listGoogleWorkspaceDomains).toHaveBeenCalledWith(
      "organization-1",
      expect.any(AbortSignal)
    );
  });

  it("searches domain, alias, parent and classification fields", async () => {
    const user = userEvent.setup();
    renderInventory();
    await screen.findByText("alias.example.test");

    await user.type(screen.getByRole("searchbox", { name: "Search domains and aliases" }), "alias");

    expect(screen.getByText("alias.example.test")).toBeVisible();
    expect(screen.queryByText("secondary.example.test")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByText("secondary.example.test")).toBeVisible();
  });

  it("shows an accessible empty result without inventing inventory", async () => {
    vi.mocked(listGoogleWorkspaceDomains).mockResolvedValue({
      domains: [], aliases: [], domain_count: 0, alias_count: 0, read_only: true
    });
    renderInventory();

    expect(await screen.findByRole("heading", { name: "No domains returned" })).toBeVisible();
  });

  it("explains the least-privilege scope when Google denies access", async () => {
    vi.mocked(listGoogleWorkspaceDomains).mockRejectedValue(
      new ApiError("Denied", 403, "missing_scope_or_permission")
    );
    renderInventory();

    expect(await screen.findByRole("heading", { name: "Domain inventory unavailable" })).toBeVisible();
    expect(screen.getByText(new RegExp(DIRECTORY_DOMAIN_READONLY_SCOPE))).toBeVisible();
  });

  it("does not load before organization, access, and connector preconditions pass", () => {
    const { rerender } = render(
      <DomainsInventory organizationId="" organizationName={null} connectorConfig={null} canRead />
    );
    expect(screen.getByRole("heading", { name: "Select an organization" })).toBeVisible();

    rerender(
      <DomainsInventory organizationId="organization-1" organizationName="Example" connectorConfig={connectedConfig} canRead={false} />
    );
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

    rerender(
      <DomainsInventory organizationId="organization-1" organizationName="Example" connectorConfig={{ ...connectedConfig, status: "configured" }} canRead />
    );
    expect(screen.getByRole("heading", { name: "Connect Google Workspace" })).toBeVisible();
    expect(listGoogleWorkspaceDomains).not.toHaveBeenCalled();
  });

  it("cancels stale tenant requests and renders only the current tenant", async () => {
    let resolveFirst!: (value: GoogleWorkspaceDomainInventory) => void;
    const first = new Promise<GoogleWorkspaceDomainInventory>((resolve) => {
      resolveFirst = resolve;
    });
    vi.mocked(listGoogleWorkspaceDomains)
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({
        domains: [{ name: "current.example.test", kind: "primary", verified: true, creation_time: null }],
        aliases: [], domain_count: 1, alias_count: 0, read_only: true
      });
    const { rerender } = renderInventory();

    rerender(
      <DomainsInventory organizationId="organization-2" organizationName="Current" connectorConfig={{ ...connectedConfig, organization_id: "organization-2" }} canRead />
    );
    expect(await screen.findByText("current.example.test")).toBeVisible();

    resolveFirst({
      domains: [{ name: "stale.example.test", kind: "primary", verified: true, creation_time: null }],
      aliases: [], domain_count: 1, alias_count: 0, read_only: true
    });
    await waitFor(() => expect(screen.queryByText("stale.example.test")).not.toBeInTheDocument());
  });
});
