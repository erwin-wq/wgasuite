import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  executeGoogleWorkspaceUserStatusChange,
  previewGoogleWorkspaceUserStatusChange,
  reconcileGoogleWorkspaceUserStatusChange
} from "../../api/client";
import type {
  ConnectorConfig,
  GoogleWorkspaceUser,
  GoogleWorkspaceUserStatusPreview
} from "../../types";
import { UserStatusManagement } from "./UserStatusManagement";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    previewGoogleWorkspaceUserStatusChange: vi.fn(),
    executeGoogleWorkspaceUserStatusChange: vi.fn(),
    reconcileGoogleWorkspaceUserStatusChange: vi.fn()
  };
});

const connector: ConnectorConfig = {
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
  service_account_client_id: "123456789012345678901",
  notes: null,
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T10:00:00Z",
  last_tested_at: "2026-10-10T10:00:00Z",
  last_error_code: null,
  last_error: null
};

const activeUser: GoogleWorkspaceUser = {
  id: "google-user-1",
  full_name: "Example Person",
  primary_email: "person@example.test",
  aliases: ["person.alias@example.test"],
  non_editable_aliases: [],
  suspended: false,
  archived: false,
  org_unit_path: "/People",
  is_mailbox_setup: true,
  is_super_admin: false,
  is_delegated_admin: false,
  creation_time: null,
  last_login_time: null,
  suspension_reason: null,
  deletion_time: null,
  matched_by: "primary_email"
};

