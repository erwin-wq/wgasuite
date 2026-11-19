import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Settings } from "lucide-react";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Button, IconButton } from "./Button";
import { Card } from "./Card";
import { Dropdown } from "./Dropdown";
import { Alert, Badge, EmptyState, ErrorState, Skeleton, Toast, ToastRegion } from "./Feedback";
import { Input, SearchField, Select, Textarea } from "./FormControls";
import { Modal } from "./Modal";
import { PageHeader } from "./PageHeader";
import { Tabs } from "./Tabs";
import { Tooltip } from "./Tooltip";

describe("enterprise UI components", () => {
  it("renders button variants and exposes a loading state", () => {
    render(<Button loading loadingLabel="Saving settings">Save</Button>);
    const button = screen.getByRole("button", { name: /Saving settings Save/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("requires an accessible label for icon buttons", () => {
    render(<IconButton label="Open settings" icon={<Settings aria-hidden="true" />} />);
    expect(screen.getByRole("button", { name: "Open settings" })).toBeVisible();
  });

  it("associates field hints and validation errors", () => {
    const { rerender } = render(<Input label="Name" hint="Use the display name." />);
    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("Use the display name.");
    rerender(<Input label="Name" error="Name is required." />);
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Name is required.");
  });

  it("announces required and optional fields and keeps help text associated with errors", () => {
    render(
      <>
        <Input label="Customer name" required hint="Use the legal display name." error="Customer name is required." />
        <Textarea label="Notes" optional hint="Do not include credentials." />
      </>
    );

    expect(screen.getByLabelText("Customer name")).toBeRequired();
    expect(screen.getByLabelText("Customer name")).toHaveAccessibleDescription(
      "Use the legal display name. Customer name is required."
    );
    expect(screen.getByLabelText(/Notes/)).toHaveAccessibleDescription("Do not include credentials.");
  });

  it("renders native select options and clears a search field", async () => {
    const onClear = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <Select label="Role" options={[{ value: "viewer", label: "Viewer" }]} />
        <SearchField label="Search" value="workspace" onChange={() => undefined} onClear={onClear} />
      </>
    );
    expect(screen.getByRole("option", { name: "Viewer" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("supports arrow-key navigation and selection in tabs", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Tabs
        ariaLabel="Directory views"
        activeId="users"
        onChange={onChange}
        items={[{ id: "users", label: "Users" }, { id: "groups", label: "Groups" }]}
      />
    );
    const users = screen.getByRole("tab", { name: "Users" });
    const groups = screen.getByRole("tab", { name: "Groups" });
    users.focus();
    await user.keyboard("{ArrowRight}{Enter}");
    expect(groups).toHaveFocus();
    expect(onChange).toHaveBeenCalledWith("groups");
  });

  it("operates a keyboard-accessible dropdown and restores trigger focus", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<Dropdown label="Actions" trigger="Actions" items={[{ id: "edit", label: "Edit", onSelect }]} />);
    const trigger = screen.getByRole("button", { name: "Actions" });
    await user.click(trigger);
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveFocus();
  });

  it("links tooltip content to its interactive child", () => {
    render(<Tooltip content="Configuration"><button type="button">Settings</button></Tooltip>);
    const button = screen.getByRole("button", { name: "Settings" });
    expect(button).toHaveAttribute("aria-describedby", screen.getByRole("tooltip").id);
  });

  it("closes a modal with Escape and restores focus", async () => {
    const user = userEvent.setup();
    function ModalFixture() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open modal</button>
          <Modal open={open} onClose={() => setOpen(false)} title="Review change">
            <button type="button">Confirm</button>
          </Modal>
        </>
      );
    }
    render(<ModalFixture />);
    const trigger = screen.getByRole("button", { name: "Open modal" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Review change" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(screen.getByRole("button", { name: "Confirm" })).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("restores an explicit trigger and supports consecutive modal openings", async () => {
    const user = userEvent.setup();
    function ModalFixture() {
      const [open, setOpen] = useState(false);
      const triggerRef = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>Review membership</button>
          <Modal
            open={open}
            onClose={() => setOpen(false)}
            title="Confirm membership"
            restoreFocusRef={triggerRef}
          >
            <button type="button" onClick={() => setOpen(false)}>Cancel</button>
          </Modal>
        </>
      );
    }
    render(<ModalFixture />);
    const trigger = screen.getByRole("button", { name: "Review membership" });

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });

  it("dismisses safely when the explicit restore target becomes disabled", async () => {
    const user = userEvent.setup();
    function ModalFixture() {
      const [open, setOpen] = useState(false);
      const [disabled, setDisabled] = useState(false);
      const triggerRef = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button ref={triggerRef} type="button" disabled={disabled} onClick={() => setOpen(true)}>
            Open protected dialog
          </button>
          <Modal
            open={open}
            onClose={() => setOpen(false)}
            title="Protected dialog"
            restoreFocusRef={triggerRef}
          >
            <button type="button" onClick={() => { setDisabled(true); setOpen(false); }}>
              Disable trigger and close
            </button>
          </Modal>
        </>
      );
    }
    render(<ModalFixture />);
    const trigger = screen.getByRole("button", { name: "Open protected dialog" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Disable trigger and close" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toBeDisabled();
    expect(trigger).not.toHaveFocus();
  });

  it("renders semantic feedback and status components", () => {
    render(
      <>
        <Badge variant="success">Connected</Badge>
        <Alert variant="warning" title="Review required">Check the tenant.</Alert>
        <ToastRegion><Toast title="Saved">The setting was stored.</Toast></ToastRegion>
        <Skeleton lines={2} />
      </>
    );
    expect(screen.getByText("Connected")).toBeVisible();
    expect(screen.getByText("Review required").closest("[role='status']")).toHaveTextContent("Check the tenant.");
    expect(screen.getByLabelText("Notifications")).toHaveTextContent("Saved");
    expect(document.querySelectorAll(".ui-skeleton")).toHaveLength(2);
  });

  it("renders page, card, empty and error foundations with semantic landmarks", () => {
    render(
      <>
        <PageHeader breadcrumbs={["Directory", "Users"]} title="Users" description="Browse users." />
        <Card as="article">Card content</Card>
        <EmptyState title="No users">Change the filters.</EmptyState>
        <ErrorState title="Could not load">Try again later.</ErrorState>
      </>
    );
    expect(screen.getByRole("heading", { name: "Users" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Directory/Users");
    expect(screen.getByRole("article")).toHaveTextContent("Card content");
    expect(screen.getByRole("status")).toHaveTextContent("No users");
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load");
  });
});
