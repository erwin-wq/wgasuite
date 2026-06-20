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

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "assessor" | "viewer" | string;
  is_active: boolean;
  created_at: string;
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
