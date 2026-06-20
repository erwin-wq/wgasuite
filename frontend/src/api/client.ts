import type {
  Assessment,
  AssessmentCreate,
  AssessmentReport,
  Asset,
  AssetCreate,
  Finding,
  FindingCreate,
  Organization,
  OrganizationCreate
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers
    }
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const detail = "detail" in errorBody ? String(errorBody.detail) : response.statusText;
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function listOrganizations(): Promise<Organization[]> {
  return request<Organization[]>("/api/v1/organizations");
}

export function createOrganization(payload: OrganizationCreate): Promise<Organization> {
  return request<Organization>("/api/v1/organizations", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listAssessments(): Promise<Assessment[]> {
  return request<Assessment[]>("/api/v1/assessments");
}

export function createAssessment(payload: AssessmentCreate): Promise<Assessment> {
  return request<Assessment>("/api/v1/assessments", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getAssessmentReport(assessmentId: string): Promise<AssessmentReport> {
  return request<AssessmentReport>(`/api/v1/assessments/${assessmentId}/report`);
}

export function listAssets(): Promise<Asset[]> {
  return request<Asset[]>("/api/v1/assets");
}

export function createAsset(payload: AssetCreate): Promise<Asset> {
  return request<Asset>("/api/v1/assets", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listFindings(): Promise<Finding[]> {
  return request<Finding[]>("/api/v1/findings");
}

export function createFinding(payload: FindingCreate): Promise<Finding> {
  return request<Finding>("/api/v1/findings", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
