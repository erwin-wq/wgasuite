import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  importGoogleWorkspaceCredential,
  selectExternalGoogleWorkspaceCredential
} from "../../api/client";
import type { ConnectorConfig } from "../../types";
import { ConnectionWizard, DIRECTORY_USER_READONLY_SCOPE } from "./ConnectionWizard";

vi.mock("../../api/client", () => ({
  importGoogleWorkspaceCredential: vi.fn(),
  selectExternalGoogleWorkspaceCredential: vi.fn()
}));

const baseConfig: ConnectorConfig = {
  id: "connector-1",
  organization_id: "organization-1",
  connector_type: "google_workspace",
  auth_method: "service_account_domain_wide_delegation",
  status: "configured",
  display_name: "Google Workspace",
  primary_domain: "example.com",
  admin_subject_email: null,
  credential_provider: "managed_file",
  credentials_configured: true,
  service_account_email: "scanner@project.iam.gserviceaccount.com",
  service_account_client_id: "123456789012345678901",
  notes: null,
  created_at: "2026-10-09T10:00:00Z",
  updated_at: "2026-10-09T10:00:00Z",
  last_tested_at: null,
  last_error_code: null,
  last_error: null
};

function renderWizard(config: ConnectorConfig | null = baseConfig, overrides = {}) {
  const props = {
    connectorConfig: config,
    organizationSelected: true,
    canManageCredentials: true,
    displayName: "Google Workspace",
    primaryDomain: "example.com",
    adminSubjectEmail: config?.admin_subject_email ?? "",
    notes: "",
    isSaving: false,
    isTesting: false,
    feedback: null,
    onDisplayNameChange: vi.fn(),
    onPrimaryDomainChange: vi.fn(),
    onAdminSubjectEmailChange: vi.fn(),
    onNotesChange: vi.fn(),
    onSave: vi.fn().mockResolvedValue(config ?? baseConfig),
    onTest: vi.fn().mockResolvedValue(undefined),
    onReload: vi.fn().mockResolvedValue(undefined),
    onCredentialFeedback: vi.fn(),
    ...overrides
  };
  return { ...render(<ConnectionWizard {...props} />), props };
}

describe("ConnectionWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) }
    });
  });

  it("shows the exact delegation values and copies them", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    renderWizard();

    expect(screen.getByRole("heading", { name: "Authorize domain-wide delegation" })).toBeVisible();
    expect(screen.getByText(DIRECTORY_USER_READONLY_SCOPE)).toBeVisible();
    expect(screen.getByText(baseConfig.service_account_client_id!)).toBeVisible();
    await user.click(screen.getAllByRole("button", { name: "Copy" })[1]);

    expect(writeText).toHaveBeenCalledWith(DIRECTORY_USER_READONLY_SCOPE);
  });

  it("uploads a selected JSON file and advances after success", async () => {
    vi.mocked(importGoogleWorkspaceCredential).mockResolvedValue({
      credential_provider: "managed_file",
      credentials_configured: true,
      service_account_email: "scanner@project.iam.gserviceaccount.com",
      service_account_client_id: "123456789012345678901"
    });
    const user = userEvent.setup();
    const { props } = renderWizard(null);
    await user.click(screen.getByRole("button", { name: "Continue to credentials" }));
    const file = new File(["{}"], "service-account.json", { type: "application/json" });
    await user.upload(screen.getByLabelText("Service-account JSON file"), file);
    await user.click(screen.getByRole("button", { name: "Validate and store" }));

    await waitFor(() => expect(importGoogleWorkspaceCredential).toHaveBeenCalledWith("connector-1", file));
    expect(props.onReload).toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Authorize domain-wide delegation" })).toBeVisible();
  });

  it("reports credential upload failures without advancing", async () => {
    vi.mocked(importGoogleWorkspaceCredential).mockRejectedValue(new Error("Invalid private key."));
    const user = userEvent.setup();
    const { props } = renderWizard(null);
    await user.click(screen.getByRole("button", { name: "Continue to credentials" }));
    fireEvent.change(screen.getByLabelText("Service-account JSON file"), {
      target: { files: [new File(["{}"], "bad.json", { type: "application/json" })] }
    });
    await user.click(screen.getByRole("button", { name: "Validate and store" }));

    await waitFor(() =>
      expect(props.onCredentialFeedback).toHaveBeenCalledWith({
        type: "error",
        message: "Invalid private key."
      })
    );
    expect(screen.getByRole("heading", { name: "Provide the service-account credential" })).toBeVisible();
  });

  it("requires a valid admin subject before saving", async () => {
    const user = userEvent.setup();
    const { props } = renderWizard();
    await user.click(screen.getByRole("button", { name: "Delegation is authorized" }));
    const adminInput = screen.getByLabelText("Admin subject email") as HTMLInputElement;

    expect(adminInput.required).toBe(true);
    expect(adminInput.type).toBe("email");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("restores verified state without automatically testing and tests only on click", async () => {
    const user = userEvent.setup();
    const onTest = vi.fn().mockResolvedValue(undefined);
    renderWizard(
      {
        ...baseConfig,
        status: "connected",
        admin_subject_email: "admin@another-workspace.example",
        last_tested_at: "2026-10-09T11:00:00Z"
      },
      { adminSubjectEmail: "admin@another-workspace.example", onTest }
    );

    expect(screen.getByText("connected")).toBeVisible();
    expect(onTest).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    expect(onTest).toHaveBeenCalledOnce();
  });

  it("restores the persisted step when configuration arrives asynchronously", async () => {
    const { rerender, props } = renderWizard(null);
    expect(screen.getByRole("heading", { name: "Prepare a Google Cloud project" })).toBeVisible();

    rerender(
      <ConnectionWizard
        {...props}
        connectorConfig={{
          ...baseConfig,
          admin_subject_email: "admin@secondary.example"
        }}
        adminSubjectEmail="admin@secondary.example"
      />
    );

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Test the real Google Workspace connection" })
      ).toBeVisible()
    );
  });

  it("supports selecting the operator-provisioned file mode", async () => {
    vi.mocked(selectExternalGoogleWorkspaceCredential).mockResolvedValue({
      credential_provider: "file",
      credentials_configured: true,
      service_account_email: "scanner@project.iam.gserviceaccount.com",
      service_account_client_id: "123456789012345678901"
    });
    const user = userEvent.setup();
    renderWizard(null);
    await user.click(screen.getByRole("button", { name: "Continue to credentials" }));
    await user.click(screen.getByText("Existing server file"));
    await user.type(screen.getByLabelText("Provisioned credential reference"), "production-key");
    await user.click(screen.getByRole("button", { name: "Validate and use reference" }));

    await waitFor(() =>
      expect(selectExternalGoogleWorkspaceCredential).toHaveBeenCalledWith(
        "connector-1",
        "production-key"
      )
    );
  });
});
