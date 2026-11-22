import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { authenticate, installApiHarness, seedAppearance } from "./fixtures";

const routes = [
  { path: "/overview", title: "Workspace overview", marker: ".overview-action-list" },
  { path: "/directory/users", title: "User directory", marker: ".user-directory" },
  { path: "/directory/users/lookup", title: "Exact user lookup", marker: ".user-lookup" },
  { path: "/directory/groups", title: "Groups", marker: ".group-management" },
  { path: "/directory/org-units", title: "Organizational units", marker: ".organizational-units" },
  { path: "/gmail/delegations", title: "Gmail delegations", marker: ".gmail-mailbox-lookup" },
  { path: "/settings/connections", title: "Connections", marker: ".workspace-connection-overview" },
  { path: "/administration/customers", title: "Customers", marker: "[aria-label='Customer administration']" },
  { path: "/administration/organizations", title: "Organizations", marker: "[aria-label='Organization administration']" },
  { path: "/platform", title: "Platform administration", marker: "[aria-label='Platform support overview']" }
] as const;

const themes = ["navy-teal", "cobalt-ice", "graphite-copper"] as const;
const densities = ["comfortable", "compact"] as const;

async function expectHealthyPage(page: Page): Promise<void> {
  await expect(page.locator(".premium-app-shell")).toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
}

for (const [index, route] of routes.entries()) {
  test(`${route.path} renders its accepted route contract`, async ({ page }, testInfo) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    await authenticate(page);
    const theme = themes[(index + testInfo.project.name.length) % themes.length];
    const density = densities[(index + testInfo.project.name.length) % densities.length];
    await seedAppearance(page, theme, density);
    const api = await installApiHarness(page);

    await page.goto(route.path);
    await expect(page).toHaveURL(route.path);
    await expect(page.getByRole("heading", { level: 1, name: route.title })).toBeVisible();
    await expect(page.locator(route.marker)).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator("html")).toHaveAttribute("data-density", density);
    await expectHealthyPage(page);
    const accessibility = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    expect(page.url()).not.toContain("@");
    expect(consoleErrors).toEqual([]);
    expect(api.rejectedWrites).toEqual([]);
  });
}

test("login, logout, direct routes, history, reload and session expiry remain coherent", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "One browser profile is sufficient for the authentication contract.");
  const api = await installApiHarness(page);
  await page.goto("/directory/groups");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill("operator@example.invalid");
  await page.getByLabel("Password").fill("fictional-password");
  await page.getByRole("button", { name: "Inloggen" }).click();
  await expect(page).toHaveURL(/\/directory\/groups$/);

  await page.getByRole("link", { name: "Organizational units", exact: true }).click();
  await expect(page).toHaveURL(/\/directory\/org-units$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/directory\/groups$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/directory\/org-units$/);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Organizational units" })).toBeVisible();

  await page.getByRole("button", { name: /Account and appearance/ }).click();
  await page.getByRole("menuitem", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("wgasuite.authToken"))).toBeNull();
  expect(api.rejectedWrites).toEqual([]);

  const expired = await page.context().newPage();
  await expired.addInitScript(() => localStorage.setItem("wgasuite.authToken", "expired-fictional-token"));
  await installApiHarness(expired, { expiredSession: true });
  await expired.goto("/overview");
  await expect(expired).toHaveURL(/\/login$/);
  await expect.poll(() => expired.evaluate(() => localStorage.getItem("wgasuite.authToken"))).toBeNull();
});

test("theme and density persist without exposing account or tenant identifiers", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "One browser profile is sufficient for persistence coverage.");
  await authenticate(page);
  await installApiHarness(page);
  await page.goto("/overview");
  await page.getByRole("button", { name: /Account and appearance/ }).click();
  await page.getByRole("menuitemradio", { name: /Graphite & Copper/ }).click();
  await page.getByRole("menuitemradio", { name: /Compact/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "graphite-copper");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "graphite-copper");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  const storage = await page.evaluate(() => JSON.stringify(localStorage));
  expect(storage).not.toContain("operator@example.invalid");
  expect(storage).not.toContain("customer-northstar");
  expect(storage).not.toContain("organization-northstar");

  await page.getByRole("button", { name: /Account and appearance/ }).click();
  await page.getByRole("menuitem", { name: "Logout" }).click();
  await page.getByLabel("Email").fill("second@example.invalid");
  await page.getByLabel("Password").fill("fictional-password");
  await page.getByRole("button", { name: "Inloggen" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "navy-teal");
  await expect(page.locator("html")).toHaveAttribute("data-density", "comfortable");

  await page.getByRole("button", { name: /Account and appearance/ }).click();
  await page.getByRole("menuitem", { name: "Logout" }).click();
  await page.getByLabel("Email").fill("operator@example.invalid");
  await page.getByLabel("Password").fill("fictional-password");
  await page.getByRole("button", { name: "Inloggen" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "graphite-copper");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
});

