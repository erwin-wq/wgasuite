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
  credential_provider: "file" | "managed_file";
  credentials_configured: boolean;
  service_account_email: string | null;
  service_account_client_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  last_tested_at: string | null;
  last_error_code: string | null;
  last_error: string | null;
}

export interface ConnectorConfigPayload {
  display_name: string;
  primary_domain: string | null;
  admin_subject_email: string | null;
  auth_method: ConnectorAuthMethod;
  notes: string | null;
}

export interface ConnectorConfigTestResult {
  status: "connected" | "connection_failed";
  tested_at: string;
  message: string;
  error_code: string | null;
  error_category: "configuration" | "google" | "network" | "unexpected" | null;
  retryable: boolean;
  persisted: boolean;
}

export interface ConnectorCredentialResult {
  credential_provider: "file" | "managed_file";
  credentials_configured: boolean;
  service_account_email: string;
  service_account_client_id: string;
}

export type GoogleWorkspaceUserMatchType =
  | "primary_email"
  | "alias"
  | "non_editable_alias";

export interface GoogleWorkspaceUser {
  id: string;
  full_name: string | null;
  primary_email: string;
  aliases: string[];
  non_editable_aliases: string[];
  suspended: boolean;
  archived: boolean | null;
  org_unit_path: string | null;
  is_mailbox_setup: boolean | null;
  is_super_admin: boolean | null;
  is_delegated_admin: boolean | null;
  creation_time: string | null;
  last_login_time: string | null;
  suspension_reason?: string | null;
  deletion_time?: string | null;
  matched_by: GoogleWorkspaceUserMatchType;
}

export type GoogleWorkspaceUserStatusOperation = "suspend" | "reactivate";

export interface GoogleWorkspaceUserStatusPreview {
  operation: GoogleWorkspaceUserStatusOperation;
  organization_id: string;
  customer_id: string;
  target_google_id: string;
  target_primary_email: string;
  previous_suspended: boolean;
  requested_suspended: boolean;
  confirmation_token: string;
  expires_at: string;
  effect: string;
}

export interface GoogleWorkspaceUserStatusMutationResult {
  operation: GoogleWorkspaceUserStatusOperation;
  target_google_id: string;
  target_primary_email: string;
  previous_suspended: boolean;
  suspended: boolean;
  outcome: "suspended" | "reactivated";
  message: string;
}

export interface GoogleWorkspaceUserStatusReconciliationResult {
  operation: GoogleWorkspaceUserStatusOperation;
  target_google_id: string;
  target_primary_email: string;
  status: "verified" | "unknown";
  observed_suspended: boolean;
  attempts: number;
  correlation_id: string;
  message: string;
}

export interface GoogleWorkspaceUserOrgUnitMovePreview {
  organization_id: string;
  customer_id: string;
  target_google_id: string;
  target_primary_email: string;
  source_org_unit_path: string;
  destination_org_unit_id: string;
  destination_org_unit_path: string;
  confirmation_token: string;
  expires_at: string;
  effect: string;
}

export interface GoogleWorkspaceUserOrgUnitMoveResult {
  target_google_id: string;
  target_primary_email: string;
  previous_org_unit_path: string;
  org_unit_path: string;
  outcome: "moved";
  message: string;
}

export interface GoogleWorkspaceUserOrgUnitMoveReconciliationResult {
  target_google_id: string;
  target_primary_email: string;
  status: "verified" | "unknown";
  observed_org_unit_path: string;
  attempts: number;
  correlation_id: string;
  message: string;
}

export type GoogleWorkspaceUserGroupRole = "MEMBER" | "MANAGER" | "OWNER";

export interface GoogleWorkspaceUserGroupMembership {
  group_id: string;
  group_name: string;
  group_primary_email: string;
  role: GoogleWorkspaceUserGroupRole;
  member_type: "USER";
  status: string | null;
}

export interface GoogleWorkspaceUserGroupMembershipResult {
  user_id: string;
  user_primary_email: string;
  matched_by: GoogleWorkspaceUserMatchType;
  memberships: GoogleWorkspaceUserGroupMembership[];
  next_page_token: string | null;
  verification_complete: boolean;
  candidates_examined: number;
  omitted_external_count: number;
  omitted_indirect_count: number;
}

export type UserDirectorySearchField =
  | "all"
  | "email"
  | "given_name"
  | "family_name"
  | "full_name";
export type UserDirectorySuspendedFilter = "all" | "active" | "suspended";
export type UserDirectoryAdminFilter = "all" | "super_admin" | "delegated_admin";
export type UserDirectoryArchivedFilter = "all" | "archived" | "not_archived";
export type UserDirectoryOrder = "email" | "given_name" | "family_name";
export type UserDirectorySortDirection = "ascending" | "descending";

