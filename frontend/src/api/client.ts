import type {
  Assessment,
  AssessmentCreate,
  AssessmentReport,
  Asset,
  AssetCreate,
  ConnectorConfig,
  ConnectorConfigPayload,
  ConnectorConfigTestResult,
  ConnectorCredentialResult,
  Customer,
  CustomerCreate,
  Finding,
  FindingCreate,
  GmailDelegateChangePreview,
  GmailDelegateList,
  GmailDelegateMutationResult,
  GmailDelegateReconciliationResult,
  GoogleWorkspaceGroup,
  GoogleWorkspaceGroupMemberList,
  GoogleWorkspaceGroupSearchResult,
  GoogleWorkspaceOrganizationalUnit,
  GoogleWorkspaceOrganizationalUnitHierarchy,
  GoogleWorkspaceCheck,
  GoogleWorkspaceUser,
  GoogleWorkspaceUserStatusMutationResult,
  GoogleWorkspaceUserStatusOperation,
  GoogleWorkspaceUserStatusPreview,
  GoogleWorkspaceUserStatusReconciliationResult,
  GoogleWorkspaceUserOrgUnitMovePreview,
  GoogleWorkspaceUserOrgUnitMoveResult,
  GoogleWorkspaceUserOrgUnitMoveReconciliationResult,
  GoogleWorkspaceUserGroupMembershipResult,
  GoogleWorkspaceUserDirectoryRequest,
  GoogleWorkspaceUserDirectoryResult,
  GroupMembershipMutationResult,
  GroupMembershipPreview,
  GroupMembershipReconciliationResult,
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
  code: string | null;
  correlationId: string | null;
  reconciliationAvailable: boolean;

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    options: { correlationId?: string | null; reconciliationAvailable?: boolean } = {}
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.correlationId = options.correlationId ?? null;
    this.reconciliationAvailable = options.reconciliationAvailable ?? false;
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
    const rawDetail = "detail" in errorBody ? errorBody.detail : response.statusText;
    const detail =
      typeof rawDetail === "object" && rawDetail !== null && "message" in rawDetail
        ? String(rawDetail.message)
        : String(rawDetail);
    const code =
      typeof rawDetail === "object" && rawDetail !== null && "code" in rawDetail
        ? String(rawDetail.code)
        : null;
    const correlationId =
      typeof rawDetail === "object" && rawDetail !== null && "correlation_id" in rawDetail
        ? String(rawDetail.correlation_id)
        : null;
    const reconciliationAvailable =
      typeof rawDetail === "object" &&
      rawDetail !== null &&
      "reconciliation_available" in rawDetail &&
      rawDetail.reconciliation_available === true;
    throw new ApiError(detail, response.status, code, {
      correlationId,
      reconciliationAvailable
    });
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

export function importGoogleWorkspaceCredential(
  connectorConfigId: string,
  file: File
): Promise<ConnectorCredentialResult> {
  if (file.size > 65_536) {
    return Promise.reject(new ApiError("Credential file is larger than 64 KiB.", 413));
  }
  return file.text().then((body) =>
    request<ConnectorCredentialResult>(
      `/api/v1/connector-configs/${connectorConfigId}/credentials`,
      { method: "PUT", body }
    )
  );
}

export function selectExternalGoogleWorkspaceCredential(
  connectorConfigId: string,
  credentialRef: string
): Promise<ConnectorCredentialResult> {
  return request<ConnectorCredentialResult>(
    `/api/v1/connector-configs/${connectorConfigId}/credentials/external`,
    {
      method: "PUT",
      body: JSON.stringify({ credential_ref: credentialRef })
    }
  );
}

export function lookupGoogleWorkspaceUser(
  organizationId: string,
  email: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUser> {
  return request<GoogleWorkspaceUser>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/lookup`,
    {
      method: "POST",
      body: JSON.stringify({ email }),
      signal
    }
  );
}

export function previewGoogleWorkspaceUserStatusChange(
  organizationId: string,
  operation: GoogleWorkspaceUserStatusOperation,
  userEmail: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserStatusPreview> {
  return request<GoogleWorkspaceUserStatusPreview>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/${operation}/preview`,
    {
      method: "POST",
      body: JSON.stringify({ user_email: userEmail }),
      signal
    }
  );
}

export function executeGoogleWorkspaceUserStatusChange(
  organizationId: string,
  operation: GoogleWorkspaceUserStatusOperation,
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserStatusMutationResult> {
  return request<GoogleWorkspaceUserStatusMutationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/${operation}`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function reconcileGoogleWorkspaceUserStatusChange(
  organizationId: string,
  operation: GoogleWorkspaceUserStatusOperation,
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserStatusReconciliationResult> {
  return request<GoogleWorkspaceUserStatusReconciliationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/${operation}/reconcile`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function previewGoogleWorkspaceUserOrgUnitMove(
  organizationId: string,
  userId: string,
  destinationOrgUnitId: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserOrgUnitMovePreview> {
  return request<GoogleWorkspaceUserOrgUnitMovePreview>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/orgunit/preview`,
    {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        destination_org_unit_id: destinationOrgUnitId
      }),
      signal
    }
  );
}

export function executeGoogleWorkspaceUserOrgUnitMove(
  organizationId: string,
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserOrgUnitMoveResult> {
  return request<GoogleWorkspaceUserOrgUnitMoveResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/orgunit`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function reconcileGoogleWorkspaceUserOrgUnitMove(
  organizationId: string,
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserOrgUnitMoveReconciliationResult> {
  return request<GoogleWorkspaceUserOrgUnitMoveReconciliationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/orgunit/reconcile`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function listGoogleWorkspaceUsers(
  organizationId: string,
  payload: GoogleWorkspaceUserDirectoryRequest,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserDirectoryResult> {
  return request<GoogleWorkspaceUserDirectoryResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/list`,
    {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    }
  );
}

export function listGoogleWorkspaceOrganizationalUnits(
  organizationId: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceOrganizationalUnitHierarchy> {
  return request<GoogleWorkspaceOrganizationalUnitHierarchy>(
    `/api/v1/organizations/${organizationId}/google-workspace/orgunits/list`,
    { method: "POST", signal }
  );
}

export function getGoogleWorkspaceOrganizationalUnit(
  organizationId: string,
  orgUnitId: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceOrganizationalUnit> {
  return request<GoogleWorkspaceOrganizationalUnit>(
    `/api/v1/organizations/${organizationId}/google-workspace/orgunits/get`,
    {
      method: "POST",
      body: JSON.stringify({ org_unit_id: orgUnitId }),
      signal
    }
  );
}

export function listGmailDelegates(
  organizationId: string,
  ownerEmail: string,
  signal?: AbortSignal
): Promise<GmailDelegateList> {
  return request<GmailDelegateList>(
    `/api/v1/organizations/${organizationId}/google-workspace/gmail-delegates/list`,
    {
      method: "POST",
      body: JSON.stringify({ owner_email: ownerEmail }),
      signal
    }
  );
}

export function previewGmailDelegateChange(
  organizationId: string,
  operation: "create" | "remove",
  ownerEmail: string,
  delegateEmail: string,
  signal?: AbortSignal
): Promise<GmailDelegateChangePreview> {
  return request<GmailDelegateChangePreview>(
    `/api/v1/organizations/${organizationId}/google-workspace/gmail-delegates/${operation}/preview`,
    {
      method: "POST",
      body: JSON.stringify({ owner_email: ownerEmail, delegate_email: delegateEmail }),
      signal
    }
  );
}

export function executeGmailDelegateChange(
  organizationId: string,
  operation: "create" | "remove",
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GmailDelegateMutationResult> {
  return request<GmailDelegateMutationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/gmail-delegates/${operation}`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function reconcileGmailDelegateChange(
  organizationId: string,
  operation: "create" | "remove",
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GmailDelegateReconciliationResult> {
  return request<GmailDelegateReconciliationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/gmail-delegates/${operation}/reconcile`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function searchGoogleWorkspaceGroups(
  organizationId: string,
  query: string,
  pageToken?: string | null,
  signal?: AbortSignal
): Promise<GoogleWorkspaceGroupSearchResult> {
  return request<GoogleWorkspaceGroupSearchResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/groups/search`,
    {
      method: "POST",
      body: JSON.stringify({ query, page_token: pageToken ?? null, max_results: 50 }),
      signal
    }
  );
}

export function getGoogleWorkspaceGroup(
  organizationId: string,
  groupEmail: string,
  signal?: AbortSignal
): Promise<GoogleWorkspaceGroup> {
  return request<GoogleWorkspaceGroup>(
    `/api/v1/organizations/${organizationId}/google-workspace/groups/get`,
    {
      method: "POST",
      body: JSON.stringify({ group_email: groupEmail }),
      signal
    }
  );
}

export function listGoogleWorkspaceUserGroupMemberships(
  organizationId: string,
  email: string,
  pageSize: 10 | 25,
  pageToken?: string | null,
  signal?: AbortSignal
): Promise<GoogleWorkspaceUserGroupMembershipResult> {
  return request<GoogleWorkspaceUserGroupMembershipResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/users/group-memberships`,
    {
      method: "POST",
      body: JSON.stringify({
        email,
        page_size: pageSize,
        page_token: pageToken ?? null
      }),
      signal
    }
  );
}

export function listGoogleWorkspaceGroupMembers(
  organizationId: string,
  groupEmail: string,
  pageToken?: string | null,
  signal?: AbortSignal
): Promise<GoogleWorkspaceGroupMemberList> {
  return request<GoogleWorkspaceGroupMemberList>(
    `/api/v1/organizations/${organizationId}/google-workspace/groups/members/list`,
    {
      method: "POST",
      body: JSON.stringify({
        group_email: groupEmail,
        page_token: pageToken ?? null,
        max_results: 50
      }),
      signal
    }
  );
}

export function previewGroupMembershipChange(
  organizationId: string,
  operation: "add" | "remove",
  groupEmail: string,
  memberEmail: string,
  signal?: AbortSignal
): Promise<GroupMembershipPreview> {
  return request<GroupMembershipPreview>(
    `/api/v1/organizations/${organizationId}/google-workspace/groups/members/${operation}/preview`,
    {
      method: "POST",
      body: JSON.stringify({ group_email: groupEmail, member_email: memberEmail }),
      signal
    }
  );
}

export function executeGroupMembershipChange(
  organizationId: string,
  operation: "add" | "remove",
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GroupMembershipMutationResult> {
  return request<GroupMembershipMutationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/groups/members/${operation}`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
}

export function reconcileGroupMembershipChange(
  organizationId: string,
  operation: "add" | "remove",
  confirmationToken: string,
  signal?: AbortSignal
): Promise<GroupMembershipReconciliationResult> {
  return request<GroupMembershipReconciliationResult>(
    `/api/v1/organizations/${organizationId}/google-workspace/groups/members/${operation}/reconcile`,
    {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      signal
    }
  );
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