test("tenant switching rejects stale directory state and keeps identifiers out of the URL", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "One desktop flow is sufficient for tenant invalidation coverage.");
  await authenticate(page);
  const api = await installApiHarness(page);
  await page.goto("/directory/users");
  await expect(page.getByText("alex@northstar.example.invalid")).toBeVisible();

  await page.getByRole("button", { name: /Active workspace/i }).click();
  await page.getByLabel("Customer", { exact: true }).selectOption("customer-summit");
  await expect(page.getByRole("button", { name: /Active workspace Summit Workspace Summit Systems/i })).toBeVisible();
  await expect(page.getByText("sam@summit.example.invalid")).toBeVisible();
  await expect(page.getByText("alex@northstar.example.invalid")).toHaveCount(0);
  expect(page.url()).not.toContain("customer-");
  expect(page.url()).not.toContain("organization-");
  expect(page.url()).not.toContain("@");
  expect(api.rejectedWrites).toEqual([]);
});

test("user alias, Groups, Gmail and connector workflows render authoritative read-only results", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "One desktop flow is sufficient for domain workflow coverage.");
  await authenticate(page);
  const api = await installApiHarness(page);

  await page.goto("/directory/users/lookup");
  await page.getByLabel("Primary email or user alias").fill("alias@northstar.example.invalid");
  await page.getByRole("button", { name: "Look up user" }).click();
  await expect(page.getByRole("article", { name: "Google Workspace user result" })).toContainText("Alex Example");
  expect(page.url()).not.toContain("@");

  await page.getByRole("link", { name: "Groups", exact: true }).click();
  await page.getByRole("button", { name: "View members" }).click();
  await expect(page.getByRole("heading", { name: "Northstar Team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Direct members", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Delegations", exact: true }).click();
  await page.getByLabel("Primary email or user alias").fill("alias@northstar.example.invalid");
  await page.getByRole("button", { name: "Find mailbox" }).click();
  await expect(page.getByRole("heading", { name: "Existing delegates" })).toBeVisible();
  await expect(page.getByText("No delegates")).toBeVisible();

  await page.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(page.getByLabel("Google Workspace connection status")).toContainText("Connected");
  expect(api.rejectedWrites).toEqual([]);
});

test("role guards fall back safely without loading protected platform data", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "One desktop flow is sufficient for role-guard coverage.");
  await authenticate(page);
  const api = await installApiHarness(page, { role: "customer_user" });
  await page.goto("/platform");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("heading", { name: "Workspace overview" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Platform", exact: true })).toHaveCount(0);
  expect(api.calls.some((call) => call.path === "/api/v1/platform-admin/overview")).toBe(false);
  expect(api.rejectedWrites).toEqual([]);
});

test("directory loading, empty and recoverable error states remain distinct", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "State variants are viewport-independent and covered once.");
  for (const state of ["delayed", "empty", "error"] as const) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    await authenticate(page);
    const api = await installApiHarness(page, { usersState: state });
    const navigation = page.goto("/directory/users");
    if (state === "delayed") {
      await expect(page.getByLabel("Loading Workspace directory users")).toBeVisible();
      api.releaseDelayedUsers();
    }
    await navigation;
    if (state === "delayed") await expect(page.getByText("alex@northstar.example.invalid")).toBeVisible();
    if (state === "empty") await expect(page.getByText("No users on this page")).toBeVisible();
    if (state === "error") await expect(page.getByText("Google Directory is temporarily unavailable. Try again shortly.")).toBeVisible();
    expect(api.rejectedWrites).toEqual([]);
    await context.close();
  }
});