export interface GoogleWorkspaceDirectoryUser {
  id: string;
  full_name: string | null;
  given_name: string | null;
  family_name: string | null;
  primary_email: string;
  org_unit_path: string | null;
  suspended: boolean | null;
  archived: boolean | null;
  is_super_admin: boolean | null;
  is_delegated_admin: boolean | null;
  creation_time: string | null;
  last_login_time: string | null;
}

export interface GoogleWorkspaceUserDirectoryResult {
  users: GoogleWorkspaceDirectoryUser[];
  next_page_token: string | null;
}

export interface GoogleWorkspaceUserDirectoryRequest {
  search: string;
  search_field: UserDirectorySearchField;
  org_unit_path: string | null;
  suspended: UserDirectorySuspendedFilter;
  admin_status: UserDirectoryAdminFilter;
  archived: UserDirectoryArchivedFilter;
  order_by: UserDirectoryOrder;
  sort_direction: UserDirectorySortDirection;
  page_size: 25 | 50 | 100;
  page_token: string | null;
}

export interface GoogleWorkspaceOrganizationalUnit {
  id: string;
  name: string;
  description: string | null;
  path: string;
  parent_id: string | null;
  parent_path: string | null;
  read_only: true;
}

export interface GoogleWorkspaceOrganizationalUnitTreeNode
  extends GoogleWorkspaceOrganizationalUnit {
  children: GoogleWorkspaceOrganizationalUnitTreeNode[];
}

export interface GoogleWorkspaceOrganizationalUnitHierarchy {
  roots: GoogleWorkspaceOrganizationalUnitTreeNode[];
  total: number;
}

export type GmailDelegateVerificationStatus =
  | "accepted"
  | "pending"
  | "rejected"
  | "unknown";

export interface GmailDelegate {
  primary_email: string;
  verification_status: GmailDelegateVerificationStatus;
}

export interface GmailDelegateList {
  owner_primary_email: string;
  delegates: GmailDelegate[];
}

export interface GmailDelegateChangePreview {
  operation: "create" | "remove";
  owner_primary_email: string;
  delegate_primary_email: string;
  confirmation_token: string;
  expires_at: string;
  effect: string;
}

export interface GmailDelegateMutationResult {
  operation: "create" | "remove";
  owner_primary_email: string;
  delegate_primary_email: string;
  outcome: "created" | "removed";
  message: string;
}

export type GmailDelegateObservedState =
  | "accepted"
  | "absent"
  | "not_observed"
  | "pending"
  | "rejected"
  | "unknown"
  | "present";

export interface GmailDelegateReconciliationResult {
  operation: "create" | "remove";
  owner_primary_email: string;
  delegate_primary_email: string;
  status: "verified" | "unknown";
  observed_state: GmailDelegateObservedState;
  attempts: number;
  correlation_id: string;
  message: string;
}

export interface GoogleWorkspaceGroup {
  id: string;
  primary_email: string;
  name: string;
  description: string | null;
  aliases: string[];
  non_editable_aliases: string[];
  direct_members_count: number | null;
  membership_mutable: boolean;
  restriction_reason: string | null;
}

export interface GoogleWorkspaceGroupSearchResult {
  groups: GoogleWorkspaceGroup[];
  next_page_token: string | null;
}

export type GoogleWorkspaceGroupMemberType =
  | "USER"
  | "GROUP"
  | "CUSTOMER"
  | "EXTERNAL"
  | "UNKNOWN";

export type GoogleWorkspaceGroupMemberRole = "MEMBER" | "MANAGER" | "OWNER" | "UNKNOWN";

export interface GoogleWorkspaceGroupMember {
  id: string;
  email: string | null;
  type: GoogleWorkspaceGroupMemberType;
  role: GoogleWorkspaceGroupMemberRole;
  status: string | null;
  direct: boolean;
  mutation_supported: boolean;
  restriction_reason: string | null;
}

export interface GoogleWorkspaceGroupMemberList {
  group: GoogleWorkspaceGroup;
  members: GoogleWorkspaceGroupMember[];
  next_page_token: string | null;
}

export interface GroupMembershipPreview {
  operation: "add" | "remove";
  group_primary_email: string;
  member_primary_email: string;
  member_role: "MEMBER" | "MANAGER" | "OWNER";
  confirmation_token: string;
  expires_at: string;
  effect: string;
}

export interface GroupMembershipMutationResult {
  operation: "add" | "remove";
  group_primary_email: string;
  member_primary_email: string;
  outcome: "added" | "removed";
  message: string;
}

export interface GroupMembershipReconciliationResult {
  operation: "add" | "remove";
  group_primary_email: string;
  member_primary_email: string;
  status: "verified" | "unknown";
  observed_state: "present" | "absent";
  attempts: number;
  correlation_id: string;
  message: string;
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
