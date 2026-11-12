import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  executeGoogleWorkspaceOrganizationalUnitCreation,
  previewGoogleWorkspaceOrganizationalUnitCreation,
  reconcileGoogleWorkspaceOrganizationalUnitCreation
} from "../../api/client";
import type { GoogleWorkspaceOrganizationalUnitTreeNode } from "../../types";
import {
  DIRECTORY_ORGUNIT_WRITE_SCOPE,
  OrganizationalUnitCreation
} from "./OrganizationalUnitCreation";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    executeGoogleWorkspaceOrganizationalUnitCreation: vi.fn(),
    previewGoogleWorkspaceOrganizationalUnitCreation: vi.fn(),
    reconcileGoogleWorkspaceOrganizationalUnitCreation: vi.fn()
  };
});

const parent: GoogleWorkspaceOrganizationalUnitTreeNode = {
  id: "id:engineering",
  name: "Engineering",
  description: null,
  path: "/Engineering",
  parent_id: "id:root",
  parent_path: "/",
  read_only: true,
  user_move_protected: false,
  children: []
};

describe("OrganizationalUnitCreation", () => {
  const onCreated = vi.fn(async () => undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(previewGoogleWorkspaceOrganizationalUnitCreation).mockResolvedValue({
      parent_org_unit_id: parent.id,
      parent_path: parent.path,
      name: "Platform",
      description: "Product infrastructure",
      expected_path: "/Engineering/Platform",
      confirmation_token: "confirmation-token-that-is-never-persisted-in-ui-tests",
      expires_at: "2026-11-08T12:05:00Z",
      effect: "One child Organizational Unit will be created."
    });
    vi.mocked(executeGoogleWorkspaceOrganizationalUnitCreation).mockResolvedValue({
      organizational_unit: {
        ...parent,
        id: "id:platform",
        name: "Platform",
        path: "/Engineering/Platform",
        parent_id: parent.id,
        parent_path: parent.path,
        description: "Product infrastructure"
      },
      outcome: "created",
      message: "/Engineering/Platform was created."
    });
  });

  it("previews the full path and requires a second explicit confirmation", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationalUnitCreation
        organizationId="organization-1"
        parent={parent}
        onCreated={onCreated}
      />
    );

    await user.click(screen.getByRole("button", { name: "Create child OU" }));
    await user.type(screen.getByLabelText("Name"), "Platform");
    await user.type(screen.getByLabelText(/Description/), "Product infrastructure");
    expect(screen.getByText("/Engineering/Platform")).toBeVisible();
    expect(executeGoogleWorkspaceOrganizationalUnitCreation).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Review creation" }));
    expect(await screen.findByText("One child Organizational Unit will be created.")).toBeVisible();
    expect(previewGoogleWorkspaceOrganizationalUnitCreation).toHaveBeenCalledWith(
      "organization-1",
      parent.id,
      "Platform",
      "Product infrastructure",
      expect.any(AbortSignal)
    );

    await user.click(screen.getByRole("button", { name: "Confirm and create once" }));
    expect(await screen.findByText("/Engineering/Platform was created.")).toBeVisible();
    expect(executeGoogleWorkspaceOrganizationalUnitCreation).toHaveBeenCalledTimes(1);
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("shows exact manual DWD scope instructions without submitting a write", async () => {
    vi.mocked(previewGoogleWorkspaceOrganizationalUnitCreation).mockRejectedValue(
      new ApiError("unsafe upstream detail", 403, "missing_scope_or_permission")
    );
    const user = userEvent.setup();
    render(
      <OrganizationalUnitCreation
        organizationId="organization-1"
        parent={parent}
        onCreated={onCreated}
      />
    );
    await user.click(screen.getByRole("button", { name: "Create child OU" }));
    await user.type(screen.getByLabelText("Name"), "Platform");
    await user.click(screen.getByRole("button", { name: "Review creation" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(DIRECTORY_ORGUNIT_WRITE_SCOPE);
    expect(alert).toHaveTextContent("Domain-Wide Delegation");
    expect(alert).not.toHaveTextContent("unsafe upstream detail");
    expect(executeGoogleWorkspaceOrganizationalUnitCreation).not.toHaveBeenCalled();
  });

  it("uses read-only reconciliation after an ambiguous write and never repeats it", async () => {
    vi.mocked(executeGoogleWorkspaceOrganizationalUnitCreation).mockRejectedValue(
      new ApiError("Timed out", 504, "google_timeout", {
        correlationId: "correlation-1",
        reconciliationAvailable: true
      })
    );
    vi.mocked(reconcileGoogleWorkspaceOrganizationalUnitCreation).mockResolvedValue({
      status: "verified",
      organizational_unit: {
        ...parent,
        id: "id:platform",
        name: "Platform",
        path: "/Engineering/Platform"
      },
      expected_path: "/Engineering/Platform",
      attempts: 1,
      correlation_id: "correlation-1",
      message: "Google now reports the created Organizational Unit."
    });
    const user = userEvent.setup();
    render(
      <OrganizationalUnitCreation
        organizationId="organization-1"
        parent={parent}
        onCreated={onCreated}
      />
    );
    await user.click(screen.getByRole("button", { name: "Create child OU" }));
    await user.type(screen.getByLabelText("Name"), "Platform");
    await user.click(screen.getByRole("button", { name: "Review creation" }));
    await user.click(await screen.findByRole("button", { name: "Confirm and create once" }));

    expect(await screen.findByText("Google now reports the created Organizational Unit.")).toBeVisible();
    expect(executeGoogleWorkspaceOrganizationalUnitCreation).toHaveBeenCalledTimes(1);
    expect(reconcileGoogleWorkspaceOrganizationalUnitCreation).toHaveBeenCalledTimes(1);
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("traps keyboard focus, closes with Escape and restores trigger focus", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationalUnitCreation
        organizationId="organization-1"
        parent={parent}
        onCreated={onCreated}
      />
    );
    const trigger = screen.getByRole("button", { name: "Create child OU" });
    await user.click(trigger);
    const close = screen.getByRole("button", { name: "Close creation dialog" });
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(screen.getByLabelText("Name")).toHaveFocus();

    close.focus();
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await vi.waitFor(() => expect(trigger).toHaveFocus());
  });
});
