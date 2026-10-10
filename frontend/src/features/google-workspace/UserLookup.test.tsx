import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, lookupGoogleWorkspaceUser } from "../../api/client";
import type { ConnectorConfig, GoogleWorkspaceUser } from "../../types";
import { UserLookup } from "./UserLookup";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, lookupGoogleWorkspaceUser: vi.fn() };
});

const connectedConfig: ConnectorConfig = {
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
  service_account_email: "scanner@project.iam.gserviceaccount.com",
  service_account_client_id: "123456789012345678901",
  notes: null,
  created_at: "2026-10-10T08:00:00Z",
  updated_at: "2026-10-10T08:00:00Z",
  last_tested_at: "2026-10-10T08:01:00Z",
  last_error_code: null,
  last_error: null
};

const aliasResult: GoogleWorkspaceUser = {
  id: "google-user-123",
  full_name: "Example Person",
  primary_email: "person@primary.example",
  aliases: ["person.alias@primary.example", "person@secondary.example"],
  non_editable_aliases: ["person@legacy.example"],
  suspended: false,
  archived: false,
  org_unit_path: "/Engineering",
  is_mailbox_setup: true,
  matched_by: "alias"
};

function renderLookup(overrides = {}) {
  const props = {
    organizationId: "organization-1",
    organizationName: "Primary Workspace",
    connectorConfig: connectedConfig,
    canSearch: true,
    ...overrides
  };
  return { ...render(<UserLookup {...props} />), props };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("UserLookup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not search automatically and identifies missing organization context", () => {
    renderLookup({ organizationId: "", organizationName: null, connectorConfig: null });

    expect(screen.getByText("Select an organization before searching.")).toBeVisible();
    expect(lookupGoogleWorkspaceUser).not.toHaveBeenCalled();
  });

  it("distinguishes permission and connector readiness states", () => {
    const { rerender } = renderLookup({ canSearch: false });
    expect(screen.getByText(/Administrator access is required/)).toBeVisible();

    rerender(
      <UserLookup
        organizationId="organization-1"
        organizationName="Primary Workspace"
        connectorConfig={{ ...connectedConfig, status: "configured" }}
        canSearch
      />
    );
    expect(screen.getByText(/successfully test Google Workspace/)).toBeVisible();
  });

  it("validates the email address without making a request", async () => {
    const user = userEvent.setup();
    renderLookup();

    await user.type(screen.getByLabelText("Primary email or user alias"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Search user" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid full email address.");
    expect(lookupGoogleWorkspaceUser).not.toHaveBeenCalled();
  });

  it("submits with Enter, shows loading, and renders an alias match", async () => {
    const pending = deferred<GoogleWorkspaceUser>();
    vi.mocked(lookupGoogleWorkspaceUser).mockReturnValue(pending.promise);
    const user = userEvent.setup();
    renderLookup();

    const input = screen.getByLabelText("Primary email or user alias");
    await user.type(input, "Person.Alias@Primary.Example{enter}");

    expect(screen.getByRole("button", { name: "Searching" })).toBeDisabled();
    expect(lookupGoogleWorkspaceUser).toHaveBeenCalledWith(
      "organization-1",
      "person.alias@primary.example",
      expect.any(AbortSignal)
    );
    pending.resolve(aliasResult);

    expect(await screen.findByRole("heading", { name: "Example Person" })).toBeVisible();
    expect(screen.getByText("person@primary.example")).toBeVisible();
    expect(screen.getByText("Matched editable alias")).toBeVisible();
    expect(screen.getByText("person@secondary.example")).toBeVisible();
    expect(screen.getByText("person@legacy.example")).toBeVisible();
    expect(screen.getByText("Active")).toBeVisible();
    expect(screen.getByText("/Engineering")).toBeVisible();
    expect(screen.getByText("Gmail mailbox set up")).toBeVisible();
  });

  it("renders suspended, archived, empty alias, and unknown mailbox states", async () => {
    vi.mocked(lookupGoogleWorkspaceUser).mockResolvedValue({
      ...aliasResult,
      aliases: [],
      non_editable_aliases: [],
      suspended: true,
      archived: true,
      org_unit_path: null,
      is_mailbox_setup: null,
      matched_by: "primary_email"
    });
    const user = userEvent.setup();
    renderLookup();

    await user.type(screen.getByLabelText("Primary email or user alias"), "person@primary.example");
    await user.click(screen.getByRole("button", { name: "Search user" }));

    expect(await screen.findByText("Suspended")).toBeVisible();
    expect(screen.getByText("Matched primary email")).toBeVisible();
    expect(screen.getByText("No editable aliases")).toBeVisible();
    expect(screen.getByText("No non-editable aliases")).toBeVisible();
    expect(screen.getByText("Mailbox setup unknown")).toBeVisible();
  });

  it.each([
    [new ApiError("safe not found", 404, "google_user_not_found"), /No Directory user/],
    [new ApiError("safe permission", 403, "missing_scope_or_permission"), /Google denied/],
    [new ApiError("safe rate", 429, "google_rate_limited"), /rate-limited/],
    [new ApiError("safe outage", 503, "google_service_unavailable"), /temporarily unavailable/],
    [new ApiError("safe config", 409, "connector_not_configured"), /connector is not ready/],
    [new Error("network detail"), /Check your connection/]
  ])("shows a useful sanitized failure for %s", async (failure, expectedMessage) => {
    vi.mocked(lookupGoogleWorkspaceUser).mockRejectedValue(failure);
    const user = userEvent.setup();
    renderLookup();

    await user.type(screen.getByLabelText("Primary email or user alias"), "person@example.net");
    await user.click(screen.getByRole("button", { name: "Search user" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(expectedMessage);
    expect(screen.queryByLabelText("Google Workspace user result")).not.toBeInTheDocument();
  });

  it("clears the query, result, and error state", async () => {
    vi.mocked(lookupGoogleWorkspaceUser).mockResolvedValue(aliasResult);
    const user = userEvent.setup();
    renderLookup();

    const input = screen.getByLabelText("Primary email or user alias");
    await user.type(input, "person.alias@primary.example");
    await user.click(screen.getByRole("button", { name: "Search user" }));
    expect(await screen.findByText("Matched editable alias")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(input).toHaveValue("");
    expect(screen.queryByText("Matched editable alias")).not.toBeInTheDocument();
  });

  it("discards stale results after an organization switch or newer search", async () => {
    const first = deferred<GoogleWorkspaceUser>();
    const second = deferred<GoogleWorkspaceUser>();
    vi.mocked(lookupGoogleWorkspaceUser)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const user = userEvent.setup();
    const { rerender } = renderLookup();

    await user.type(
      screen.getByLabelText("Primary email or user alias"),
      "person.alias@primary.example"
    );
    await user.click(screen.getByRole("button", { name: "Search user" }));

    rerender(
      <UserLookup
        organizationId="organization-2"
        organizationName="Secondary Workspace"
        connectorConfig={{ ...connectedConfig, organization_id: "organization-2" }}
        canSearch
      />
    );
    const newInput = screen.getByLabelText("Primary email or user alias");
    expect(newInput).toHaveValue("");
    await user.type(newInput, "second@secondary.example");
    await user.click(screen.getByRole("button", { name: "Search user" }));

    second.resolve({
      ...aliasResult,
      full_name: "Second Tenant User",
      primary_email: "second@secondary.example",
      matched_by: "primary_email"
    });
    expect(await screen.findByRole("heading", { name: "Second Tenant User" })).toBeVisible();

    first.resolve(aliasResult);
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Example Person" })).not.toBeInTheDocument()
    );
    expect(screen.getByRole("heading", { name: "Second Tenant User" })).toBeVisible();
  });

  it("discards an older request after clear and a newer search", async () => {
    const first = deferred<GoogleWorkspaceUser>();
    const second = deferred<GoogleWorkspaceUser>();
    vi.mocked(lookupGoogleWorkspaceUser)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const user = userEvent.setup();
    renderLookup();

    let input = screen.getByLabelText("Primary email or user alias");
    await user.type(input, "first@primary.example");
    await user.click(screen.getByRole("button", { name: "Search user" }));
    await user.click(screen.getByRole("button", { name: "Clear" }));
    input = screen.getByLabelText("Primary email or user alias");
    await user.type(input, "second@primary.example");
    await user.click(screen.getByRole("button", { name: "Search user" }));

    second.resolve({
      ...aliasResult,
      full_name: "Newest Search Result",
      primary_email: "second@primary.example",
      matched_by: "primary_email"
    });
    expect(await screen.findByRole("heading", { name: "Newest Search Result" })).toBeVisible();

    first.resolve({ ...aliasResult, full_name: "Stale Search Result" });
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Stale Search Result" })).not.toBeInTheDocument()
    );
    expect(screen.getByRole("heading", { name: "Newest Search Result" })).toBeVisible();
  });
});
