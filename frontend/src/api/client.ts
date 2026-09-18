import type {
  Assessment,
  AssessmentCreate,
  AssessmentReport,
  Asset,
  AssetCreate,
  ConnectorConfig,
  ConnectorConfigPayload,
  ConnectorConfigTestResult,
  Customer,
  CustomerCreate,
  Finding,
  FindingCreate,
  GoogleWorkspaceCheck,
  LoginRequest,
  PlatformAdminOverview,
  ScanRun,
  TokenResponse,
  Organization,
  OrganizationCreate,
  User
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const AUTH_TOKEN_STORAGE_KEY = "wgasuite.authToken";
const LEGACY_AUTH_TOKEN_STORAGE_KEY = "admindeck.authToken:v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getStoredAuthToken(): string | null {
  try {
    const token = window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
    if (token) {
      return token;
    }

    const legacyToken = window.localStorage.getItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
    if (!legacyToken) {
      return null;
    }

    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, legacyToken);
    window.localStorage.removeItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
    return legacyToken;
  } catch {
    return null;
  }
}

export function setStoredAuthToken(token: string): void {
  try {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    window.localStorage.removeItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in private browsing or hardened browser configurations.
  }
}

export function clearStoredAuthToken(): void {
  try {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    window.localStorage.removeItem(LEGACY_AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // There is no local session to clear when browser storage is unavailable.
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredAuthToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers
    }
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearStoredAuthToken();
    }
    const errorBody = await response.json().catch(() => ({}));
    const detail = "detail" in errorBody ? String(errorBody.detail) : response.statusText;
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export function login(payload: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getCurrentUser(): Promise<User> {
  return request<User>("/api/v1/auth/me");
}

export function getPlatformAdminOverview(): Promise<PlatformAdminOverview> {
  return request<PlatformAdminOverview>("/api/v1/platform-admin/overview");
}

export function listCustomers(): Promise<Customer[]> {
  return request<Customer[]>("/api/v1/customers");
}

export function createCustomer(payload: CustomerCreate): Promise<Customer> {
  return request<Customer>("/api/v1/customers", {
    method: "POST",
    body: JSON.stringify(payload)
  });
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

export function runMockGoogleWorkspaceScan(assessmentId: string): Promise<ScanRun> {
  return request<ScanRun>(`/api/v1/assessments/${assessmentId}/scan-runs/google-workspace-mock`, {
    method: "POST"
  });
}

export function listAssessmentScanRuns(assessmentId: string): Promise<ScanRun[]> {
  return request<ScanRun[]>(`/api/v1/assessments/${assessmentId}/scan-runs`);
}

export function listGoogleWorkspaceChecks(): Promise<GoogleWorkspaceCheck[]> {
  return request<GoogleWorkspaceCheck[]>("/api/v1/connectors/google-workspace/checks");
}

export function listOrganizationConnectorConfigs(
  organizationId: string
): Promise<ConnectorConfig[]> {
  return request<ConnectorConfig[]>(`/api/v1/organizations/${organizationId}/connector-configs`);
}

export function upsertGoogleWorkspaceConnectorConfig(
  organizationId: string,
  payload: ConnectorConfigPayload
): Promise<ConnectorConfig> {
  return request<ConnectorConfig>(
    `/api/v1/organizations/${organizationId}/connector-configs/google-workspace`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function testConnectorConfig(
  connectorConfigId: string
): Promise<ConnectorConfigTestResult> {
  return request<ConnectorConfigTestResult>(`/api/v1/connector-configs/${connectorConfigId}/test`, {
    method: "POST"
  });
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
