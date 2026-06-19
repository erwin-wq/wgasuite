export interface Organization {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
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

export type OrganizationCreate = Pick<Organization, "name" | "description">;

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
