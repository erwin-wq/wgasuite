import type { Page, Route } from "@playwright/test";

const now = "2026-11-21T08:00:00Z";

export const customers = [
  { id: "customer-northstar", name: "Northstar Labs", slug: "northstar", contact_name: null, contact_email: null, status: "active", notes: null, created_at: now, updated_at: now },
  { id: "customer-summit", name: "Summit Systems", slug: "summit", contact_name: null, contact_email: null, status: "active", notes: null, created_at: now, updated_at: now }
];

export const organizations = [
  { id: "organization-northstar", customer_id: customers[0].id, name: "Northstar Workspace", description: "Fictional QA tenant", created_at: now, updated_at: now },
  { id: "organization-summit", customer_id: customers[1].id, name: "Summit Workspace", description: "Second fictional QA tenant", created_at: now, updated_at: now }
];

export const connector = {
  id: "connector-fictional",
  organization_id: organizations[0].id,
  connector_type: "google_workspace",
  auth_method: "service_account_domain_wide_delegation",
  status: "connected",
  display_name: "Northstar Google Workspace",
  primary_domain: "northstar.example.invalid",
  admin_subject_email: "admin@northstar.example.invalid",
  credential_provider: "managed_file",
  credentials_configured: true,
  service_account_email: "service@fictional.invalid",
  service_account_client_id: "000000000000000000000",
  notes: null,
  created_at: now,
  updated_at: now,
  last_tested_at: now,
  last_error_code: null,
  last_error: null
};

export const directoryUser = {
  id: "user-fictional",
  full_name: "Alex Example",
  given_name: "Alex",
  family_name: "Example",
  primary_email: "alex@northstar.example.invalid",
  aliases: ["alias@northstar.example.invalid"],
  non_editable_aliases: [],
  org_unit_path: "/Engineering",
  suspended: false,
  archived: false,
  is_super_admin: false,
  is_delegated_admin: false,
  is_mailbox_setup: true,
  creation_time: "2024-01-02T03:04:05Z",
  last_login_time: now,
  customer_id: "C00000000"
};

export const group = {
  id: "group-fictional",
  primary_email: "team@northstar.example.invalid",
  name: "Northstar Team",
  description: "Fictional team",
  aliases: [],
  non_editable_aliases: [],
  direct_members_count: 1,
  membership_mutable: true,
  restriction_reason: null
};

export const hierarchy = {
  total: 3,
  roots: [{
    id: "id:root",
    name: "Northstar Workspace",
    description: null,
    path: "/",
    parent_id: null,
    parent_path: null,
    read_only: true,
    user_move_protected: false,
    children: [
      { id: "id:engineering", name: "Engineering", description: "Fictional engineering OU", path: "/Engineering", parent_id: "id:root", parent_path: "/", read_only: true, user_move_protected: false, children: [] },
      { id: "id:guests", name: "Workspace Guests", description: null, path: "/Workspace Guests", parent_id: "id:root", parent_path: "/", read_only: true, user_move_protected: true, children: [] }
    ]
  }]
};

const platformOverview = {
  totals: { customers_count: 2, organizations_count: 2, assessments_count: 0, connector_configs_count: 1, scan_runs_count: 0, audit_events_count: 1 },
  customers: customers.map((customer) => ({ id: customer.id, name: customer.name, slug: customer.slug, status: customer.status, organization_count: 1, connector_config_count: customer.id === customers[0].id ? 1 : 0, last_scan_run_at: null, last_audit_event_at: now })),
  connector_configs: [{ id: connector.id, customer_id: customers[0].id, customer_name: customers[0].name, organization_id: organizations[0].id, organization_name: organizations[0].name, connector_type: connector.connector_type, status: connector.status, auth_method: connector.auth_method, primary_domain: connector.primary_domain, last_tested_at: now, last_error: null }],
  recent_scan_runs: [],
  recent_audit_events: [{ id: "audit-fictional", created_at: now, actor_email: "operator@example.invalid", actor_role: "platform_admin", customer_id: customers[0].id, customer_name: customers[0].name, action: "connector_config.viewed", object_type: "connector_config", object_id: connector.id, outcome: "success" }]
};

export interface ApiHarness {
  calls: Array<{ method: string; path: string }>;
  rejectedWrites: string[];
  releaseDelayedUsers: () => void;
}

