import {
  Activity,
  AlertCircle,
  ArrowLeft,
  BadgeCheck,
  Building2,
  CheckCircle2,
  ClipboardList,
  Database,
  FileText,
  Flag,
  Layers3,
  Link2,
  LockKeyhole,
  LogOut,
  Loader2,
  Plus,
  Printer,
  ShieldAlert,
  Target,
  TrendingUp,
  Users
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  clearStoredAuthToken,
  createAssessment,
  createAsset,
  createCustomer,
  createFinding,
  createOrganization,
  getAssessmentReport,
  getCurrentUser,
  getPlatformAdminOverview,
  getStoredAuthToken,
  listAssessmentScanRuns,
  listAssessments,
  listAssets,
  listCustomers,
  listFindings,
  listGoogleWorkspaceChecks,
  listOrganizationConnectorConfigs,
  listOrganizations,
  login,
  runMockGoogleWorkspaceScan,
  setStoredAuthToken,
  testConnectorConfig,
  upsertGoogleWorkspaceConnectorConfig
} from "./api/client";
import type {
  Assessment,
  AssessmentReport,
  Asset,
  ConnectorAuthMethod,
  ConnectorConfig,
  Customer,
  DreadScoreCreate,
  Finding,
  FindingCreate,
  GoogleWorkspaceCheck,
  Organization,
  PlatformAdminOverview,
  ScanRun,
  User
} from "./types";

type DreadScoreKey = keyof DreadScoreCreate;
type Feedback = { type: "success" | "error"; message: string } | null;
type SavingTarget = "customer" | "organization" | "assessment" | "asset" | "finding" | null;
type ActiveSection =
  | "dashboard"
  | "customers"
  | "organizations"
  | "assessment"
  | "google-workspace"
  | "platform-admin"
  | "reports";

const initialDreadScore: DreadScoreCreate = {
  damage: 5,
  reproducibility: 5,
  exploitability: 5,
  affected_users: 5,
  discoverability: 5
};

const dreadControls: Array<{ key: DreadScoreKey; label: string; hint: string }> = [
  { key: "damage", label: "Damage", hint: "Impact op business of data" },
  { key: "reproducibility", label: "Reproducibility", hint: "Hoe vaak reproduceerbaar" },
  { key: "exploitability", label: "Exploitability", hint: "Moeite om uit te buiten" },
  { key: "affected_users", label: "Affected users", hint: "Bereik van impact" },
  { key: "discoverability", label: "Discoverability", hint: "Hoe makkelijk te vinden" }
];

const connectorAuthMethodLabels: Record<ConnectorAuthMethod, string> = {
  service_account_domain_wide_delegation: "Service account + domain-wide delegation",
  oauth_admin_consent: "OAuth admin consent",
  manual_import: "Manual import"
};

function riskLevelFromScore(score: number): "Low" | "Medium" | "High" | "Critical" {
  if (score < 3) {
    return "Low";
  }
  if (score < 6) {
    return "Medium";
  }
  if (score < 8) {
    return "High";
  }
  return "Critical";
}

