export interface Organization {
  id: string;
  customer_id: string | null;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Customer {
  id: string;
  name: string;
  slug: string;
  contact_name: string | null;
  contact_email: string | null;
  status: "active" | "inactive" | "prospect" | string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type PlatformRole = "platform_admin" | "platform_support" | "customer_user";

export type CustomerMembershipRole = "customer_admin" | "customer_user" | "customer_viewer";

export interface UserCustomerMembership {
  customer_id: string;
  customer_name: string;
  role: CustomerMembershipRole;
  is_active: boolean;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: PlatformRole | string;
  is_active: boolean;
  created_at: string;
  customer_memberships: UserCustomerMembership[];
}

export interface Assessment {
  id: string;
  organization_id: string;
  title: string;
  status: string;
  scope_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  organization_id: string;
  name: string;
  asset_type: string;
  identifier: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface DreadScore {
  id: string;
  finding_id: string;
  damage: number;
  reproducibility: number;
  exploitability: number;
  affected_users: number;
  discoverability: number;
  total_score: number;
  risk_level: "Low" | "Medium" | "High" | "Critical";
  created_at: string;
  updated_at: string;
}

export interface Finding {
  id: string;
  assessment_id: string;
  asset_id: string | null;
  title: string;
  description: string | null;
  status: string;
  mitigation: string | null;
  dread_score: DreadScore;
  created_at: string;
  updated_at: string;
}

export interface RiskLevelCounts {
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface AssessmentReport {
  generated_at: string;
  assessment: Assessment;
  organization: Organization;
  assets: Asset[];
  findings: Finding[];
  total_findings: number;
  findings_per_risk_level: RiskLevelCounts;
  average_score: number | null;
  highest_score: number | null;
  highest_risk_level: DreadScore["risk_level"] | null;
}

export interface ScanRun {
  id: string;
  assessment_id: string;
  connector_type: "google_workspace_mock" | string;
  status: "pending" | "running" | "completed" | "failed" | string;
  started_at: string;
  completed_at: string | null;
  findings_created: number;
  summary: string | null;
  raw_result_json: Record<string, unknown> | null;
}

export interface GoogleWorkspaceCheck {
  check_id: string;
  title: string;
  category: string;
  risk_statement: string;
  description: string;
  recommendation: string;
  mock_status: "mock_only" | string;
  data_source_hint: string;
  future_google_api_hint: string;
  default_dread_score: DreadScoreCreate;
  default_risk_level: DreadScore["risk_level"] | string;
  maps_to_finding_title: string;
}

export type ConnectorAuthMethod =
  | "service_account_domain_wide_delegation"
  | "oauth_admin_consent"
  | "manual_import";

export type ConnectorStatus =
  | "not_configured"
  | "configured"
  | "connected"
  | "connection_failed";

export interface ConnectorConfig {
  id: string;
  organization_id: string;
  connector_type: "google_workspace";
  auth_method: ConnectorAuthMethod;
  status: ConnectorStatus;
  display_name: string;
  primary_domain: string | null;
  admin_subject_email: string | null;
  credential_provider: "file";
  credentials_configured: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
  last_tested_at: string | null;
  last_error: string | null;
}

export interface ConnectorConfigPayload {
  display_name: string;
  primary_domain: string | null;
  admin_subject_email: string | null;
  auth_method: ConnectorAuthMethod;
  status: ConnectorStatus;
  notes: string | null;
}

export interface ConnectorConfigTestResult {
  status: "not_implemented";
  message: string;
  recommended_next_step: string;
}

export interface PlatformAdminTotals {
  customers_count: number;
  organizations_count: number;
  assessments_count: number;
  connector_configs_count: number;
  scan_runs_count: number;
  audit_events_count: number;
}

export interface PlatformAdminCustomerSummary {
  id: string;
  name: string;
  slug: string;
  status: string;
  organization_count: number;
  connector_config_count: number;
  last_scan_run_at: string | null;
  last_audit_event_at: string | null;
}

export interface PlatformAdminConnectorSummary {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  organization_id: string;
  organization_name: string;
  connector_type: string;
  status: string;
  auth_method: string;
  primary_domain: string | null;
  last_tested_at: string | null;
  last_error: string | null;
}

export interface PlatformAdminScanRunSummary {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  organization_id: string;
  organization_name: string;
  assessment_id: string;
  assessment_title: string;
  connector_type: string;
  status: string;
  findings_created: number;
  started_at: string;
  completed_at: string | null;
  summary: string | null;
}

export interface PlatformAdminAuditEventSummary {
  id: string;
  created_at: string;
  actor_email: string | null;
  actor_role: string | null;
  customer_id: string | null;
  customer_name: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  outcome: string;
}

export interface PlatformAdminOverview {
  totals: PlatformAdminTotals;
  customers: PlatformAdminCustomerSummary[];
  connector_configs: PlatformAdminConnectorSummary[];
  recent_scan_runs: PlatformAdminScanRunSummary[];
  recent_audit_events: PlatformAdminAuditEventSummary[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export type OrganizationCreate = Pick<Organization, "name" | "description" | "customer_id">;

export type CustomerCreate = Pick<
  Customer,
  "name" | "slug" | "contact_name" | "contact_email" | "status" | "notes"
>;

export interface AssessmentCreate {
  organization_id: string;
  title: string;
  scope_summary: string | null;
}

export type AssetCreate = Pick<
  Asset,
  "organization_id" | "name" | "asset_type" | "identifier" | "description"
>;

export interface DreadScoreCreate {
  damage: number;
  reproducibility: number;
  exploitability: number;
  affected_users: number;
  discoverability: number;
}

export interface FindingCreate {
  assessment_id: string;
  asset_id: string | null;
  title: string;
  description: string | null;
  status: string;
  mitigation: string | null;
  dread_score: DreadScoreCreate;
}