export async function installApiHarness(
  page: Page,
  options: {
    expiredSession?: boolean;
    role?: "platform_admin" | "customer_user";
    usersState?: "content" | "delayed" | "empty" | "error";
  } = {}
): Promise<ApiHarness> {
  const calls: ApiHarness["calls"] = [];
  const rejectedWrites: string[] = [];
  let releaseDelayedUsers: () => void = () => undefined;
  const delayedUsers = new Promise<void>((resolve) => {
    releaseDelayedUsers = resolve;
  });

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    calls.push({ method, path });

    const respond = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/auth/login") {
      const email = String(request.postDataJSON()?.email ?? "");
      return respond({ access_token: email.startsWith("second") ? "fictional-second-token" : "fictional-e2e-token", token_type: "bearer" });
    }
    if (path === "/api/v1/auth/me") {
      if (options.expiredSession) return respond({ detail: "Session expired" }, 401);
      const isSecond = request.headers().authorization?.includes("fictional-second-token") === true;
      const role = options.role ?? "platform_admin";
      return respond({
        id: isSecond ? "operator-second-fictional" : "operator-fictional",
        email: isSecond ? "second@example.invalid" : "operator@example.invalid",
        full_name: isSecond ? "Second QA Operator" : "Fictional QA Operator",
        role,
        is_active: true,
        created_at: now,
        customer_memberships: role === "customer_user" ? [{ customer_id: customers[0].id, customer_name: customers[0].name, role: "customer_user", is_active: true }] : []
      });
    }
    if (path === "/api/v1/customers") return respond(customers);
    if (path === "/api/v1/organizations") return respond(organizations);
    if (path.endsWith("/connector-configs")) {
      return respond(path.includes(organizations[0].id) ? [connector] : [{ ...connector, id: "connector-summit", organization_id: organizations[1].id, display_name: "Summit Google Workspace", primary_domain: "summit.example.invalid" }]);
    }
    if (path === "/api/v1/connectors/google-workspace/checks") return respond([]);
    if (path.endsWith("/google-workspace/users/list")) {
      if (options.usersState === "delayed") await delayedUsers;
      if (options.usersState === "error") return respond({ detail: { code: "google_service_unavailable", message: "Directory temporarily unavailable." } }, 503);
      if (options.usersState === "empty") return respond({ users: [], next_page_token: null });
      const user = path.includes(organizations[1].id) ? { ...directoryUser, id: "user-summit", full_name: "Sam Summit", primary_email: "sam@summit.example.invalid", aliases: [] } : directoryUser;
      return respond({ users: [user], next_page_token: null });
    }
    if (path.endsWith("/google-workspace/users/lookup")) return respond(directoryUser);
    if (path.endsWith("/google-workspace/users/group-memberships")) return respond({ memberships: [], next_page_token: null, omissions: [], verified_customer_id: "C00000000" });
    if (path.endsWith("/google-workspace/groups/search")) return respond({ groups: [group], next_page_token: null });
    if (path.endsWith("/google-workspace/groups/get")) return respond(group);
    if (path.endsWith("/google-workspace/groups/members/list")) return respond({ group, members: [], next_page_token: null });
    if (path.endsWith("/google-workspace/orgunits/list")) return respond(hierarchy);
    if (path.endsWith("/google-workspace/gmail-delegates/list")) return respond({ owner_primary_email: directoryUser.primary_email, delegates: [] });
    if (path === "/api/v1/platform-admin/overview") return respond(platformOverview);

    if (method !== "GET") {
      rejectedWrites.push(`${method} ${path}`);
      return respond({ detail: { code: "e2e_write_blocked", message: "Release-gate fixtures reject writes." } }, 409);
    }
    return respond({ detail: "No release-gate fixture exists for this request." }, 404);
  });

  return { calls, rejectedWrites, releaseDelayedUsers };
}

export async function authenticate(page: Page): Promise<void> {
  await page.addInitScript(() => localStorage.setItem("wgasuite.authToken", "fictional-e2e-token"));
}

export async function seedAppearance(
  page: Page,
  theme: "navy-teal" | "cobalt-ice" | "graphite-copper",
  density: "comfortable" | "compact"
): Promise<void> {
  await page.addInitScript(({ nextTheme, nextDensity }) => {
    const accountId = "operator-fictional";
    let hash = 0x811c9dc5;
    for (let index = 0; index < accountId.length; index += 1) {
      hash ^= accountId.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    const account = (hash >>> 0).toString(36);
    const preference = JSON.stringify({ version: 2, account, theme: nextTheme, density: nextDensity });
    localStorage.setItem(`wgasuite.ui.theme.account.v1.${account}`, preference);
    localStorage.setItem("wgasuite.ui.theme.active.v1", preference);
  }, { nextTheme: theme, nextDensity: density });
}
