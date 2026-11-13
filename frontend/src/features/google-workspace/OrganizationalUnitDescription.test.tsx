import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  executeGoogleWorkspaceOrganizationalUnitDescription,
  previewGoogleWorkspaceOrganizationalUnitDescription,
  reconcileGoogleWorkspaceOrganizationalUnitDescription
} from "../../api/client";
import type { GoogleWorkspaceOrganizationalUnitTreeNode } from "../../types";
import { DIRECTORY_ORGUNIT_WRITE_SCOPE } from "./OrganizationalUnitCreation";
import { OrganizationalUnitDescription } from "./OrganizationalUnitDescription";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    executeGoogleWorkspaceOrganizationalUnitDescription: vi.fn(),
    previewGoogleWorkspaceOrganizationalUnitDescription: vi.fn(),
    reconcileGoogleWorkspaceOrganizationalUnitDescription: vi.fn()
  };
});

const unit: GoogleWorkspaceOrganizationalUnitTreeNode = {
  id: "id:qa",
  name: "WGASuite QA",
  description: "Original description",
  path: "/WGASuite-QA",
  parent_id: "id:root",
  parent_path: "/",
  read_only: true,
  user_move_protected: false,
  children: []
};

describe("OrganizationalUnitDescription", () => {
  const onUpdated = vi.fn(async () => undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(previewGoogleWorkspaceOrganizationalUnitDescription).mockResolvedValue({
      org_unit_id: unit.id,
      name: unit.name,
      path: unit.path,
      original_description: unit.description,
      proposed_description: "Updated description",
      confirmation_token: "confirmation-token-that-remains-in-memory-only",
      expires_at: "2026-11-13T12:05:00Z",
      effect: "Only this Organizational Unit's description will change."
    });
    vi.mocked(executeGoogleWorkspaceOrganizationalUnitDescription).mockResolvedValue({
      organizational_unit: { ...unit, description: "Updated description" },
      previous_description: unit.description,
      outcome: "updated",
      message: "The description for /WGASuite-QA was updated."
    });
  });

  it("shows old and proposed values and requires one explicit confirmation", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationalUnitDescription
        organizationId="organization-1"
        unit={unit}
        onUpdated={onUpdated}
      />
    );
    await user.click(screen.getByRole("button", { name: "Edit description" }));
    const input = screen.getByLabelText(/New description/);
    expect(input).toHaveFocus();
    await user.clear(input);
    await user.type(input, "Updated description");
    expect(executeGoogleWorkspaceOrganizationalUnitDescription).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Review change" }));
    expect(await screen.findByText("Original description")).toBeVisible();
    expect(screen.getByText("Updated description")).toBeVisible();
    expect(previewGoogleWorkspaceOrganizationalUnitDescription).toHaveBeenCalledWith(
      "organization-1",
      unit.id,
      "Updated description",
      expect.any(AbortSignal)
    );
    await user.click(screen.getByRole("button", { name: "Confirm description update once" }));
    expect(await screen.findByText("The description for /WGASuite-QA was updated.")).toBeVisible();
    expect(executeGoogleWorkspaceOrganizationalUnitDescription).toHaveBeenCalledTimes(1);
    expect(onUpdated).toHaveBeenCalledTimes(1);
  });

  it("supports clearing a description and blocks an unchanged value", async () => {
    vi.mocked(previewGoogleWorkspaceOrganizationalUnitDescription).mockResolvedValue({
      org_unit_id: unit.id,
      name: unit.name,
      path: unit.path,
      original_description: unit.description,
      proposed_description: null,
      confirmation_token: "confirmation-token-that-remains-in-memory-only",
      expires_at: "2026-11-13T12:05:00Z",
      effect: "Only this Organizational Unit's description will change."
    });
    const user = userEvent.setup();
    render(
      <OrganizationalUnitDescription
        organizationId="organization-1"
        unit={unit}
        onUpdated={onUpdated}
      />
    );
    await user.click(screen.getByRole("button", { name: "Edit description" }));
    expect(screen.getByRole("button", { name: "Review change" })).toBeDisabled();
    await user.clear(screen.getByLabelText(/New description/));
    expect(screen.getByRole("button", { name: "Review change" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Review change" }));
    expect(previewGoogleWorkspaceOrganizationalUnitDescription).toHaveBeenCalledWith(
      "organization-1",
      unit.id,
      "",
      expect.any(AbortSignal)
    );
    expect((await screen.findAllByText("No description")).length).toBeGreaterThan(0);
  });

  it("shows safe DWD guidance and never submits a write after preview rejection", async () => {
    vi.mocked(previewGoogleWorkspaceOrganizationalUnitDescription).mockRejectedValue(
      new ApiError("private upstream detail", 403, "missing_scope_or_permission")
    );
    const user = userEvent.setup();
    render(
      <OrganizationalUnitDescription
        organizationId="organization-1"
        unit={unit}
        onUpdated={onUpdated}
      />
    );
    await user.click(screen.getByRole("button", { name: "Edit description" }));
    const input = screen.getByLabelText(/New description/);
    await user.clear(input);
    await user.type(input, "Updated description");
    await user.click(screen.getByRole("button", { name: "Review change" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(DIRECTORY_ORGUNIT_WRITE_SCOPE);
    expect(alert).not.toHaveTextContent("private upstream detail");
    expect(executeGoogleWorkspaceOrganizationalUnitDescription).not.toHaveBeenCalled();
  });

  it("reconciles an ambiguous result without repeating the write", async () => {
    vi.mocked(executeGoogleWorkspaceOrganizationalUnitDescription).mockRejectedValue(
      new ApiError("Timed out", 504, "google_timeout", {
        correlationId: "correlation-1",
        reconciliationAvailable: true
      })
    );
    vi.mocked(reconcileGoogleWorkspaceOrganizationalUnitDescription).mockResolvedValue({
      status: "verified",
      organizational_unit: { ...unit, description: "Updated description" },
      attempts: 1,
      correlation_id: "correlation-1",
      message: "The description for /WGASuite-QA is verified."
    });
    const user = userEvent.setup();
    render(
      <OrganizationalUnitDescription
        organizationId="organization-1"
        unit={unit}
        onUpdated={onUpdated}
      />
    );
    await user.click(screen.getByRole("button", { name: "Edit description" }));
    const input = screen.getByLabelText(/New description/);
    await user.clear(input);
    await user.type(input, "Updated description");
    await user.click(screen.getByRole("button", { name: "Review change" }));
    await user.click(await screen.findByRole("button", { name: "Confirm description update once" }));
    expect(await screen.findByText("The description for /WGASuite-QA is verified.")).toBeVisible();
    expect(executeGoogleWorkspaceOrganizationalUnitDescription).toHaveBeenCalledTimes(1);
    expect(reconcileGoogleWorkspaceOrganizationalUnitDescription).toHaveBeenCalledTimes(1);
  });

  it("traps focus, closes with Escape and restores focus", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationalUnitDescription
        organizationId="organization-1"
        unit={unit}
        onUpdated={onUpdated}
      />
    );
    const trigger = screen.getByRole("button", { name: "Edit description" });
    await user.click(trigger);
    const close = screen.getByRole("button", { name: "Close description dialog" });
    const cancel = screen.getByRole("button", { name: "Cancel" });
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
