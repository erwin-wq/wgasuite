import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ConnectorConfig } from "../../types";
import { DIRECTORY_USER_READONLY_SCOPE } from "./ConnectionWizard";
import {
  GMAIL_DELEGATE_READ_SCOPE,
  GMAIL_DELEGATE_WRITE_SCOPE,
  GmailDelegationAuthorization
} from "./GmailDelegationAuthorization";

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
  service_account_client_id: "123456789012345678901",
  notes: null,
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T10:00:00Z",
  last_tested_at: "2026-10-10T10:00:00Z",
  last_error_code: null,
  last_error: null
};

describe("GmailDelegationAuthorization", () => {
  it("separates Directory, Gmail read, and Gmail write capabilities", () => {
    render(<GmailDelegationAuthorization connectorConfig={connectedConfig} />);

    expect(screen.getByText("Directory user lookup")).toBeVisible();
    expect(screen.getByText("Gmail delegates readable")).toBeVisible();
    expect(screen.getByText("Gmail delegate writes")).toBeVisible();
    expect(screen.getByText("Verified")).toBeVisible();
    expect(screen.getByText("Verify by loading a mailbox")).toBeVisible();
    expect(screen.getByText("Not tested automatically")).toBeVisible();
    expect(screen.getByText(DIRECTORY_USER_READONLY_SCOPE)).toBeVisible();
    expect(screen.getByText(GMAIL_DELEGATE_READ_SCOPE)).toBeVisible();
    expect(screen.getByText(GMAIL_DELEGATE_WRITE_SCOPE)).toBeVisible();
  });

  it("copies all required scopes while preserving the Directory scope", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<GmailDelegationAuthorization connectorConfig={connectedConfig} />);

    await user.click(screen.getByRole("button", { name: "Copy all" }));

    expect(writeText).toHaveBeenCalledWith(
      [DIRECTORY_USER_READONLY_SCOPE, GMAIL_DELEGATE_READ_SCOPE, GMAIL_DELEGATE_WRITE_SCOPE].join(
        ","
      )
    );
    expect(screen.getByRole("button", { name: "Copied" })).toBeVisible();
  });
});
