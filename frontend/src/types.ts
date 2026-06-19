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

export interface Finding {
  id: string;
  assessment_id: string;
  title: string;
  description: string | null;
  affected_asset: string | null;
  status: string;
  mitigation: string | null;
  dread_damage: number;
  dread_reproducibility: number;
  dread_exploitability: number;
  dread_affected_users: number;
  dread_discoverability: number;
  risk_score: number;
  created_at: string;
  updated_at: string;
}

export type OrganizationCreate = Pick<Organization, "name" | "description">;

export interface AssessmentCreate {
  title: string;
  scope_summary: string | null;
}

export type FindingCreate = Omit<Finding, "id" | "assessment_id" | "risk_score" | "created_at" | "updated_at">;
