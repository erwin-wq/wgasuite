import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppNavigation } from "./AppNavigation";

describe("AppNavigation", () => {
  it("shows working administration areas and hides demo-only areas by default", () => {
    render(
      <AppNavigation
        activeSection="dashboard"
        canViewPlatformAdmin
        showDemoFeatures={false}
        onNavigate={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "Dashboard" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Customer Context" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Organizations" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Google Workspace" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Platform Admin" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Assessment Workspace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reports" })).not.toBeInTheDocument();
  });

  it("preserves role boundaries and routes selected navigation actions", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(
      <AppNavigation
        activeSection="organizations"
        canViewPlatformAdmin={false}
        showDemoFeatures={false}
        onNavigate={onNavigate}
      />
    );

    expect(screen.queryByRole("button", { name: "Platform Admin" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Google Workspace" }));
    expect(onNavigate).toHaveBeenCalledWith("google-workspace");
  });
});