function formatScore(score: number | null): string {
  return score === null ? "-" : score.toFixed(2);
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("nl-NL", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatOptionalDateTime(value: string | null): string {
  return value ? formatDateTime(value) : "Nog niet getest";
}

function formatNullableDateTime(value: string | null): string {
  return value ? formatDateTime(value) : "-";
}

function buildExecutiveSummary(report: AssessmentReport): string {
  if (report.total_findings === 0) {
    return "Dit assessment heeft nog geen findings. Voeg findings toe om risico's en DREAD-scores zichtbaar te maken.";
  }

  return `Dit assessment bevat ${report.total_findings} finding${
    report.total_findings === 1 ? "" : "s"
  }. Het hoogste risico is ${report.highest_risk_level ?? "onbekend"} en de gemiddelde DREAD-score is ${formatScore(
    report.average_score
  )}.`;
}

function averageDreadScore(score: DreadScoreCreate): number {
  return Object.values(score).reduce((sum, value) => sum + value, 0) / 5;
}

function App() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [googleWorkspaceChecks, setGoogleWorkspaceChecks] = useState<GoogleWorkspaceCheck[]>([]);
  const [connectorConfigs, setConnectorConfigs] = useState<ConnectorConfig[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [selectedAssessmentId, setSelectedAssessmentId] = useState("");
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerSlug, setCustomerSlug] = useState("");
  const [customerContactName, setCustomerContactName] = useState("");
  const [customerContactEmail, setCustomerContactEmail] = useState("");
  const [customerStatus, setCustomerStatus] = useState("active");
  const [customerNotes, setCustomerNotes] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [organizationDescription, setOrganizationDescription] = useState("");
  const [assessmentTitle, setAssessmentTitle] = useState("");
  const [assessmentScope, setAssessmentScope] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetType, setAssetType] = useState("saas");
  const [assetIdentifier, setAssetIdentifier] = useState("");
  const [findingTitle, setFindingTitle] = useState("");
  const [findingDescription, setFindingDescription] = useState("");
  const [findingMitigation, setFindingMitigation] = useState("");
  const [dreadScore, setDreadScore] = useState<DreadScoreCreate>(initialDreadScore);
  const [connectorDisplayName, setConnectorDisplayName] = useState("Google Workspace");
  const [connectorPrimaryDomain, setConnectorPrimaryDomain] = useState("");
  const [connectorAdminSubjectEmail, setConnectorAdminSubjectEmail] = useState("");
  const [connectorAuthMethod, setConnectorAuthMethod] = useState<ConnectorAuthMethod>(
    "service_account_domain_wide_delegation"
  );
  const [connectorNotes, setConnectorNotes] = useState("");
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [connectorFeedback, setConnectorFeedback] = useState<Feedback>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [isLoginSaving, setIsLoginSaving] = useState(false);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [isScanLoading, setIsScanLoading] = useState(false);
  const [isScanRunning, setIsScanRunning] = useState(false);
  const [isConnectorSaving, setIsConnectorSaving] = useState(false);
  const [isConnectorTesting, setIsConnectorTesting] = useState(false);
  const [showGoogleWorkspaceChecks, setShowGoogleWorkspaceChecks] = useState(false);
  const [saving, setSaving] = useState<SavingTarget>(null);
  const [activeSection, setActiveSection] = useState<ActiveSection>("dashboard");
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [platformAdminOverview, setPlatformAdminOverview] =
    useState<PlatformAdminOverview | null>(null);
  const [isPlatformAdminOverviewLoading, setIsPlatformAdminOverviewLoading] = useState(false);

  const customerById = useMemo(
    () => new Map(customers.map((customer) => [customer.id, customer])),
    [customers]
  );
  const selectedCustomer = useMemo(
    () => customers.find((customer) => customer.id === selectedCustomerId),
    [customers, selectedCustomerId]
  );
  const visibleOrganizations = useMemo(
    () =>
      selectedCustomerId
        ? organizations.filter((organization) => organization.customer_id === selectedCustomerId)
        : organizations,
    [organizations, selectedCustomerId]
  );
  const selectedOrganization = useMemo(
    () => organizations.find((organization) => organization.id === selectedOrganizationId),
    [organizations, selectedOrganizationId]
  );
  const selectedOrganizationCustomer = useMemo(
    () =>
      selectedOrganization?.customer_id ? customerById.get(selectedOrganization.customer_id) : null,
    [customerById, selectedOrganization]
  );
  const organizationAssessments = useMemo(
    () => assessments.filter((assessment) => assessment.organization_id === selectedOrganizationId),
    [assessments, selectedOrganizationId]
  );
  const organizationAssets = useMemo(
    () => assets.filter((asset) => asset.organization_id === selectedOrganizationId),
    [assets, selectedOrganizationId]
  );
  const selectedAssessment = useMemo(
    () => assessments.find((assessment) => assessment.id === selectedAssessmentId),
    [assessments, selectedAssessmentId]
  );
  const assessmentFindings = useMemo(
    () => findings.filter((finding) => finding.assessment_id === selectedAssessmentId),
    [findings, selectedAssessmentId]
  );
  const googleWorkspaceConnectorConfig = useMemo(
    () =>
      connectorConfigs.find(
        (connectorConfig) =>
          connectorConfig.organization_id === selectedOrganizationId &&
          connectorConfig.connector_type === "google_workspace"
      ) ?? null,
    [connectorConfigs, selectedOrganizationId]
  );
  const assetById = useMemo(
    () => new Map(assets.map((asset) => [asset.id, asset])),
    [assets]
  );
  const reportAssetById = useMemo(
    () => new Map((report?.assets ?? []).map((asset) => [asset.id, asset])),
    [report]
  );

  const previewScore = useMemo(() => {
    const total = Object.values(dreadScore).reduce((sum, value) => sum + value, 0);
    return total / 5;
  }, [dreadScore]);
  const previewRiskLevel = riskLevelFromScore(previewScore);

  const averageRiskScore = useMemo(() => {
    if (assessmentFindings.length === 0) {
      return null;
    }

    const total = assessmentFindings.reduce(
      (sum, finding) => sum + finding.dread_score.total_score,
      0
    );
    return total / assessmentFindings.length;
  }, [assessmentFindings]);

  const highestFinding = useMemo(() => {
    if (assessmentFindings.length === 0) {
      return null;
    }

    return assessmentFindings.reduce((highest, finding) =>
      finding.dread_score.total_score > highest.dread_score.total_score ? finding : highest
    );
  }, [assessmentFindings]);

  const canCreateCustomer = Boolean(customerName.trim() && customerSlug.trim());
  const canCreateAssessment = Boolean(selectedOrganizationId && assessmentTitle.trim());
  const canCreateAsset = Boolean(selectedOrganizationId && assetName.trim());
  const canCreateFinding = Boolean(selectedAssessmentId && findingTitle.trim());
  const canSaveConnectorConfig = Boolean(selectedOrganizationId && connectorDisplayName.trim());
  const canViewPlatformAdmin =
    currentUser?.role === "platform_admin" || currentUser?.role === "platform_support";

  const resetSession = useCallback((message?: string) => {
    clearStoredAuthToken();
    setCurrentUser(null);
    setReport(null);
    setActiveSection("dashboard");
    setCustomers([]);
    setOrganizations([]);
    setAssessments([]);
    setAssets([]);
    setFindings([]);
    setScanRuns([]);
    setGoogleWorkspaceChecks([]);
    setConnectorConfigs([]);
    setPlatformAdminOverview(null);
    setConnectorFeedback(null);
    setSelectedCustomerId("");
    setSelectedOrganizationId("");
    setSelectedAssessmentId("");
    setSelectedAssetId("");
    setIsLoading(false);
    if (message) {
      setFeedback({ type: "error", message });
    }
  }, []);

  const handleRequestError = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.status === 401) {
        resetSession("Sessie verlopen of ongeldig. Log opnieuw in.");
        return;
      }

      setFeedback({ type: "error", message: (error as Error).message });
    },
    [resetSession]
  );

  const loadOrganizationConnectorConfigs = useCallback(
    async (organizationId: string) => {
      if (!organizationId) {
        setConnectorConfigs([]);
        return;
      }

      try {
        const loadedConnectorConfigs = await listOrganizationConnectorConfigs(organizationId);
        setConnectorConfigs(loadedConnectorConfigs);
      } catch (connectorError) {
        handleRequestError(connectorError);
      }
    },
    [handleRequestError]
  );

  const loadAssessmentScanRuns = useCallback(
    async (assessmentId: string) => {
      if (!assessmentId) {
        setScanRuns([]);
        return;
      }

      setIsScanLoading(true);
      try {
        const loadedScanRuns = await listAssessmentScanRuns(assessmentId);
        setScanRuns(loadedScanRuns);
      } catch (scanError) {
        handleRequestError(scanError);
      } finally {
        setIsScanLoading(false);
      }
    },
    [handleRequestError]
  );

  const loadPlatformAdminOverview = useCallback(async () => {
    if (!canViewPlatformAdmin) {
      setPlatformAdminOverview(null);
      return;
    }

    setIsPlatformAdminOverviewLoading(true);
    try {
      const loadedOverview = await getPlatformAdminOverview();
      setPlatformAdminOverview(loadedOverview);
    } catch (overviewError) {
      handleRequestError(overviewError);
    } finally {
      setIsPlatformAdminOverviewLoading(false);
    }
  }, [canViewPlatformAdmin, handleRequestError]);

  const loadWorkspace = useCallback(
    async (
      preferredCustomerId?: string,
      preferredOrganizationId?: string,
      preferredAssessmentId?: string
    ) => {
      setIsLoading(true);
      try {
        const [
          loadedCustomers,
          loadedOrganizations,
          loadedAssessments,
          loadedAssets,
          loadedFindings,
          loadedGoogleWorkspaceChecks
        ] = await Promise.all([
          listCustomers(),
          listOrganizations(),
          listAssessments(),
          listAssets(),
          listFindings(),
          listGoogleWorkspaceChecks()
        ]);

        setCustomers(loadedCustomers);
        setOrganizations(loadedOrganizations);
        setAssessments(loadedAssessments);
        setAssets(loadedAssets);
        setFindings(loadedFindings);
        setGoogleWorkspaceChecks(loadedGoogleWorkspaceChecks);

        const nextCustomerId = preferredCustomerId ?? selectedCustomerId;
        const organizationOptions = nextCustomerId
          ? loadedOrganizations.filter((organization) => organization.customer_id === nextCustomerId)
          : loadedOrganizations;
        const preferredOrganization = preferredOrganizationId
          ? loadedOrganizations.find((organization) => organization.id === preferredOrganizationId)
          : null;
        const canUsePreferredOrganization =
          preferredOrganization &&
          (!nextCustomerId || preferredOrganization.customer_id === nextCustomerId);
        const nextOrganizationId =
          (canUsePreferredOrganization ? preferredOrganization.id : null) ??
          organizationOptions[0]?.id ??
          loadedOrganizations[0]?.id ??
          "";
        const nextAssessmentId =
          preferredAssessmentId ??
          loadedAssessments.find((assessment) => assessment.organization_id === nextOrganizationId)
            ?.id ??
          "";

        setSelectedCustomerId(nextCustomerId);
        setSelectedOrganizationId(nextOrganizationId);
        setSelectedAssessmentId(nextAssessmentId);
      } catch (loadError) {
        handleRequestError(loadError);
      } finally {
        setIsLoading(false);
      }
    },
    [handleRequestError, selectedCustomerId]
  );

  useEffect(() => {
    async function restoreSession() {
      const token = getStoredAuthToken();
      if (!token) {
        setIsAuthLoading(false);
        setIsLoading(false);
        return;
      }

      try {
        const user = await getCurrentUser();
        setCurrentUser(user);
        await loadWorkspace();
      } catch (authError) {
        handleRequestError(authError);
      } finally {
        setIsAuthLoading(false);
      }
    }

    restoreSession();
  }, [handleRequestError, loadWorkspace]);

  useEffect(() => {
    if (!selectedCustomerId) {
      return;
    }

    if (!visibleOrganizations.some((organization) => organization.id === selectedOrganizationId)) {
      setSelectedOrganizationId(visibleOrganizations[0]?.id ?? "");
    }
  }, [selectedCustomerId, selectedOrganizationId, visibleOrganizations]);

  useEffect(() => {
    if (!selectedOrganizationId) {
      setSelectedAssessmentId("");
      setSelectedAssetId("");
      setScanRuns([]);
      setConnectorConfigs([]);
      return;
    }

    if (!organizationAssessments.some((assessment) => assessment.id === selectedAssessmentId)) {
      setSelectedAssessmentId(organizationAssessments[0]?.id ?? "");
    }

    if (!organizationAssets.some((asset) => asset.id === selectedAssetId)) {
      setSelectedAssetId("");
    }
  }, [
    organizationAssessments,
    organizationAssets,
    selectedAssessmentId,
    selectedAssetId,
    selectedOrganizationId
  ]);

  useEffect(() => {
    if (!currentUser || !selectedAssessmentId) {
      setScanRuns([]);
      return;
    }

    loadAssessmentScanRuns(selectedAssessmentId);
  }, [currentUser, loadAssessmentScanRuns, selectedAssessmentId]);

  useEffect(() => {
    if (!currentUser || !selectedOrganizationId) {
      setConnectorConfigs([]);
      return;
    }

    loadOrganizationConnectorConfigs(selectedOrganizationId);
  }, [currentUser, loadOrganizationConnectorConfigs, selectedOrganizationId]);

  useEffect(() => {
    if (!currentUser || !canViewPlatformAdmin) {
      setPlatformAdminOverview(null);
      if (activeSection === "platform-admin") {
        setActiveSection("dashboard");
      }
      return;
    }

    if (activeSection === "platform-admin") {
      loadPlatformAdminOverview();
    }
  }, [activeSection, canViewPlatformAdmin, currentUser, loadPlatformAdminOverview]);

  useEffect(() => {
    if (!googleWorkspaceConnectorConfig) {
      setConnectorDisplayName("Google Workspace");
      setConnectorPrimaryDomain("");
      setConnectorAdminSubjectEmail("");
      setConnectorAuthMethod("service_account_domain_wide_delegation");
      setConnectorNotes("");
      return;
    }

    setConnectorDisplayName(googleWorkspaceConnectorConfig.display_name);
    setConnectorPrimaryDomain(googleWorkspaceConnectorConfig.primary_domain ?? "");
    setConnectorAdminSubjectEmail(googleWorkspaceConnectorConfig.admin_subject_email ?? "");
    setConnectorAuthMethod(googleWorkspaceConnectorConfig.auth_method);
    setConnectorNotes(googleWorkspaceConnectorConfig.notes ?? "");
  }, [googleWorkspaceConnectorConfig]);

  async function handleCreateCustomer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreateCustomer) {
      return;
    }

    setFeedback(null);
    setSaving("customer");
    try {
      const customer = await createCustomer({
        name: customerName.trim(),
        slug: customerSlug.trim(),
        contact_name: customerContactName.trim() || null,
        contact_email: customerContactEmail.trim() || null,
        status: customerStatus,
        notes: customerNotes.trim() || null
      });
      setCustomerName("");
      setCustomerSlug("");
      setCustomerContactName("");
      setCustomerContactEmail("");
      setCustomerStatus("active");
      setCustomerNotes("");
      setSelectedCustomerId(customer.id);
      setFeedback({ type: "success", message: "Customer aangemaakt." });
      await loadWorkspace(customer.id);
    } catch (submitError) {
      handleRequestError(submitError);
    } finally {
      setSaving(null);
    }
  }

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = organizationName.trim();
    if (!name) {
      return;
    }

    setFeedback(null);
    setSaving("organization");
    try {
      const organization = await createOrganization({
        name,
        description: organizationDescription.trim() || null,
        customer_id: selectedCustomerId || null
      });
      setOrganizationName("");
      setOrganizationDescription("");
      setSelectedOrganizationId(organization.id);
      setFeedback({ type: "success", message: "Organisatie aangemaakt." });
      await loadWorkspace(selectedCustomerId, organization.id);
    } catch (submitError) {
      handleRequestError(submitError);
    } finally {
      setSaving(null);
    }
  }

  async function handleCreateAssessment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreateAssessment) {
      return;
    }

    setFeedback(null);
    setSaving("assessment");
    try {
      const assessment = await createAssessment({
        organization_id: selectedOrganizationId,
        title: assessmentTitle.trim(),
        scope_summary: assessmentScope.trim() || null
      });
      setAssessmentTitle("");
      setAssessmentScope("");
      setSelectedAssessmentId(assessment.id);
      setFeedback({ type: "success", message: "Assessment aangemaakt." });
      await loadWorkspace(selectedCustomerId, selectedOrganizationId, assessment.id);
    } catch (submitError) {
      handleRequestError(submitError);
    } finally {
      setSaving(null);
    }
  }

  async function handleCreateAsset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreateAsset) {
      return;
    }

    setFeedback(null);
    setSaving("asset");
    try {
      const asset = await createAsset({
        organization_id: selectedOrganizationId,
        name: assetName.trim(),
        asset_type: assetType,
        identifier: assetIdentifier.trim() || null,
        description: null
      });
      setAssetName("");
      setAssetIdentifier("");
      setSelectedAssetId(asset.id);
      setFeedback({ type: "success", message: "Asset toegevoegd." });
      await loadWorkspace(selectedCustomerId, selectedOrganizationId, selectedAssessmentId);
      setSelectedAssetId(asset.id);
    } catch (submitError) {
      handleRequestError(submitError);
    } finally {
      setSaving(null);
    }
  }

  async function handleCreateFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreateFinding) {
      return;
    }

    const payload: FindingCreate = {
      assessment_id: selectedAssessmentId,
      asset_id: selectedAssetId || null,
      title: findingTitle.trim(),
      description: findingDescription.trim() || null,
      status: "open",
      mitigation: findingMitigation.trim() || null,
      dread_score: dreadScore
    };

    setFeedback(null);
    setSaving("finding");
    try {
      await createFinding(payload);
      setFindingTitle("");
      setFindingDescription("");
      setFindingMitigation("");
      setDreadScore(initialDreadScore);
      setFeedback({ type: "success", message: "Finding toegevoegd en DREAD-score berekend." });
      await loadWorkspace(selectedCustomerId, selectedOrganizationId, selectedAssessmentId);
    } catch (submitError) {
      handleRequestError(submitError);
    } finally {
      setSaving(null);
    }
  }

  async function handleRunMockGoogleWorkspaceScan() {
    if (!selectedAssessmentId) {
      return;
    }

    setFeedback(null);
    setIsScanRunning(true);
    try {
      const scanRun = await runMockGoogleWorkspaceScan(selectedAssessmentId);
      if (scanRun.status === "failed") {
        setFeedback({
          type: "error",
          message: scanRun.summary ?? "Mock Google Workspace scan is mislukt."
        });
      } else {
        setFeedback({
          type: "success",
          message: `Mock Google Workspace scan klaar: ${scanRun.findings_created} findings aangemaakt.`
        });
      }
      await loadWorkspace(selectedCustomerId, selectedOrganizationId, selectedAssessmentId);
      await loadAssessmentScanRuns(selectedAssessmentId);
    } catch (scanError) {
      handleRequestError(scanError);
    } finally {
      setIsScanRunning(false);
    }
  }

  async function handleSaveConnectorConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSaveConnectorConfig) {
      return;
    }

    setFeedback(null);
    setConnectorFeedback(null);
    setIsConnectorSaving(true);
    try {
      const savedConnectorConfig = await upsertGoogleWorkspaceConnectorConfig(
        selectedOrganizationId,
        {
          display_name: connectorDisplayName.trim(),
          primary_domain: connectorPrimaryDomain.trim() || null,
          admin_subject_email: connectorAdminSubjectEmail.trim() || null,
          auth_method: connectorAuthMethod,
          status: "configured",
          notes: connectorNotes.trim() || null
        }
      );
      setConnectorConfigs((current) => {
        const otherConfigs = current.filter((item) => item.id !== savedConnectorConfig.id);
        return [savedConnectorConfig, ...otherConfigs];
      });
      setConnectorFeedback({
        type: "success",
        message: "Google Workspace connectorconfiguratie opgeslagen."
      });
    } catch (connectorError) {
      if (connectorError instanceof ApiError && connectorError.status === 401) {
        handleRequestError(connectorError);
      } else {
        setConnectorFeedback({ type: "error", message: (connectorError as Error).message });
      }
    } finally {
      setIsConnectorSaving(false);
    }
  }

  async function handleTestConnectorConfig() {
    if (!googleWorkspaceConnectorConfig) {
      return;
    }

    setFeedback(null);
    setConnectorFeedback(null);
    setIsConnectorTesting(true);
    try {
      const testResult = await testConnectorConfig(googleWorkspaceConnectorConfig.id);
      setConnectorFeedback({
        type: "success",
        message: `${testResult.message} ${testResult.recommended_next_step}`
      });
      await loadOrganizationConnectorConfigs(selectedOrganizationId);
    } catch (connectorError) {
      if (connectorError instanceof ApiError && connectorError.status === 401) {
        handleRequestError(connectorError);
      } else {
        setConnectorFeedback({ type: "error", message: (connectorError as Error).message });
      }
    } finally {
      setIsConnectorTesting(false);
    }
  }

  function updateFindingScore(key: DreadScoreKey, value: number) {
    setDreadScore((current) => ({ ...current, [key]: value }));
  }

  function renderButtonLabel(target: Exclude<SavingTarget, null>, label: string) {
    if (saving !== target) {
      return label;
    }

    return (
      <>
        <Loader2 className="spin" aria-hidden="true" />
        Opslaan
      </>
    );
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setFeedback(null);
    setIsLoginSaving(true);
    try {
      const tokenResponse = await login({
        email: loginEmail.trim(),
        password: loginPassword
      });
      setStoredAuthToken(tokenResponse.access_token);
      const user = await getCurrentUser();
      setCurrentUser(user);
      setFeedback({ type: "success", message: "Ingelogd." });
      await loadWorkspace();
    } catch (loginError) {
      clearStoredAuthToken();
      setCurrentUser(null);
      setFeedback({ type: "error", message: (loginError as Error).message });
    } finally {
      setIsLoginSaving(false);
      setIsAuthLoading(false);
    }
  }

  function handleLogout(message = "Uitgelogd.") {
    resetSession();
    setLoginPassword("");
    setFeedback({ type: "success", message });
  }

  async function handleOpenReport() {
    if (!selectedAssessmentId) {
      return;
    }

    setFeedback(null);
    setIsReportLoading(true);
    try {
      const loadedReport = await getAssessmentReport(selectedAssessmentId);
      setReport(loadedReport);
      setActiveSection("reports");
    } catch (reportError) {
      handleRequestError(reportError);
    } finally {
      setIsReportLoading(false);
    }
  }

  function handleBackToWorkspace() {
    setActiveSection("assessment");
  }

  function handlePrintReport() {
    window.print();
  }

  const activeOrganizationLabel = isLoading
    ? "Data laden"
    : selectedOrganization?.name ?? "Geen organisatie geselecteerd";
  const activeCustomerLabel = isLoading
    ? "Data laden"
    : selectedCustomer?.name ?? selectedOrganizationCustomer?.name ?? "Geen customer geselecteerd";
  const activeSectionMeta: Record<ActiveSection, { title: string; description: string }> = {
    dashboard: {
      title: "Dashboard",
      description: "Samenvatting van de actieve klantorganisatie, assessment en risico's."
    },
    customers: {
      title: "Customer context",
      description: "Platform/customer context for this MVP. Nog geen volledig admin-model."
    },
    organizations: {
      title: "Organizations",
      description: "Maak organisaties aan en controleer de koppeling met de actieve customer."
    },
    assessment: {
      title: "Assessment workspace",
      description: "Maak assessments, assets en findings aan en vul DREAD-scores in."
    },
    "google-workspace": {
      title: "Google Workspace",
      description: "Beheer connector metadata, check catalog en mock scans zonder echte Google data."
    },
    "platform-admin": {
      title: "Platform Admin",
      description: "Read-only support en troubleshooting overzicht voor platformrollen."
    },
    reports: {
      title: "Reports",
      description: "Open het rapport voor het actieve assessment en print of sla het op als PDF."
    }
  };
  const recommendedNextStep: { message: string; buttonLabel: string; target: ActiveSection } =
    !selectedCustomerId
      ? {
          message: "Selecteer of maak een customer aan.",
          buttonLabel: "Customer context openen",
          target: "customers"
        }
      : !selectedOrganizationId
        ? {
            message: "Selecteer of maak een organisatie aan.",
            buttonLabel: "Organizations openen",
            target: "organizations"
          }
        : !selectedAssessmentId
          ? {
              message: "Maak of open een assessment.",
              buttonLabel: "Assessment workspace openen",
              target: "assessment"
            }
          : assessmentFindings.length === 0
            ? {
                message: "Start een Google Workspace mock scan of voeg handmatig een finding toe.",
                buttonLabel: "Google Workspace openen",
                target: "google-workspace"
              }
            : {
                message: "Open het rapport of beoordeel de findings.",
                buttonLabel: "Reports openen",
                target: "reports"
              };
  const sectionClass = (section: ActiveSection, extraClass = "") =>
    `section-view ${activeSection === section ? "active" : ""} ${extraClass}`.trim();

  if (isAuthLoading) {
    return (
      <main className="app-shell login-shell">
        <section className="login-panel">
          <LockKeyhole aria-hidden="true" />
          <h1>AdminDeck</h1>
          <p>Authenticatie controleren.</p>
          <div className="login-loading">
            <Loader2 className="spin" aria-hidden="true" />
            Sessie laden
          </div>
        </section>
      </main>
    );
  }

  if (!currentUser) {
    return (
      <main className="app-shell login-shell">
        <section className="login-panel">
          <LockKeyhole aria-hidden="true" />
          <span className="eyebrow">Development login</span>
          <h1>AdminDeck</h1>
          <p>
            Gebruik het lokaal geconfigureerde development-account om de MVP auth foundation te
            testen. Dit is geen productie-authenticatie.
          </p>

          {feedback && (
            <section className={`message ${feedback.type}`} aria-live="polite">
              {feedback.type === "error" ? (
                <AlertCircle aria-hidden="true" />
              ) : (
                <CheckCircle2 aria-hidden="true" />
              )}
              <span>{feedback.message}</span>
            </section>
          )}

          <form className="login-form" onSubmit={handleLogin}>
            <label>
              Email
              <input
                value={loginEmail}
                onChange={(event) => setLoginEmail(event.target.value)}
                placeholder="admin@example.local"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={loginPassword}
                onChange={(event) => setLoginPassword(event.target.value)}
                placeholder="Password"
                autoComplete="current-password"
                required
              />
            </label>
            <button type="submit" disabled={!loginEmail.trim() || !loginPassword || isLoginSaving}>
              {isLoginSaving ? (
                <Loader2 className="spin" aria-hidden="true" />
              ) : (
                <LockKeyhole aria-hidden="true" />
              )}
              Inloggen
            </button>
          </form>

        </section>
      </main>
    );
  }

  const reportPanel = (
    <>
        <section className="report-page">
          <div className="report-toolbar no-print">
            <button type="button" className="secondary-button" onClick={handleBackToWorkspace}>
              <ArrowLeft aria-hidden="true" />
              Terug naar assessment
            </button>
            <button type="button" onClick={handlePrintReport} disabled={!report}>
              <Printer aria-hidden="true" />
              Print / opslaan als PDF
            </button>
          </div>

          {!report ? (
            <div className="empty-state">
              <FileText aria-hidden="true" />
              <h3>Geen rapport geopend</h3>
              <p>Open eerst het rapport voor het actieve assessment.</p>
            </div>
          ) : (
            <>
              <header className="report-header">
                <div>
                  <span className="eyebrow">Assessment export</span>
                  <h1>AdminDeck DREAD Risk Assessment Report</h1>
                  <p>{buildExecutiveSummary(report)}</p>
                </div>
                {report.highest_risk_level ? (
                  <span className={`risk-badge risk-${report.highest_risk_level.toLowerCase()}`}>
                    {report.highest_risk_level}
                  </span>
                ) : (
                  <span className="risk-badge risk-neutral">Geen findings</span>
                )}
              </header>

              <section className="report-meta-grid" aria-label="Rapport metadata">
                <article>
                  <span>Organization</span>
                  <strong>{report.organization.name}</strong>
                </article>
                <article>
                  <span>Assessment naam</span>
                  <strong>{report.assessment.title}</strong>
                </article>
                <article>
                  <span>Status</span>
                  <strong>{report.assessment.status}</strong>
                </article>
                <article>
                  <span>Datum</span>
                  <strong>{formatDateTime(report.generated_at)}</strong>
                </article>
              </section>

              <section className="report-section">
                <div className="report-section-heading">
                  <h2>Executive summary</h2>
                  <p>{buildExecutiveSummary(report)}</p>
                </div>
                <div className="report-summary-grid">
                  <article>
                    <span>Aantal findings</span>
                    <strong>{report.total_findings}</strong>
                  </article>
                  <article>
                    <span>Hoogste risico</span>
                    <strong>{report.highest_risk_level ?? "-"}</strong>
                  </article>
                  <article>
                    <span>Gemiddelde score</span>
                    <strong>{formatScore(report.average_score)}</strong>
                  </article>
                </div>
              </section>

              <section className="report-section">
                <div className="report-section-heading">
                  <h2>Risk overview</h2>
                  <p>Verdeling van findings per DREAD risk level.</p>
                </div>
                <div className="risk-overview-grid">
                  <article>
                    <span className="risk-badge risk-low">Low</span>
                    <strong>{report.findings_per_risk_level.low}</strong>
                  </article>
                  <article>
                    <span className="risk-badge risk-medium">Medium</span>
                    <strong>{report.findings_per_risk_level.medium}</strong>
                  </article>
                  <article>
                    <span className="risk-badge risk-high">High</span>
                    <strong>{report.findings_per_risk_level.high}</strong>
                  </article>
                  <article>
                    <span className="risk-badge risk-critical">Critical</span>
                    <strong>{report.findings_per_risk_level.critical}</strong>
                  </article>
                  <article>
                    <span>Gemiddelde score</span>
                    <strong>{formatScore(report.average_score)}</strong>
                  </article>
                  <article>
                    <span>Hoogste score</span>
                    <strong>{formatScore(report.highest_score)}</strong>
                  </article>
                </div>
              </section>

              <section className="report-section">
                <div className="report-section-heading">
                  <h2>Findings tabel</h2>
                  <p>{report.assessment.title}</p>
                </div>
                {report.findings.length === 0 ? (
                  <div className="report-empty-state">
                    <Layers3 aria-hidden="true" />
                    <h3>Nog geen findings in dit assessment.</h3>
                  </div>
                ) : (
                  <div className="report-table-wrap">
                    <table className="report-table">
                      <thead>
                        <tr>
                          <th>Titel</th>
                          <th>Asset</th>
                          <th>Risk level</th>
                          <th>Total score</th>
                          <th>Damage</th>
                          <th>Reproducibility</th>
                          <th>Exploitability</th>
                          <th>Affected users</th>
                          <th>Discoverability</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.findings.map((finding) => {
                          const asset = finding.asset_id ? reportAssetById.get(finding.asset_id) : null;
                          return (
                            <tr key={finding.id}>
                              <td>{finding.title}</td>
                              <td>{asset?.name ?? "Niet gekoppeld"}</td>
                              <td>
                                <span className={`risk-badge risk-${finding.dread_score.risk_level.toLowerCase()}`}>
                                  {finding.dread_score.risk_level}
                                </span>
                              </td>
                              <td>{finding.dread_score.total_score.toFixed(2)}</td>
                              <td>{finding.dread_score.damage}</td>
                              <td>{finding.dread_score.reproducibility}</td>
                              <td>{finding.dread_score.exploitability}</td>
                              <td>{finding.dread_score.affected_users}</td>
                              <td>{finding.dread_score.discoverability}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {report.findings.length > 0 && (
                <section className="report-section">
                  <div className="report-section-heading">
                    <h2>Finding details</h2>
                    <p>Beschrijving, impact en aanbevolen mitigatie per finding.</p>
                  </div>
                  <div className="finding-detail-list">
                    {report.findings.map((finding) => {
                      const asset = finding.asset_id ? reportAssetById.get(finding.asset_id) : null;
                      return (
                        <article className="finding-detail-card" key={finding.id}>
                          <div className="finding-detail-heading">
                            <div>
                              <h3>{finding.title}</h3>
                              <p>{asset?.name ?? "Geen asset gekoppeld"}</p>
                            </div>
                            <span className={`risk-badge risk-${finding.dread_score.risk_level.toLowerCase()}`}>
                              {finding.dread_score.risk_level}
                            </span>
                          </div>
                          <dl>
                            <div>
                              <dt>Beschrijving</dt>
                              <dd>{finding.description ?? "Geen beschrijving opgegeven."}</dd>
                            </div>
                            <div>
                              <dt>Impact</dt>
                              <dd>Damage score {finding.dread_score.damage}/10</dd>
                            </div>
                            <div>
                              <dt>Recommendation / mitigation</dt>
                              <dd>{finding.mitigation ?? "Nog geen mitigatie vastgelegd."}</dd>
                            </div>
                          </dl>
                          <div className="dread-breakdown">
                            {dreadControls.map((control) => (
                              <span key={control.key}>
                                {control.label}
                                <strong>{finding.dread_score[control.key]}</strong>
                              </span>
                            ))}
                            <span>
                              Total
                              <strong>{finding.dread_score.total_score.toFixed(2)}</strong>
                            </span>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              )}
            </>
          )}
        </section>

        {isReportLoading && (
          <div className="loading-overlay no-print" aria-live="polite">
            <Activity className="spin" aria-hidden="true" />
            Rapport laden
          </div>
        )}
    </>
  );

  return (
    <main className="app-shell nav-app-shell">
      <aside className="app-sidebar no-print" aria-label="Hoofdnavigatie">
        <div className="sidebar-brand">
          <ShieldAlert aria-hidden="true" />
          <div>
            <strong>AdminDeck</strong>
            <span>Admin &amp; security ops</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button
            type="button"
            className={activeSection === "dashboard" ? "active" : ""}
            onClick={() => setActiveSection("dashboard")}
          >
            <Activity aria-hidden="true" />
            Dashboard
          </button>
          <button
            type="button"
            className={activeSection === "customers" ? "active" : ""}
            onClick={() => setActiveSection("customers")}
          >
            <Users aria-hidden="true" />
            Customer context
          </button>
          <button
            type="button"
            className={activeSection === "organizations" ? "active" : ""}
            onClick={() => setActiveSection("organizations")}
          >
            <Building2 aria-hidden="true" />
            Organizations
          </button>
          <button
            type="button"
            className={activeSection === "assessment" ? "active" : ""}
            onClick={() => setActiveSection("assessment")}
          >
            <ClipboardList aria-hidden="true" />
            Assessment workspace
          </button>
          <button
            type="button"
            className={activeSection === "google-workspace" ? "active" : ""}
            onClick={() => setActiveSection("google-workspace")}
          >
            <ShieldAlert aria-hidden="true" />
            Google Workspace
          </button>
          {canViewPlatformAdmin && (
            <button
              type="button"
              className={activeSection === "platform-admin" ? "active" : ""}
              onClick={() => setActiveSection("platform-admin")}
            >
              <Database aria-hidden="true" />
              Platform Admin
            </button>
          )}
          <button
            type="button"
            className={activeSection === "reports" ? "active" : ""}
            onClick={() => setActiveSection("reports")}
          >
            <FileText aria-hidden="true" />
            Reports
          </button>
        </nav>

        <div className="sidebar-context">
          <span>Actieve organisatie</span>
          <strong title={activeOrganizationLabel}>{activeOrganizationLabel}</strong>
        </div>
      </aside>

      <section className="app-main">
        <header className="app-topbar no-print">
          <div>
            <span className="eyebrow">Administration &amp; security workspace</span>
            <h1>AdminDeck</h1>
          </div>
          <div className="user-session">
            <div>
              <span>Ingelogd als</span>
              <strong>{currentUser.full_name}</strong>
              <em>Role: {currentUser.role}</em>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleLogout()}>
              <LogOut aria-hidden="true" />
              Logout
            </button>
          </div>
        </header>

        <section className="content-header no-print">
          <div>
            <h2>{activeSectionMeta[activeSection].title}</h2>
            <p>{activeSectionMeta[activeSection].description}</p>
          </div>
          <div className="hero-status" aria-live="polite">
            <BadgeCheck aria-hidden="true" />
            <span className="hero-status-name" title={activeOrganizationLabel}>
              {activeOrganizationLabel}
            </span>
          </div>
        </section>

      {feedback && (
        <section className={`message ${feedback.type}`} aria-live="polite">
          {feedback.type === "error" ? (
            <AlertCircle aria-hidden="true" />
          ) : (
            <CheckCircle2 aria-hidden="true" />
          )}
          <span>{feedback.message}</span>
        </section>
      )}

      <section className={sectionClass("dashboard", "dashboard-view")} aria-label="Dashboard">
        <section className="product-context-panel">
          <h2>Klantportaal voor security assessments</h2>
          <p>
            Dit portaal is bedoeld om per klantorganisatie risico-assessments, Google Workspace
            checks en rapportages te beheren.
          </p>
        </section>

        <section className="access-model-panel" aria-label="Access model">
          <div className="access-model-heading">
            <LockKeyhole aria-hidden="true" />
            <div>
              <h2>Access model</h2>
              <p>Customer data scoping is enforced. Support access logging foundation enabled.</p>
            </div>
          </div>
          <div className="access-model-grid">
            <div>
              <span>Platform role</span>
              <strong>{currentUser.role}</strong>
            </div>
            <div>
              <span>Customer memberships</span>
              <strong>{currentUser.customer_memberships.length}</strong>
            </div>
          </div>
          {canViewPlatformAdmin && (
            <p className="platform-admin-hint">Platform Admin overview available.</p>
          )}
        </section>

        <div className="summary-grid" aria-label="Assessment overzicht">
          <article className="metric-card">
            <Users aria-hidden="true" />
            <div className="metric-content">
              <span className="metric-label">Actieve customer</span>
              <strong className="metric-value" title={activeCustomerLabel}>
                {activeCustomerLabel}
              </strong>
            </div>
          </article>
          <article className="metric-card">
            <Building2 aria-hidden="true" />
            <div className="metric-content">
              <span className="metric-label">Actieve organisatie</span>
              <strong className="metric-value" title={selectedOrganization?.name ?? "Niet gekozen"}>
                {selectedOrganization?.name ?? "Niet gekozen"}
              </strong>
            </div>
          </article>
          <article className="metric-card">
            <ClipboardList aria-hidden="true" />
            <div className="metric-content">
              <span className="metric-label">Actief assessment</span>
              <strong className="metric-value" title={selectedAssessment?.title ?? "Niet gekozen"}>
                {selectedAssessment?.title ?? "Niet gekozen"}
              </strong>
            </div>
          </article>
          <article className="metric-card">
            <Flag aria-hidden="true" />
            <div className="metric-content">
              <span className="metric-label">Findings</span>
              <strong className="metric-value metric-number">{assessmentFindings.length}</strong>
            </div>
          </article>
          <article className="metric-card">
            <TrendingUp aria-hidden="true" />
            <div className="metric-content">
              <span className="metric-label">Gemiddelde score</span>
              <strong className="metric-value metric-number">{formatScore(averageRiskScore)}</strong>
            </div>
          </article>
          <article className="metric-card">
            <ShieldAlert aria-hidden="true" />
            <div className="metric-content">
              <span className="metric-label">Hoogste risico</span>
              <strong className="metric-value">
                {highestFinding ? (
                  <span className={`risk-badge risk-${highestFinding.dread_score.risk_level.toLowerCase()}`}>
                    {highestFinding.dread_score.risk_level}
                  </span>
                ) : (
                  "-"
                )}
              </strong>
            </div>
          </article>
        </div>

        <section className="recommended-next-panel">
          <div>
            <h2>Aanbevolen volgende stap</h2>
            <p>{recommendedNextStep.message}</p>
          </div>
          <button type="button" onClick={() => setActiveSection(recommendedNextStep.target)}>
            <Target aria-hidden="true" />
            {recommendedNextStep.buttonLabel}
          </button>
        </section>
      </section>

      <section
        className={`workflow-layout ${
          activeSection === "dashboard" ||
          activeSection === "reports" ||
          activeSection === "platform-admin"
            ? "section-hidden"
            : ""
        } ${activeSection === "assessment" ? "" : "single-column"}`}
      >
        <div className="setup-column">
          <article className={sectionClass("customers", "panel compact-panel customer-panel")}>
            <div className="panel-heading">
              <span className="step-number">A</span>
              <div>
                <h2>Customer context</h2>
                <p>
                  Platform/customer context for this MVP. Dit is nog geen volledig
                  platform-admin/customer-user model.
                </p>
              </div>
            </div>

            <form className="form-stack" onSubmit={handleCreateCustomer}>
              <label>
                Customernaam
                <input
                  value={customerName}
                  onChange={(event) => setCustomerName(event.target.value)}
                  placeholder="Demo Customer"
                  required
                />
              </label>
              <label>
                Slug
                <input
                  value={customerSlug}
                  onChange={(event) => setCustomerSlug(event.target.value)}
                  placeholder="demo-customer"
                  required
                />
              </label>
              <div className="two-column-fields">
                <label>
                  Contactpersoon
                  <input
                    value={customerContactName}
                    onChange={(event) => setCustomerContactName(event.target.value)}
                    placeholder="Alex Admin"
                  />
                </label>
                <label>
                  Contact e-mail
                  <input
                    type="email"
                    value={customerContactEmail}
                    onChange={(event) => setCustomerContactEmail(event.target.value)}
                    placeholder="alex@example.local"
                  />
                </label>
              </div>
              <label>
                Status
                <select
                  value={customerStatus}
                  onChange={(event) => setCustomerStatus(event.target.value)}
                >
                  <option value="active">Active</option>
                  <option value="prospect">Prospect</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>
              <label>
                Notes
                <textarea
                  value={customerNotes}
                  onChange={(event) => setCustomerNotes(event.target.value)}
                  placeholder="Korte interne notitie"
                  rows={3}
                />
              </label>
              <button type="submit" disabled={!canCreateCustomer || saving === "customer"}>
                <Plus aria-hidden="true" />
                {renderButtonLabel("customer", "Customer aanmaken")}
              </button>
            </form>

            <label className="selector">
              Actieve customer
              <select
                value={selectedCustomerId}
                onChange={(event) => setSelectedCustomerId(event.target.value)}
                disabled={customers.length === 0}
              >
                <option value="">Geen actieve customer</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.name}
                  </option>
                ))}
              </select>
            </label>

            {customers.length === 0 ? (
              <div className="mini-empty-state">Nog geen customers. Maak de eerste customer aan.</div>
            ) : (
              <div className="customer-list" aria-label="Customer overzicht">
                {customers.map((customer) => (
                  <article
                    className={`customer-list-item ${
                      customer.id === selectedCustomerId ? "active" : ""
                    }`}
                    key={customer.id}
                  >
                    <div>
                      <strong title={customer.name}>{customer.name}</strong>
                      <span>{customer.slug}</span>
                    </div>
                    <em>{customer.status}</em>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className={sectionClass("organizations", "panel compact-panel")}>
            <div className="panel-heading">
              <span className="step-number">1</span>
              <div>
                <h2>Organisatie</h2>
                <p>Kies een bestaande organisatie of maak een nieuwe aan.</p>
              </div>
            </div>

            {selectedCustomer && (
              <div className="helper-note">
                <Link2 aria-hidden="true" />
                Nieuwe organisaties worden gekoppeld aan {selectedCustomer.name}.
              </div>
            )}

            <form className="form-stack" onSubmit={handleCreateOrganization}>
              <label>
                Organisatienaam
                <input
                  value={organizationName}
                  onChange={(event) => setOrganizationName(event.target.value)}
                  placeholder="Acme Security"
                  required
                />
              </label>
              <label>
                Beschrijving
                <textarea
                  value={organizationDescription}
                  onChange={(event) => setOrganizationDescription(event.target.value)}
                  placeholder="Interne security organisatie"
                  rows={3}
                />
              </label>
              <button type="submit" disabled={!organizationName.trim() || saving === "organization"}>
                <Plus aria-hidden="true" />
                {renderButtonLabel("organization", "Organisatie aanmaken")}
              </button>
            </form>

            <label className="selector">
              Actieve organisatie
              <select
                value={selectedOrganizationId}
                onChange={(event) => setSelectedOrganizationId(event.target.value)}
                disabled={visibleOrganizations.length === 0}
              >
                <option value="">Selecteer organisatie</option>
                {visibleOrganizations.map((organization) => (
                  <option key={organization.id} value={organization.id}>
                    {organization.name}
                  </option>
                ))}
              </select>
            </label>

            {selectedCustomerId && visibleOrganizations.length === 0 && (
              <div className="mini-empty-state">
                Deze customer heeft nog geen gekoppelde organizations.
              </div>
            )}

            {selectedOrganization && (
              <div className="linked-customer-note">
                <Link2 aria-hidden="true" />
                <span>
                  Gekoppelde customer:{" "}
                  <strong>{selectedOrganizationCustomer?.name ?? "geen customer gekoppeld"}</strong>
                </span>
              </div>
            )}
          </article>

          <article className={sectionClass("google-workspace", "panel compact-panel connector-panel")}>
            <div className="panel-heading">
              <span className="step-number">G</span>
              <div>
                <h2>Google Workspace connector</h2>
                <p>Leg alvast configuratiemetadata vast voor de latere echte koppeling.</p>
              </div>
            </div>

            {!selectedOrganizationId && (
              <div className="helper-note">
                <ShieldAlert aria-hidden="true" />
                Kies eerst een organisatie.
              </div>
            )}

            <div className="connector-summary">
              <div>
                <span>Status</span>
                <strong>
                  {googleWorkspaceConnectorConfig ? (
                    <span
                      className={`connector-status connector-status-${googleWorkspaceConnectorConfig.status.replace(
                        "_",
                        "-"
                      )}`}
                    >
                      {googleWorkspaceConnectorConfig.status.replace("_", " ")}
                    </span>
                  ) : (
                    <span className="connector-status connector-status-not-configured">
                      not configured
                    </span>
                  )}
                </strong>
              </div>
              <div>
                <span>Primary domain</span>
                <strong title={googleWorkspaceConnectorConfig?.primary_domain ?? "Nog niet gezet"}>
                  {googleWorkspaceConnectorConfig?.primary_domain ?? "-"}
                </strong>
              </div>
              <div>
                <span>Auth method</span>
                <strong>
                  {googleWorkspaceConnectorConfig
                    ? connectorAuthMethodLabels[googleWorkspaceConnectorConfig.auth_method]
                    : "-"}
                </strong>
              </div>
              <div>
                <span>Admin subject</span>
                <strong
                  title={googleWorkspaceConnectorConfig?.admin_subject_email ?? "Nog niet gezet"}
                >
                  {googleWorkspaceConnectorConfig?.admin_subject_email ?? "-"}
                </strong>
              </div>
              <div>
                <span>Laatst getest</span>
                <strong>{formatOptionalDateTime(googleWorkspaceConnectorConfig?.last_tested_at ?? null)}</strong>
              </div>
            </div>

            <p className="connector-disclaimer">
              No secrets are stored. Real Google Workspace API access will be added later.
            </p>

            <form className="form-stack connector-form" onSubmit={handleSaveConnectorConfig}>
              <label>
                Display name
                <input
                  value={connectorDisplayName}
                  onChange={(event) => setConnectorDisplayName(event.target.value)}
                  placeholder="Google Workspace"
                  disabled={!selectedOrganizationId}
                  required
                />
              </label>
              <label>
                Primary domain
                <input
                  value={connectorPrimaryDomain}
                  onChange={(event) => setConnectorPrimaryDomain(event.target.value)}
                  placeholder="example.com"
                  disabled={!selectedOrganizationId}
                />
              </label>
              <label>
                Admin subject email
                <input
                  type="email"
                  value={connectorAdminSubjectEmail}
                  onChange={(event) => setConnectorAdminSubjectEmail(event.target.value)}
                  placeholder="admin@example.com"
                  disabled={!selectedOrganizationId}
                />
              </label>
              <label>
                Auth method
                <select
                  value={connectorAuthMethod}
                  onChange={(event) =>
                    setConnectorAuthMethod(event.target.value as ConnectorAuthMethod)
                  }
                  disabled={!selectedOrganizationId}
                >
                  <option value="service_account_domain_wide_delegation">
                    Service account + domain-wide delegation
                  </option>
                  <option value="oauth_admin_consent">OAuth admin consent</option>
                  <option value="manual_import">Manual import</option>
                </select>
              </label>
              <label>
                Notes
                <textarea
                  value={connectorNotes}
                  onChange={(event) => setConnectorNotes(event.target.value)}
                  placeholder="Korte notitie over beoogde configuratie"
                  rows={3}
                  disabled={!selectedOrganizationId}
                />
              </label>
              <div className="connector-actions">
                <button
                  type="submit"
                  disabled={!canSaveConnectorConfig || isConnectorSaving}
                >
                  {isConnectorSaving ? (
                    <Loader2 className="spin" aria-hidden="true" />
                  ) : (
                    <Plus aria-hidden="true" />
                  )}
                  {isConnectorSaving ? "Opslaan" : "Configuratie opslaan"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleTestConnectorConfig}
                  disabled={!googleWorkspaceConnectorConfig || isConnectorTesting}
                >
                  {isConnectorTesting ? (
                    <Loader2 className="spin" aria-hidden="true" />
                  ) : (
                    <Activity aria-hidden="true" />
                  )}
                  Test connection
                </button>
              </div>
            </form>

            {connectorFeedback && (
              <section className={`message connector-message ${connectorFeedback.type}`} aria-live="polite">
                {connectorFeedback.type === "error" ? (
                  <AlertCircle aria-hidden="true" />
                ) : (
                  <CheckCircle2 aria-hidden="true" />
                )}
                <span>{connectorFeedback.message}</span>
              </section>
            )}
          </article>

          <article className={sectionClass("google-workspace", "panel compact-panel google-workspace-info")}>
            <div className="panel-heading">
              <span className="step-number">S</span>
              <div>
                <h2>Mock scan en check catalog</h2>
                <p>No real Google data is accessed yet.</p>
              </div>
            </div>

            <div className="google-workspace-explainer">
              <article>
                <strong>Connector configuration</strong>
                <span>Metadata/configuratie voor later. No secrets are stored.</span>
              </article>
              <article>
                <strong>Check catalog</strong>
                <span>Welke Google Workspace checks de tool nu als mock/demo kent.</span>
              </article>
              <article>
                <strong>Mock scan</strong>
                <span>Mock scan creates demo findings for the selected assessment.</span>
              </article>
            </div>

            <section className="check-catalog-panel" aria-label="Google Workspace check catalog">
              <div className="check-catalog-toolbar">
                <div>
                  <strong>Check catalog</strong>
                  <span>
                    Welke Google Workspace checks de tool kent. Deze checks zijn nu mock/demo.
                  </span>
                </div>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setShowGoogleWorkspaceChecks((current) => !current)}
                >
                  {showGoogleWorkspaceChecks ? "Verberg checks" : "Bekijk checks"}
                </button>
              </div>

              {showGoogleWorkspaceChecks && (
                <div className="check-catalog-list">
                  {googleWorkspaceChecks.map((check) => (
                    <article className="check-catalog-item" key={check.check_id}>
                      <div className="check-catalog-title">
                        <span>{check.check_id}</span>
                        <h4>{check.title}</h4>
                        <em>Mock only</em>
                      </div>
                      <p>{check.risk_statement}</p>
                      <div className="check-catalog-meta">
                        <span>{check.category}</span>
                        <span>
                          DREAD {averageDreadScore(check.default_dread_score).toFixed(1)} ·{" "}
                          {check.default_risk_level}
                        </span>
                      </div>
                      <dl>
                        <div>
                          <dt>Finding</dt>
                          <dd>{check.maps_to_finding_title}</dd>
                        </div>
                        <div>
                          <dt>Later databron/API</dt>
                          <dd>{check.future_google_api_hint}</dd>
                        </div>
                      </dl>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="mock-scan-panel" aria-label="Google Workspace mock scan">
              <div className="inline-heading">
                <ShieldAlert aria-hidden="true" />
                <h3>Mock scan</h3>
              </div>
              <p>No real Google data is accessed yet. Mock scan creates demo findings for the selected assessment.</p>

              {!selectedAssessmentId && (
                <div className="mini-empty-state">Selecteer eerst een assessment.</div>
              )}

              <button
                type="button"
                onClick={handleRunMockGoogleWorkspaceScan}
                disabled={!selectedAssessmentId || isScanRunning}
              >
                {isScanRunning ? (
                  <Loader2 className="spin" aria-hidden="true" />
                ) : (
                  <Activity aria-hidden="true" />
                )}
                {isScanRunning ? "Mock scan uitvoeren" : "Run mock Google Workspace scan"}
              </button>

              <div className="scan-run-list" aria-label="Recente scan runs">
                <div className="scan-run-list-heading">
                  <strong>Scan run historie</strong>
                  {isScanLoading && <span>laden</span>}
                </div>
                {scanRuns.length === 0 ? (
                  <div className="mini-empty-state">Nog geen scan runs voor dit assessment.</div>
                ) : (
                  scanRuns.slice(0, 6).map((scanRun) => (
                    <article className="scan-run-item" key={scanRun.id}>
                      <div>
                        <strong>{scanRun.status}</strong>
                        <span>{formatDateTime(scanRun.started_at)}</span>
                      </div>
                      <div>
                        <strong>{scanRun.findings_created}</strong>
                        <span>findings</span>
                      </div>
                      <p>{scanRun.summary ?? "Geen samenvatting beschikbaar."}</p>
                      {scanRun.completed_at && (
                        <time dateTime={scanRun.completed_at}>
                          Afgerond {formatDateTime(scanRun.completed_at)}
                        </time>
                      )}
                    </article>
                  ))
                )}
              </div>
            </section>
          </article>

          <article className={sectionClass("assessment", "panel compact-panel")}>
            <div className="panel-heading">
              <span className="step-number">2</span>
              <div>
                <h2>Assessment</h2>
                <p>Start een assessment binnen de actieve organisatie.</p>
              </div>
            </div>

            {!selectedOrganizationId && (
              <div className="helper-note">
                <Target aria-hidden="true" />
                Kies eerst een organisatie.
              </div>
            )}

            <form className="form-stack" onSubmit={handleCreateAssessment}>
              <label>
                Assessmenttitel
                <input
                  value={assessmentTitle}
                  onChange={(event) => setAssessmentTitle(event.target.value)}
                  placeholder="Q3 identity review"
                  required
                  disabled={!selectedOrganizationId}
                />
              </label>
              <label>
                Scope
                <textarea
                  value={assessmentScope}
                  onChange={(event) => setAssessmentScope(event.target.value)}
                  placeholder="Identity, SaaS en beheeraccounts"
                  rows={3}
                  disabled={!selectedOrganizationId}
                />
              </label>
              <button type="submit" disabled={!canCreateAssessment || saving === "assessment"}>
                <Plus aria-hidden="true" />
                {renderButtonLabel("assessment", "Assessment aanmaken")}
              </button>
            </form>

            <label className="selector">
              Actief assessment
              <select
                value={selectedAssessmentId}
                onChange={(event) => setSelectedAssessmentId(event.target.value)}
                disabled={organizationAssessments.length === 0}
              >
                <option value="">Selecteer assessment</option>
                {organizationAssessments.map((assessment) => (
                  <option key={assessment.id} value={assessment.id}>
                    {assessment.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="assessment-actions">
              <button type="button" onClick={handleOpenReport} disabled={!selectedAssessmentId || isReportLoading}>
                {isReportLoading ? (
                  <Loader2 className="spin" aria-hidden="true" />
                ) : (
                  <FileText aria-hidden="true" />
                )}
                Open rapport
              </button>
            </div>

          </article>
        </div>

        <article className={sectionClass("assessment", "panel finding-panel composer-panel")}>
          <div className="panel-heading">
            <span className="step-number">3</span>
            <div>
              <h2>Finding toevoegen</h2>
              <p>Koppel optioneel een asset en vul de DREAD-score in.</p>
            </div>
          </div>

          {!selectedAssessmentId && (
            <div className="helper-note">
              <ShieldAlert aria-hidden="true" />
              Kies eerst een assessment voordat je een finding toevoegt.
            </div>
          )}

          <form className="asset-form" onSubmit={handleCreateAsset}>
            <div className="inline-heading">
              <Database aria-hidden="true" />
              <h3>Asset</h3>
            </div>
            <label>
              Gekoppeld asset
              <select
                value={selectedAssetId}
                onChange={(event) => setSelectedAssetId(event.target.value)}
                disabled={!selectedOrganizationId || organizationAssets.length === 0}
              >
                <option value="">Geen asset gekozen</option>
                {organizationAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="asset-create-grid">
              <label>
                Nieuw asset
                <input
                  value={assetName}
                  onChange={(event) => setAssetName(event.target.value)}
                  placeholder="Google Workspace"
                  disabled={!selectedOrganizationId}
                />
              </label>
              <label>
                Type
                <select
                  value={assetType}
                  onChange={(event) => setAssetType(event.target.value)}
                  disabled={!selectedOrganizationId}
                >
                  <option value="saas">SaaS</option>
                  <option value="system">System</option>
                  <option value="process">Process</option>
                  <option value="data">Data</option>
                </select>
              </label>
              <label>
                Identifier
                <input
                  value={assetIdentifier}
                  onChange={(event) => setAssetIdentifier(event.target.value)}
                  placeholder="workspace-primary"
                  disabled={!selectedOrganizationId}
                />
              </label>
              <button type="submit" disabled={!canCreateAsset || saving === "asset"}>
                <Plus aria-hidden="true" />
                {renderButtonLabel("asset", "Asset toevoegen")}
              </button>
            </div>
          </form>

          <form className="finding-form" onSubmit={handleCreateFinding}>
            <label>
              Findingtitel
              <input
                value={findingTitle}
                onChange={(event) => setFindingTitle(event.target.value)}
                placeholder="Onvoldoende MFA dekking"
                required
                disabled={!selectedAssessmentId}
              />
            </label>
            <label>
              Beschrijving
              <textarea
                value={findingDescription}
                onChange={(event) => setFindingDescription(event.target.value)}
                placeholder="Beschrijf het risico kort en concreet."
                rows={3}
                disabled={!selectedAssessmentId}
              />
            </label>
            <label>
              Mitigatie
              <textarea
                value={findingMitigation}
                onChange={(event) => setFindingMitigation(event.target.value)}
                placeholder="Welke maatregel verlaagt het risico?"
                rows={3}
                disabled={!selectedAssessmentId}
              />
            </label>

            <div className="score-grid">
              {dreadControls.map((control) => (
                <label className="score-control" key={control.key}>
                  <span>
                    <span>
                      {control.label}
                      <small>{control.hint}</small>
                    </span>
                    <strong className="score-value">{dreadScore[control.key]}</strong>
                  </span>
                  <input
                    type="range"
                    min="0"
                    max="10"
                    value={dreadScore[control.key]}
                    onChange={(event) => updateFindingScore(control.key, Number(event.target.value))}
                    disabled={!selectedAssessmentId}
                  />
                </label>
              ))}
            </div>

            <div className="form-footer">
              <div className={`score-summary risk-outline-${previewRiskLevel.toLowerCase()}`}>
                <span>Totale DREAD-score</span>
                <strong>{previewScore.toFixed(2)}</strong>
                <em>{previewRiskLevel}</em>
              </div>
              <button type="submit" disabled={!canCreateFinding || saving === "finding"}>
                <Plus aria-hidden="true" />
                {renderButtonLabel("finding", "Finding toevoegen")}
              </button>
            </div>
          </form>
        </article>
      </section>

      <section className={sectionClass("assessment", "findings-section")}>
        <div className="section-heading">
          <div>
            <span className="step-number">4</span>
            <div>
              <h2>Findings overzicht</h2>
              <p className="section-current-name" title={selectedAssessment?.title ?? "Geen assessment geselecteerd"}>
                {selectedAssessment?.title ?? "Geen assessment geselecteerd"}
              </p>
            </div>
          </div>
          <span className="count-pill">{assessmentFindings.length} totaal</span>
        </div>

        {assessmentFindings.length === 0 ? (
          <div className="empty-state">
            <Layers3 aria-hidden="true" />
            <h3>Nog geen findings</h3>
            <p>Voeg de eerste bevinding toe om de DREAD-score te berekenen.</p>
          </div>
        ) : (
          <div className="findings-table">
            <div className="finding-table-head">
              <span>Finding</span>
              <span>Asset</span>
              <span>Score</span>
              <span>Risk</span>
              <span>Mitigatie</span>
            </div>
            {assessmentFindings.map((finding) => {
              const asset = finding.asset_id ? assetById.get(finding.asset_id) : null;
              return (
                <article className="finding-row" key={finding.id}>
                  <div className="finding-main">
                    <h3 title={finding.title}>{finding.title}</h3>
                    <p>{finding.description ?? "Geen beschrijving opgegeven."}</p>
                  </div>
                  <span className="asset-name" title={asset?.name ?? "Niet gekoppeld"}>
                    {asset?.name ?? "Niet gekoppeld"}
                  </span>
                  <strong className="finding-score">{finding.dread_score.total_score.toFixed(2)}</strong>
                  <span className={`risk-badge risk-${finding.dread_score.risk_level.toLowerCase()}`}>
                    {finding.dread_score.risk_level}
                  </span>
                  <p className="mitigation-text">{finding.mitigation ?? "Nog geen mitigatie vastgelegd."}</p>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section
        className={sectionClass("platform-admin", "platform-admin-view")}
        aria-label="Platform Admin overview"
      >
        <article className="platform-admin-hero">
          <div>
            <span className="eyebrow">Platform Admin</span>
            <h2>Read-only support overview</h2>
            <p>
              Read-only platform overview for support and troubleshooting. Customer data access is
              scoped and support actions are audit logged.
            </p>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={loadPlatformAdminOverview}
            disabled={!canViewPlatformAdmin || isPlatformAdminOverviewLoading}
          >
            {isPlatformAdminOverviewLoading ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : (
              <Activity aria-hidden="true" />
            )}
            Refresh overview
          </button>
        </article>

        {!canViewPlatformAdmin ? (
          <div className="empty-state">
            <LockKeyhole aria-hidden="true" />
            <h3>Geen toegang</h3>
            <p>Alleen platform_admin en platform_support kunnen dit overzicht openen.</p>
          </div>
        ) : !platformAdminOverview ? (
          <div className="empty-state">
            <Activity className={isPlatformAdminOverviewLoading ? "spin" : ""} aria-hidden="true" />
            <h3>Platform overzicht laden</h3>
            <p>Open of refresh het overzicht om supportdata op te halen.</p>
          </div>
        ) : (
          <>
            <div className="platform-admin-kpi-grid" aria-label="Platform totals">
              <article>
                <span>Customers</span>
                <strong>{platformAdminOverview.totals.customers_count}</strong>
              </article>
              <article>
                <span>Organizations</span>
                <strong>{platformAdminOverview.totals.organizations_count}</strong>
              </article>
              <article>
                <span>Connector configs</span>
                <strong>{platformAdminOverview.totals.connector_configs_count}</strong>
              </article>
              <article>
                <span>Scan runs</span>
                <strong>{platformAdminOverview.totals.scan_runs_count}</strong>
              </article>
              <article>
                <span>Audit events</span>
                <strong>{platformAdminOverview.totals.audit_events_count}</strong>
              </article>
            </div>

            <section className="platform-admin-table-card">
              <div className="platform-admin-section-heading">
                <h3>Customer overview</h3>
                <p>Customers, gekoppelde organisaties, connectorconfigs en recente activiteit.</p>
              </div>
              {platformAdminOverview.customers.length === 0 ? (
                <div className="mini-empty-state">Nog geen customers beschikbaar.</div>
              ) : (
                <div className="platform-admin-table-wrap">
                  <table className="platform-admin-table">
                    <thead>
                      <tr>
                        <th>Customer</th>
                        <th>Status</th>
                        <th>Organizations</th>
                        <th>Connector configs</th>
                        <th>Last scan</th>
                        <th>Last audit event</th>
                      </tr>
                    </thead>
                    <tbody>
                      {platformAdminOverview.customers.map((customer) => (
                        <tr key={customer.id}>
                          <td>
                            <strong>{customer.name}</strong>
                            <span>{customer.slug}</span>
                          </td>
                          <td>
                            <span className="status-pill">{customer.status}</span>
                          </td>
                          <td>{customer.organization_count}</td>
                          <td>{customer.connector_config_count}</td>
                          <td>{formatNullableDateTime(customer.last_scan_run_at)}</td>
                          <td>{formatNullableDateTime(customer.last_audit_event_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="platform-admin-table-card">
              <div className="platform-admin-section-heading">
                <h3>Connector status</h3>
                <p>Configuratiemetadata. Er worden geen secrets of credentials getoond.</p>
              </div>
              {platformAdminOverview.connector_configs.length === 0 ? (
                <div className="mini-empty-state">Nog geen connectorconfigs beschikbaar.</div>
              ) : (
                <div className="platform-admin-table-wrap">
                  <table className="platform-admin-table">
                    <thead>
                      <tr>
                        <th>Customer</th>
                        <th>Organization</th>
                        <th>Connector type</th>
                        <th>Status</th>
                        <th>Primary domain</th>
                        <th>Last tested</th>
                        <th>Last error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {platformAdminOverview.connector_configs.map((connectorConfig) => (
                        <tr key={connectorConfig.id}>
                          <td>{connectorConfig.customer_name ?? "-"}</td>
                          <td>{connectorConfig.organization_name}</td>
                          <td>{connectorConfig.connector_type.replace(/_/g, " ")}</td>
                          <td>
                            <span
                              className={`connector-status connector-status-${connectorConfig.status.replace(
                                "_",
                                "-"
                              )}`}
                            >
                              {connectorConfig.status.replace(/_/g, " ")}
                            </span>
                          </td>
                          <td>{connectorConfig.primary_domain ?? "-"}</td>
                          <td>{formatNullableDateTime(connectorConfig.last_tested_at)}</td>
                          <td>{connectorConfig.last_error ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="platform-admin-table-card">
              <div className="platform-admin-section-heading">
                <h3>Recent scan runs</h3>
                <p>Laatste 10 scan runs voor troubleshooting.</p>
              </div>
              {platformAdminOverview.recent_scan_runs.length === 0 ? (
                <div className="mini-empty-state">Nog geen scan runs beschikbaar.</div>
              ) : (
                <div className="platform-admin-table-wrap">
                  <table className="platform-admin-table">
                    <thead>
                      <tr>
                        <th>Customer</th>
                        <th>Organization</th>
                        <th>Assessment</th>
                        <th>Status</th>
                        <th>Findings</th>
                        <th>Completed</th>
                        <th>Summary</th>
                      </tr>
                    </thead>
                    <tbody>
                      {platformAdminOverview.recent_scan_runs.map((scanRun) => (
                        <tr key={scanRun.id}>
                          <td>{scanRun.customer_name ?? "-"}</td>
                          <td>{scanRun.organization_name}</td>
                          <td>{scanRun.assessment_title}</td>
                          <td>
                            <span className={`status-pill status-${scanRun.status}`}>
                              {scanRun.status}
                            </span>
                          </td>
                          <td>{scanRun.findings_created}</td>
                          <td>{formatNullableDateTime(scanRun.completed_at)}</td>
                          <td>{scanRun.summary ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="platform-admin-table-card">
              <div className="platform-admin-section-heading">
                <h3>Recent audit events</h3>
                <p>Laatste 10 audit events zonder metadata of secretvelden.</p>
              </div>
              {platformAdminOverview.recent_audit_events.length === 0 ? (
                <div className="mini-empty-state">Nog geen audit events beschikbaar.</div>
              ) : (
                <div className="platform-admin-table-wrap">
                  <table className="platform-admin-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Actor</th>
                        <th>Customer</th>
                        <th>Action</th>
                        <th>Object type</th>
                        <th>Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {platformAdminOverview.recent_audit_events.map((auditEvent) => (
                        <tr key={auditEvent.id}>
                          <td>{formatDateTime(auditEvent.created_at)}</td>
                          <td>
                            <strong>{auditEvent.actor_email ?? "system"}</strong>
                            <span>{auditEvent.actor_role ?? "-"}</span>
                          </td>
                          <td>{auditEvent.customer_name ?? "-"}</td>
                          <td>{auditEvent.action}</td>
                          <td>{auditEvent.object_type}</td>
                          <td>
                            <span className={`status-pill status-${auditEvent.outcome}`}>
                              {auditEvent.outcome}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </section>

      <section className={sectionClass("reports", "reports-view report-shell")}>
        <article className="panel report-intro-panel no-print">
          <div className="panel-heading">
            <span className="step-number">R</span>
            <div>
              <h2>Rapportage/export</h2>
              <p>
                Open het rapport voor het actieve assessment. Gebruik daarna Print / opslaan als PDF
                via de browser.
              </p>
            </div>
          </div>
          {!selectedAssessmentId && (
            <div className="helper-note">
              <FileText aria-hidden="true" />
              Selecteer eerst een assessment in de Assessment workspace.
            </div>
          )}
          <button type="button" onClick={handleOpenReport} disabled={!selectedAssessmentId || isReportLoading}>
            {isReportLoading ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : (
              <FileText aria-hidden="true" />
            )}
            Rapport openen
          </button>
        </article>

        {reportPanel}
      </section>

      {isLoading && (
        <div className="loading-overlay" aria-live="polite">
          <Activity className="spin" aria-hidden="true" />
          Workspace laden
        </div>
      )}
      </section>
    </main>
  );
}

export default App;
