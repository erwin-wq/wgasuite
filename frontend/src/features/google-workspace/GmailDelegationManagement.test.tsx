import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, lookupGoogleWorkspaceUser } from "../../api/client";
import type { ConnectorConfig, GoogleWorkspaceUser } from "../../types";
import { GmailDelegationManagement } from "./GmailDelegationManagement";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, lookupGoogleWorkspaceUser: vi.fn() };
});

vi.mock("./MailboxDelegates", () => ({
  MailboxDelegates: ({ owner, canMutate }: { owner: GoogleWorkspaceUser; canMutate: boolean }) => (
    <div data-testid="mailbox-delegates">
      Delegates for {owner.primary_email}; writes {canMutate ? "enabled" : "disabled"}
    </div>
  )
}));

const connector: ConnectorConfig = {
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
  service_account_email: "service-account@project.invalid",
  service_account_client_id: "000000000000000000000",
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_tested_at: "2026-11-19T12:00:00Z",
  last_error_code: null,
  last_error: null
};

const owner: GoogleWorkspaceUser = {
  id: "owner-1",
  full_name: "Alexandra Rivera",
  primary_email: "alexandra@primary.example",
  aliases: ["alex@primary.example"],
  non_editable_aliases: [],
  suspended: false,
  archived: false,
  org_unit_path: "/People",
  is_mailbox_setup: true,
  is_super_admin: false,
  is_delegated_admin: false,
  is_guest_user: false,
  creation_time: "2024-01-01T00:00:00Z",
  last_login_time: "2026-11-19T09:00:00Z",
  matched_by: "primary_email"
};

const defaultProps = {
  organizationId: "organization-1",
  organizationName: "Primary organization",
  connectorConfig: connector,
  canSearch: true,
  canManageDelegates: true
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

describe("GmailDelegationManagement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(lookupGoogleWorkspaceUser).mockResolvedValue(owner);
  });

  it("looks up one exact mailbox and passes its canonical identity to the shared delegate workflow", async () => {
    const interaction = userEvent.setup();
    render(<GmailDelegationManagement {...defaultProps} />);

    expect(screen.getByRole("region", { name: "Gmail delegation workflow" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Select a mailbox" })).toBeVisible();
    await interaction.type(screen.getByLabelText("Primary email or user alias"), "Alex@Primary.Example");
    await interaction.click(screen.getByRole("button", { name: "Find mailbox" }));

    expect(lookupGoogleWorkspaceUser).toHaveBeenCalledWith(
      "organization-1",
      "alex@primary.example",
      expect.any(AbortSignal)
    );
    expect(await screen.findByRole("heading", { name: owner.full_name! })).toHaveFocus();
    expect(screen.getByText(owner.primary_email)).toBeVisible();
    expect(screen.getByText("Gmail mailbox set up")).toBeVisible();
    expect(screen.getByTestId("mailbox-delegates")).toHaveTextContent("writes enabled");
  });

  it("validates the supported exact-address lookup before calling the API", async () => {
    const interaction = userEvent.setup();
    render(<GmailDelegationManagement {...defaultProps} />);
    await interaction.type(screen.getByLabelText("Primary email or user alias"), "partial-name");
    await interaction.click(screen.getByRole("button", { name: "Find mailbox" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid full email address.");
    expect(lookupGoogleWorkspaceUser).not.toHaveBeenCalled();
  });

  it("renders a sanitized API error and permission/connection gates", async () => {
    vi.mocked(lookupGoogleWorkspaceUser).mockRejectedValue(
      new ApiError("private upstream detail", 403, "google_forbidden")
    );
    const interaction = userEvent.setup();
    const view = render(<GmailDelegationManagement {...defaultProps} />);
    await interaction.type(screen.getByLabelText("Primary email or user alias"), owner.primary_email);
    await interaction.click(screen.getByRole("button", { name: "Find mailbox" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Google denied this lookup");
    expect(screen.queryByText("private upstream detail")).not.toBeInTheDocument();

    view.rerender(<GmailDelegationManagement {...defaultProps} canSearch={false} />);
    expect(screen.getByText(/Administrator access is required to search/)).toBeVisible();
    view.rerender(
      <GmailDelegationManagement
        {...defaultProps}
        connectorConfig={{ ...connector, status: "connection_failed" }}
      />
    );
    expect(screen.getByText(/Connect and successfully test Google Workspace/)).toBeVisible();
  });

  it("does not render unclassified upstream lookup details", async () => {
    vi.mocked(lookupGoogleWorkspaceUser).mockRejectedValue(
      new ApiError("private unclassified upstream detail", 502, "unexpected_upstream_failure")
    );
    const interaction = userEvent.setup();
    render(<GmailDelegationManagement {...defaultProps} />);
    await interaction.type(screen.getByLabelText("Primary email or user alias"), owner.primary_email);
    await interaction.click(screen.getByRole("button", { name: "Find mailbox" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("lookup could not be completed");
    expect(screen.queryByText("private unclassified upstream detail")).not.toBeInTheDocument();
  });

  it("discards a stale mailbox response when the tenant changes", async () => {
    const first = deferred<GoogleWorkspaceUser>();
    vi.mocked(lookupGoogleWorkspaceUser)
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ ...owner, id: "owner-2", primary_email: "second@secondary.example" });
    const interaction = userEvent.setup();
    const view = render(<GmailDelegationManagement {...defaultProps} />);
    await interaction.type(screen.getByLabelText("Primary email or user alias"), owner.primary_email);
    await interaction.click(screen.getByRole("button", { name: "Find mailbox" }));

    view.rerender(
      <GmailDelegationManagement
        {...defaultProps}
        organizationId="organization-2"
        connectorConfig={{ ...connector, organization_id: "organization-2" }}
      />
    );
    expect(screen.getByLabelText("Primary email or user alias")).toHaveValue("");
    await interaction.type(screen.getByLabelText("Primary email or user alias"), "second@secondary.example");
    await interaction.click(screen.getByRole("button", { name: "Find mailbox" }));
    expect(await screen.findByText("second@secondary.example")).toBeVisible();
    first.resolve(owner);
    await waitFor(() => expect(screen.queryByText(owner.primary_email)).not.toBeInTheDocument());
  });

  it("preserves lookup form state while theme and density attributes change", async () => {
    const interaction = userEvent.setup();
    render(<GmailDelegationManagement {...defaultProps} />);
    const input = screen.getByLabelText("Primary email or user alias");
    await interaction.type(input, "alex@primary.example");
    document.documentElement.dataset.theme = "graphite-copper";
    document.documentElement.dataset.density = "compact";
    expect(input).toHaveValue("alex@primary.example");
  });
});
