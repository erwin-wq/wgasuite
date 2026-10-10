import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  executeGmailDelegateChange,
  listGmailDelegates,
  previewGmailDelegateChange
} from "../../api/client";
import type {
  GmailDelegateChangePreview,
  GmailDelegateList,
  GoogleWorkspaceUser
} from "../../types";
import { MailboxDelegates } from "./MailboxDelegates";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listGmailDelegates: vi.fn(),
    previewGmailDelegateChange: vi.fn(),
    executeGmailDelegateChange: vi.fn()
  };
});

const owner: GoogleWorkspaceUser = {
  id: "owner-id",
  full_name: "Mailbox Owner",
  primary_email: "owner@primary.example",
  aliases: ["owner.alias@primary.example"],
  non_editable_aliases: [],
  suspended: false,
  archived: false,
  org_unit_path: "/People",
  is_mailbox_setup: true,
  matched_by: "primary_email"
};

const populatedList: GmailDelegateList = {
  owner_primary_email: owner.primary_email,
  delegates: [
    { primary_email: "delegate@primary.example", verification_status: "accepted" }
  ]
};

const createPreview: GmailDelegateChangePreview = {
  operation: "create",
  owner_primary_email: owner.primary_email,
  delegate_primary_email: "canonical@primary.example",
  confirmation_token: "confirmation-token-create-1234567890",
  expires_at: "2026-10-10T20:05:00Z",
  effect:
    "The delegate will be able to read, send, and delete messages in the mailbox. Google may take approximately one minute to make access usable."
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function renderDelegates(overrides = {}) {
  return render(
    <MailboxDelegates
      organizationId="organization-1"
      owner={owner}
      canMutate
      {...overrides}
    />
  );
}

describe("MailboxDelegates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listGmailDelegates).mockResolvedValue(populatedList);
  });

  it("loads and refreshes delegates for the canonical mailbox owner", async () => {
    const user = userEvent.setup();
    renderDelegates();

    expect(await screen.findByText("delegate@primary.example")).toBeVisible();
    expect(screen.getByText("1 delegate")).toBeVisible();
    expect(screen.getByText("Accepted")).toBeVisible();
    expect(listGmailDelegates).toHaveBeenCalledWith(
      "organization-1",
      "owner@primary.example",
      expect.any(AbortSignal)
    );

    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listGmailDelegates).toHaveBeenCalledTimes(2));
  });

  it("renders an empty delegate collection as a valid state", async () => {
    vi.mocked(listGmailDelegates).mockResolvedValue({
      owner_primary_email: owner.primary_email,
      delegates: []
    });
    renderDelegates();

    expect(await screen.findByText("No delegates")).toBeVisible();
    expect(screen.getByText("This mailbox has no delegated users.")).toBeVisible();
  });

  it("validates an alias, previews the canonical identity, confirms, and refreshes", async () => {
    vi.mocked(previewGmailDelegateChange).mockResolvedValue(createPreview);
    vi.mocked(executeGmailDelegateChange).mockResolvedValue({
      operation: "create",
      owner_primary_email: owner.primary_email,
      delegate_primary_email: "canonical@primary.example",
      outcome: "created",
      message: "Mailbox delegate added. Google may take approximately one minute."
    });
    const user = userEvent.setup();
    renderDelegates();
    await screen.findByText("delegate@primary.example");

    await user.type(
      screen.getByLabelText("Add delegate by primary email or alias"),
      "Alias@Primary.Example"
    );
    await user.click(screen.getByRole("button", { name: "Review delegate" }));

    expect(previewGmailDelegateChange).toHaveBeenCalledWith(
      "organization-1",
      "create",
      owner.primary_email,
      "alias@primary.example",
      expect.any(AbortSignal)
    );
    const dialog = await screen.findByRole("dialog", { name: "Grant mailbox access?" });
    expect(dialog).toHaveTextContent(owner.primary_email);
    expect(dialog).toHaveTextContent("canonical@primary.example");
    expect(dialog).toHaveTextContent("read, send, and delete messages");

    await user.click(screen.getByRole("button", { name: "Grant access" }));
    expect(executeGmailDelegateChange).toHaveBeenCalledWith(
      "organization-1",
      "create",
      createPreview.confirmation_token
    );
    expect(await screen.findByText(/Mailbox delegate added/)).toBeVisible();
    await waitFor(() => expect(listGmailDelegates).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("requires deliberate confirmation before removing a delegate", async () => {
    const removePreview: GmailDelegateChangePreview = {
      ...createPreview,
      operation: "remove",
      delegate_primary_email: "delegate@primary.example",
      confirmation_token: "confirmation-token-remove-1234567890",
      effect: "The delegate's access to read, send, and delete mailbox messages will be revoked."
    };
    vi.mocked(previewGmailDelegateChange).mockResolvedValue(removePreview);
    vi.mocked(executeGmailDelegateChange).mockResolvedValue({
      operation: "remove",
      owner_primary_email: owner.primary_email,
      delegate_primary_email: "delegate@primary.example",
      outcome: "removed",
      message: "Mailbox delegate removed."
    });
    const user = userEvent.setup();
    renderDelegates();
    await screen.findByText("delegate@primary.example");

    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(executeGmailDelegateChange).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog", { name: "Revoke mailbox access?" });
    expect(dialog).toHaveTextContent("delegate@primary.example");
    expect(dialog).toHaveTextContent("will be revoked");

    await user.click(screen.getByRole("button", { name: "Revoke access" }));
    expect(executeGmailDelegateChange).toHaveBeenCalledWith(
      "organization-1",
      "remove",
      removePreview.confirmation_token
    );
  });

  it("disables every write control for a read-only viewer", async () => {
    renderDelegates({ canMutate: false });

    expect(await screen.findByText("delegate@primary.example")).toBeVisible();
    expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Review delegate" })).toBeDisabled();
    expect(screen.getByLabelText("Add delegate by primary email or alias")).toBeDisabled();
    expect(screen.getByText(/Administrator access is required/)).toBeVisible();
  });

  it.each([
    [
      new ApiError("private upstream", 403, "gmail_scope_missing"),
      /Gmail delegation access is not authorized/
    ],
    [
      new ApiError("private upstream", 409, "gmail_api_unavailable"),
      /Gmail API is not enabled/
    ],
    [
      new ApiError("private upstream", 429, "google_rate_limited"),
      /rate-limited/
    ]
  ])("renders a safe configuration or rate-limit error", async (failure, expected) => {
    vi.mocked(listGmailDelegates).mockRejectedValue(failure);
    renderDelegates();

    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(screen.queryByText("private upstream")).not.toBeInTheDocument();
  });

  it("does not submit an invalid delegate email", async () => {
    const user = userEvent.setup();
    renderDelegates();
    await screen.findByText("delegate@primary.example");

    await user.type(screen.getByLabelText("Add delegate by primary email or alias"), "invalid");
    await user.click(screen.getByRole("button", { name: "Review delegate" }));

    expect(screen.getByText("Enter a valid full email address.")).toBeVisible();
    expect(previewGmailDelegateChange).not.toHaveBeenCalled();
  });

  it("discards a stale delegate list after an organization switch", async () => {
    const first = deferred<GmailDelegateList>();
    vi.mocked(listGmailDelegates)
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({
        owner_primary_email: "second@secondary.example",
        delegates: [
          { primary_email: "new@secondary.example", verification_status: "accepted" }
        ]
      });
    const { rerender } = renderDelegates();

    rerender(
      <MailboxDelegates
        organizationId="organization-2"
        owner={{ ...owner, id: "owner-2", primary_email: "second@secondary.example" }}
        canMutate
      />
    );

    expect(await screen.findByText("new@secondary.example")).toBeVisible();
    first.resolve(populatedList);
    await waitFor(() =>
      expect(screen.queryByText("delegate@primary.example")).not.toBeInTheDocument()
    );
    expect(screen.getByText("new@secondary.example")).toBeVisible();
  });

  it("surfaces ambiguous mutation failure and prevents duplicate clicks", async () => {
    const pendingMutation = deferred<never>();
    vi.mocked(previewGmailDelegateChange).mockResolvedValue(createPreview);
    vi.mocked(executeGmailDelegateChange).mockReturnValue(pendingMutation.promise);
    const user = userEvent.setup();
    renderDelegates();
    await screen.findByText("delegate@primary.example");

    await user.type(
      screen.getByLabelText("Add delegate by primary email or alias"),
      "canonical@primary.example"
    );
    await user.click(screen.getByRole("button", { name: "Review delegate" }));
    const confirm = await screen.findByRole("button", { name: "Grant access" });
    await user.click(confirm);
    expect(confirm).toBeDisabled();
    await user.click(confirm);
    expect(executeGmailDelegateChange).toHaveBeenCalledTimes(1);

    pendingMutation.reject(new ApiError("private timeout", 504, "google_timeout"));
    expect(await screen.findByText(/did not return a reliable result/)).toBeVisible();
    expect(screen.queryByText("private timeout")).not.toBeInTheDocument();
  });
});