const suspendPreview: GoogleWorkspaceUserStatusPreview = {
  operation: "suspend",
  organization_id: "organization-1",
  customer_id: "customer-1",
  target_google_id: activeUser.id,
  target_primary_email: activeUser.primary_email,
  previous_suspended: false,
  requested_suspended: true,
  confirmation_token: "confirmation-token-suspend-1234567890",
  expires_at: "2026-10-14T21:05:00Z",
  effect: "The user will be suspended and lose access. Their data is not deleted."
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function renderStatus(overrides: Partial<React.ComponentProps<typeof UserStatusManagement>> = {}) {
  const onRefresh = vi.fn().mockResolvedValue(undefined);
  const result = render(
    <UserStatusManagement
      organizationId="organization-1"
      connectorConfig={connector}
      user={activeUser}
      canMutate
      onRefresh={onRefresh}
      {...overrides}
    />
  );
  return { ...result, onRefresh };
}

describe("UserStatusManagement", () => {
  beforeEach(() => vi.clearAllMocks());

  it("previews by canonical email and requires deliberate confirmation", async () => {
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockResolvedValue(suspendPreview);
    vi.mocked(executeGoogleWorkspaceUserStatusChange).mockResolvedValue({
      operation: "suspend",
      target_google_id: activeUser.id,
      target_primary_email: activeUser.primary_email,
      previous_suspended: false,
      suspended: true,
      outcome: "suspended",
      message: "person@example.test was suspended."
    });
    const user = userEvent.setup();
    const { onRefresh } = renderStatus();

    await user.click(screen.getByRole("button", { name: "Suspend user" }));
    expect(previewGoogleWorkspaceUserStatusChange).toHaveBeenCalledWith(
      "organization-1",
      "suspend",
      activeUser.primary_email,
      expect.any(AbortSignal)
    );
    const confirm = await screen.findByRole("button", { name: "Confirm suspension" });
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("dialog", { name: "Suspend this user?" })).toHaveTextContent(
      activeUser.id
    );

    await user.click(
      screen.getByRole("checkbox", {
        name: /I understand this changes the user's access/
      })
    );
    await user.click(confirm);

    expect(executeGoogleWorkspaceUserStatusChange).toHaveBeenCalledWith(
      "organization-1",
      "suspend",
      suspendPreview.confirmation_token
    );
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
  });

  it("offers reactivation only for an administrator-controlled suspension", () => {
    renderStatus({
      user: { ...activeUser, suspended: true, suspension_reason: "ADMIN" }
    });

    expect(screen.getByRole("button", { name: "Reactivate user" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Suspend user" })).not.toBeInTheDocument();
  });

  it("previews reactivation with the canonical suspended account", async () => {
    const suspended = { ...activeUser, suspended: true, suspension_reason: "ADMIN" };
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockResolvedValue({
      ...suspendPreview,
      operation: "reactivate",
      previous_suspended: true,
      requested_suspended: false,
      confirmation_token: "confirmation-token-reactivate-123456",
      effect: "Access may be restored."
    });
    const user = userEvent.setup();
    renderStatus({ user: suspended });

    await user.click(screen.getByRole("button", { name: "Reactivate user" }));

    expect(previewGoogleWorkspaceUserStatusChange).toHaveBeenCalledWith(
      "organization-1",
      "reactivate",
      activeUser.primary_email,
      expect.any(AbortSignal)
    );
    expect(await screen.findByRole("dialog", { name: "Reactivate this user?" })).toBeVisible();
  });

  it.each([
    [{ ...activeUser, is_super_admin: true }, /Super administrator accounts are protected/],
    [{ ...activeUser, is_delegated_admin: true }, /Delegated administrator accounts are protected/],
    [{ ...activeUser, archived: true }, /Archived accounts cannot be changed/],
    [
      { ...activeUser, suspended: true, suspension_reason: "GOOGLE" },
      /Only suspensions verified as administrator-controlled/
    ]
  ])("hides mutations for protected identities", (protectedUser, message) => {
    renderStatus({ user: protectedUser });

    expect(screen.getByText(message)).toBeVisible();
    expect(screen.queryByRole("button", { name: /user$/ })).not.toBeInTheDocument();
  });

  it("automatically reconciles an ambiguous response without resubmitting", async () => {
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockResolvedValue(suspendPreview);
    vi.mocked(executeGoogleWorkspaceUserStatusChange).mockRejectedValue(
      new ApiError("private timeout", 504, "google_timeout", {
        correlationId: "correlation-1",
        reconciliationAvailable: true
      })
    );
    vi.mocked(reconcileGoogleWorkspaceUserStatusChange).mockResolvedValue({
      operation: "suspend",
      target_google_id: activeUser.id,
      target_primary_email: activeUser.primary_email,
      status: "verified",
      observed_suspended: true,
      attempts: 1,
      correlation_id: "correlation-1",
      message: "Google now reports the requested account status."
    });
    const user = userEvent.setup();
    const { onRefresh } = renderStatus();

    await user.click(screen.getByRole("button", { name: "Suspend user" }));
    await user.click(await screen.findByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Confirm suspension" }));

    expect(await screen.findByText(/Google now reports/)).toBeVisible();
    expect(reconcileGoogleWorkspaceUserStatusChange).toHaveBeenCalledWith(
      "organization-1",
      "suspend",
      suspendPreview.confirmation_token,
      expect.any(AbortSignal)
    );
    expect(executeGoogleWorkspaceUserStatusChange).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("private timeout")).not.toBeInTheDocument();
  });

  it("shows a safe missing-scope error", async () => {
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockRejectedValue(
      new ApiError("private upstream response", 403, "missing_scope_or_permission")
    );
    const user = userEvent.setup();
    renderStatus();

    await user.click(screen.getByRole("button", { name: "Suspend user" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Directory user write scope/);
    expect(screen.queryByText("private upstream response")).not.toBeInTheDocument();
  });

  it("prevents double submission while the confirmed mutation is pending", async () => {
    const pending = deferred<never>();
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockResolvedValue(suspendPreview);
    vi.mocked(executeGoogleWorkspaceUserStatusChange).mockReturnValue(pending.promise);
    const user = userEvent.setup();
    renderStatus();

    await user.click(screen.getByRole("button", { name: "Suspend user" }));
    await user.click(await screen.findByRole("checkbox"));
    const confirm = screen.getByRole("button", { name: "Confirm suspension" });
    await user.click(confirm);
    expect(confirm).toBeDisabled();
    await user.click(confirm);

    expect(executeGoogleWorkspaceUserStatusChange).toHaveBeenCalledTimes(1);
  });

  it("discards a stale preview after an organization switch", async () => {
    const pending = deferred<GoogleWorkspaceUserStatusPreview>();
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockReturnValue(pending.promise);
    const user = userEvent.setup();
    const { rerender } = renderStatus();

    await user.click(screen.getByRole("button", { name: "Suspend user" }));
    rerender(
      <UserStatusManagement
        organizationId="organization-2"
        connectorConfig={{ ...connector, organization_id: "organization-2" }}
        user={{ ...activeUser, id: "google-user-2", primary_email: "second@example.test" }}
        canMutate
        onRefresh={vi.fn().mockResolvedValue(undefined)}
      />
    );
    pending.resolve(suspendPreview);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Suspend user" })).toBeEnabled();
  });

  it("does not display mutation controls to read-only users", () => {
    renderStatus({ canMutate: false });

    expect(screen.getByText(/Customer administrator access is required/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Suspend user" })).not.toBeInTheDocument();
  });

  it("keeps unknown outcomes visible for manual read-only checks", async () => {
    vi.mocked(previewGoogleWorkspaceUserStatusChange).mockResolvedValue(suspendPreview);
    vi.mocked(executeGoogleWorkspaceUserStatusChange).mockRejectedValue(
      new ApiError("private timeout", 504, "google_timeout", {
        correlationId: "correlation-2",
        reconciliationAvailable: true
      })
    );
    vi.mocked(reconcileGoogleWorkspaceUserStatusChange).mockResolvedValue({
      operation: "suspend",
      target_google_id: activeUser.id,
      target_primary_email: activeUser.primary_email,
      status: "unknown",
      observed_suspended: false,
      attempts: 4,
      correlation_id: "correlation-2",
      message: "The result is still unknown. Check the account status again before retrying."
    });
    const user = userEvent.setup();
    renderStatus();

    await user.click(screen.getByRole("button", { name: "Suspend user" }));
    await user.click(await screen.findByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Confirm suspension" }));

    expect(await screen.findByRole("button", { name: "Check status" })).toBeVisible();
    expect(executeGoogleWorkspaceUserStatusChange).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() =>
      expect(reconcileGoogleWorkspaceUserStatusChange).toHaveBeenCalledTimes(2)
    );
    expect(executeGoogleWorkspaceUserStatusChange).toHaveBeenCalledTimes(1);
  });
});
