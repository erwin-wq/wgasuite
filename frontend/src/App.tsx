import {
  Activity,
  ArrowLeft,
  Database,
  FileText,
  Layers3,
  LockKeyhole,
  Loader2,
  Plus,
  Printer,
  ShieldAlert,
  Target,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { Button } from "./components/ui/Button";
import { Card } from "./components/ui/Card";
import { Alert } from "./components/ui/Feedback";
import { Input } from "./components/ui/FormControls";
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
import { ConnectionWizard } from "./features/google-workspace/ConnectionWizard";
import { DomainsInventory } from "./features/google-workspace/DomainsInventory";
import { AdminRolesInventory } from "./features/google-workspace/AdminRolesInventory";
import { GmailDelegationAuthorization } from "./features/google-workspace/GmailDelegationAuthorization";
import { GmailDelegationManagement } from "./features/google-workspace/GmailDelegationManagement";
import { GroupManagement } from "./features/google-workspace/GroupManagement";
import { WorkspaceConnectionOverview } from "./features/google-workspace/GoogleWorkspaceAdministration";
import { OrganizationalUnits } from "./features/google-workspace/OrganizationalUnits";
import { UserDirectoryAdministration } from "./features/google-workspace/UserDirectoryAdministration";
import { DashboardOverview } from "./features/dashboard/DashboardOverview";
import { CustomerAdministration } from "./features/administration/CustomerAdministration";
import { OrganizationAdministration } from "./features/administration/OrganizationAdministration";
import { PlatformAdministration } from "./features/administration/PlatformAdministration";
import { AppShell, RouteUnavailable } from "./features/navigation/AppShell";
import { appRoutes, findRoute, routeList, type AppRouteId } from "./app/routes";
import type { ActiveSection } from "./features/navigation/AppNavigation";
import { useThemePreference } from "./theme/theme";

type DreadScoreKey = keyof DreadScoreCreate;
type Feedback = { type: "success" | "error"; message: string } | null;
type SavingTarget = "customer" | "organization" | "assessment" | "asset" | "finding" | null;
interface GroupNavigationTarget {
  organizationId: string;
  groupEmail: string;
  requestId: number;
}
const DEMO_FEATURES_ENABLED =
  import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_FEATURES === "true";

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
  const location = useLocation();
  const navigate = useNavigate();
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
  const [isConnectorConfigLoading, setIsConnectorConfigLoading] = useState(false);
  const [hasConnectorConfigLoadError, setHasConnectorConfigLoadError] = useState(false);
  const [isScanRunning, setIsScanRunning] = useState(false);
  const [isConnectorSaving, setIsConnectorSaving] = useState(false);
  const [isConnectorTesting, setIsConnectorTesting] = useState(false);
  const [showGoogleWorkspaceChecks, setShowGoogleWorkspaceChecks] = useState(false);
  const [saving, setSaving] = useState<SavingTarget>(null);
  const [groupNavigationTarget, setGroupNavigationTarget] =
    useState<GroupNavigationTarget | null>(null);
  const [tenantEpoch, setTenantEpoch] = useState(0);
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [platformAdminOverview, setPlatformAdminOverview] =
    useState<PlatformAdminOverview | null>(null);
  const [platformAdminOverviewError, setPlatformAdminOverviewError] = useState<string | null>(null);
  const connectorConfigRequestSequence = useRef(0);
  const workspaceRequestSequence = useRef(0);
  const [isPlatformAdminOverviewLoading, setIsPlatformAdminOverviewLoading] = useState(false);
  const {
    theme,
    density,
    setTheme,
    setDensity,
    activateAccountTheme,
    resetThemeSession
  } = useThemePreference(currentUser?.id ?? null);

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
  const activeGroupNavigation =
    groupNavigationTarget?.organizationId === selectedOrganizationId
      ? groupNavigationTarget
      : null;
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

  const canCreateCustomer = Boolean(customerName.trim() && customerSlug.trim());
  const canCreateAssessment = Boolean(selectedOrganizationId && assessmentTitle.trim());
  const canCreateAsset = Boolean(selectedOrganizationId && assetName.trim());
  const canCreateFinding = Boolean(selectedAssessmentId && findingTitle.trim());
  const canSaveConnectorConfig = Boolean(selectedOrganizationId && connectorDisplayName.trim());
  const canViewPlatformAdmin =
    currentUser?.role === "platform_admin" || currentUser?.role === "platform_support";
  const canManageConnectorCredentials = Boolean(
    currentUser?.role === "platform_admin" ||
      (selectedOrganization?.customer_id &&
        currentUser?.customer_memberships.some(
          (membership) =>
            membership.customer_id === selectedOrganization.customer_id &&
            membership.is_active &&
            membership.role === "customer_admin"
        ))
  );
  const canOperateConnector = Boolean(
    currentUser?.role === "platform_admin" ||
      currentUser?.role === "platform_support" ||
      (selectedOrganization?.customer_id &&
        currentUser?.customer_memberships.some(
          (membership) =>
            membership.customer_id === selectedOrganization.customer_id &&
            membership.is_active &&
            (membership.role === "customer_admin" || membership.role === "customer_user")
        ))
  );

  const canReadSelectedCustomer = Boolean(
    currentUser?.role === "platform_admin" ||
      currentUser?.role === "platform_support" ||
      (selectedOrganization?.customer_id &&
        currentUser?.customer_memberships.some(
          (membership) =>
            membership.customer_id === selectedOrganization.customer_id && membership.is_active
        ))
  );
  const canViewAdministration = Boolean(
    currentUser?.role === "platform_admin" ||
      currentUser?.customer_memberships.some(
        (membership) =>
          membership.is_active &&
          (membership.role === "customer_admin" || membership.role === "customer_user")
      )
  );
  const canCreateOrganization = Boolean(
    currentUser?.role === "platform_admin" ||
      (selectedCustomerId &&
        currentUser?.customer_memberships.some(
          (membership) =>
            membership.customer_id === selectedCustomerId &&
            membership.is_active &&
            (membership.role === "customer_admin" || membership.role === "customer_user")
        ))
  );
  const resolvedRoute = findRoute(location.pathname);
  const currentRoute = resolvedRoute ?? appRoutes.overview;
  const activeSection: ActiveSection =
    currentRoute.id === "overview"
      ? "dashboard"
      : currentRoute.id === "customers"
        ? "customers"
        : currentRoute.id === "organizations"
          ? "organizations"
          : currentRoute.id === "platform"
            ? "platform-admin"
            : "google-workspace";

  const setActiveSection = useCallback(
    (section: ActiveSection) => {
      const target =
        section === "customers"
          ? appRoutes.customers.path
          : section === "organizations"
            ? appRoutes.organizations.path
            : section === "google-workspace"
              ? appRoutes.userLookup.path
              : section === "platform-admin"
                ? appRoutes.platform.path
                : appRoutes.overview.path;
      navigate(target);
    },
    [navigate]
  );

  const resetSession = useCallback((message?: string) => {
    clearStoredAuthToken();
    resetThemeSession();
    setCurrentUser(null);
    setReport(null);
    setCustomers([]);
    setOrganizations([]);
    setAssessments([]);
    setAssets([]);
    setFindings([]);
    setScanRuns([]);
    setGoogleWorkspaceChecks([]);
    setConnectorConfigs([]);
    setIsConnectorConfigLoading(false);
    setHasConnectorConfigLoadError(false);
    setPlatformAdminOverview(null);
    setPlatformAdminOverviewError(null);
    setConnectorFeedback(null);
    setSelectedCustomerId("");
    setSelectedOrganizationId("");
    setSelectedAssessmentId("");
    setSelectedAssetId("");
    setIsLoading(false);
    if (message) {
      setFeedback({ type: "error", message });
    }
    workspaceRequestSequence.current += 1;
    connectorConfigRequestSequence.current += 1;
    setTenantEpoch((current) => current + 1);
  }, [resetThemeSession]);

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
    async (organizationId: string, preserveExisting = false) => {
      const sequence = connectorConfigRequestSequence.current + 1;
      connectorConfigRequestSequence.current = sequence;
      if (!organizationId) {
        setConnectorConfigs([]);
        setIsConnectorConfigLoading(false);
        setHasConnectorConfigLoadError(false);
        return;
      }

      setIsConnectorConfigLoading(true);
      setHasConnectorConfigLoadError(false);
      if (!preserveExisting) {
        setConnectorConfigs([]);
      }
      try {
        const loadedConnectorConfigs = await listOrganizationConnectorConfigs(organizationId);
        if (connectorConfigRequestSequence.current === sequence) {
          setConnectorConfigs(loadedConnectorConfigs);
        }
      } catch (connectorError) {
        if (connectorConfigRequestSequence.current === sequence) {
          setHasConnectorConfigLoadError(true);
          handleRequestError(connectorError);
        }
      } finally {
        if (connectorConfigRequestSequence.current === sequence) {
          setIsConnectorConfigLoading(false);
        }
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
      setPlatformAdminOverviewError(null);
      return;
    }

    setIsPlatformAdminOverviewLoading(true);
    setPlatformAdminOverviewError(null);
    try {
      const loadedOverview = await getPlatformAdminOverview();
      setPlatformAdminOverview(loadedOverview);
    } catch (overviewError) {
      setPlatformAdminOverviewError("The platform support overview could not be loaded.");
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
      const sequence = workspaceRequestSequence.current + 1;
      workspaceRequestSequence.current = sequence;
      setIsLoading(true);
      try {
        const [loadedCustomers, loadedOrganizations, demoData] = await Promise.all([
          listCustomers(),
          listOrganizations(),
          DEMO_FEATURES_ENABLED
            ? Promise.all([
                listAssessments(),
                listAssets(),
                listFindings(),
                listGoogleWorkspaceChecks()
              ])
            : Promise.resolve<[Assessment[], Asset[], Finding[], GoogleWorkspaceCheck[]]>([
                [],
                [],
                [],
                []
              ])
        ]);
        if (workspaceRequestSequence.current !== sequence) return;
        const [loadedAssessments, loadedAssets, loadedFindings, loadedGoogleWorkspaceChecks] =
          demoData;

        setCustomers(loadedCustomers);
        setOrganizations(loadedOrganizations);
        setAssessments(loadedAssessments);
        setAssets(loadedAssets);
        setFindings(loadedFindings);
        setGoogleWorkspaceChecks(loadedGoogleWorkspaceChecks);

        const preferredOrganization = preferredOrganizationId
          ? loadedOrganizations.find((organization) => organization.id === preferredOrganizationId)
          : null;
        const requestedCustomerId = preferredCustomerId ?? selectedCustomerId;
        const nextCustomerId =
          requestedCustomerId ||
          preferredOrganization?.customer_id ||
          loadedOrganizations[0]?.customer_id ||
          loadedCustomers[0]?.id ||
          "";
        const organizationOptions = nextCustomerId
          ? loadedOrganizations.filter((organization) => organization.customer_id === nextCustomerId)
          : loadedOrganizations;
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
        if (workspaceRequestSequence.current === sequence) handleRequestError(loadError);
      } finally {
        if (workspaceRequestSequence.current === sequence) setIsLoading(false);
      }
    },
    [handleRequestError, selectedCustomerId]
  );

  useEffect(() => {
    async function restoreSession() {
      const token = getStoredAuthToken();
      if (!token) {
        resetThemeSession();
        setIsAuthLoading(false);
        setIsLoading(false);
        return;
      }

      try {
        const user = await getCurrentUser();
        activateAccountTheme(user.id);
        setCurrentUser(user);
        await loadWorkspace();
      } catch (authError) {
        handleRequestError(authError);
      } finally {
        setIsAuthLoading(false);
      }
    }

    restoreSession();
  }, [activateAccountTheme, handleRequestError, loadWorkspace, resetThemeSession]);

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
    if (!DEMO_FEATURES_ENABLED || !currentUser || !selectedAssessmentId) {
      setScanRuns([]);
      return;
    }

    loadAssessmentScanRuns(selectedAssessmentId);
  }, [currentUser, loadAssessmentScanRuns, selectedAssessmentId]);

  useEffect(() => {
    if (!currentUser || !selectedOrganizationId) {
      setConnectorConfigs([]);
      setIsConnectorConfigLoading(false);
      setHasConnectorConfigLoadError(false);
      return;
    }

    loadOrganizationConnectorConfigs(selectedOrganizationId);
  }, [currentUser, loadOrganizationConnectorConfigs, selectedOrganizationId]);

  useEffect(() => {
    if (!currentUser) {
      setPlatformAdminOverview(null);
      setPlatformAdminOverviewError(null);
      return;
    }
    if (!canViewPlatformAdmin) {
      setPlatformAdminOverview(null);
      setPlatformAdminOverviewError(null);
      if (activeSection === "platform-admin") {
        setActiveSection("dashboard");
      }
      return;
    }

    if (activeSection === "platform-admin") {
      loadPlatformAdminOverview();
    }
  }, [
    activeSection,
    canViewPlatformAdmin,
    currentUser,
    loadPlatformAdminOverview,
    setActiveSection
  ]);

  useEffect(() => {
    if (!googleWorkspaceConnectorConfig) {
      setConnectorDisplayName("Google Workspace");
      setConnectorPrimaryDomain("");
      setConnectorAdminSubjectEmail("");
      setConnectorNotes("");
      return;
    }

    setConnectorDisplayName(googleWorkspaceConnectorConfig.display_name);
    setConnectorPrimaryDomain(googleWorkspaceConnectorConfig.primary_domain ?? "");
    setConnectorAdminSubjectEmail(googleWorkspaceConnectorConfig.admin_subject_email ?? "");
    setConnectorNotes(googleWorkspaceConnectorConfig.notes ?? "");
  }, [googleWorkspaceConnectorConfig]);

  const isRouteAuthorized = useCallback(
    (routeId: AppRouteId) => {
      if (routeId === "platform") return canViewPlatformAdmin;
      if (routeId === "customers") return currentUser?.role === "platform_admin";
      if (routeId === "organizations") return canViewAdministration;
      const route = appRoutes[routeId];
      if (route.access === "tenant-operator") return canOperateConnector;
      if (route.access === "tenant") return canReadSelectedCustomer;
      return true;
    },
    [
      canOperateConnector,
      canReadSelectedCustomer,
      canViewAdministration,
      canViewPlatformAdmin,
      currentUser?.role
    ]
  );
  const navigationRoutes = useMemo(
    () => routeList.filter((route) => isRouteAuthorized(route.id)),
    [isRouteAuthorized]
  );

  function invalidateTenantContext() {
    workspaceRequestSequence.current += 1;
    connectorConfigRequestSequence.current += 1;
    setSelectedAssessmentId("");
    setSelectedAssetId("");
    setScanRuns([]);
    setConnectorConfigs([]);
    setIsConnectorConfigLoading(false);
    setHasConnectorConfigLoadError(false);
    setGroupNavigationTarget(null);
    setConnectorFeedback(null);
    setFeedback(null);
    setReport(null);
    setTenantEpoch((current) => current + 1);
  }

  function canAccessOrganization(organization: Organization, requireOperation: boolean) {
    if (currentUser?.role === "platform_admin" || currentUser?.role === "platform_support") {
      return true;
    }
    return currentUser?.customer_memberships.some(
      (membership) =>
        membership.customer_id === organization.customer_id &&
        membership.is_active &&
        (!requireOperation ||
          membership.role === "customer_admin" ||
          membership.role === "customer_user")
    ) ?? false;
  }

  function requiresSafeFallback(organization: Organization | undefined) {
    if (!organization) return currentRoute.access !== "authenticated";
    if (currentRoute.access === "tenant-operator") {
      return !canAccessOrganization(organization, true);
    }
    if (currentRoute.access === "tenant") {
      return !canAccessOrganization(organization, false);
    }
    return false;
  }

  function handleCustomerContextChange(customerId: string) {
    invalidateTenantContext();
    setSelectedCustomerId(customerId);
    const nextOrganization = organizations.find(
      (organization) => organization.customer_id === customerId
    );
    setSelectedOrganizationId(nextOrganization?.id ?? "");
    if (requiresSafeFallback(nextOrganization)) {
      navigate(appRoutes.overview.path);
    }
  }

  function handleOrganizationContextChange(organizationId: string) {
    invalidateTenantContext();
    setSelectedOrganizationId(organizationId);
    const organization = organizations.find((candidate) => candidate.id === organizationId);
    if (organization?.customer_id) setSelectedCustomerId(organization.customer_id);
    if (requiresSafeFallback(organization)) {
      navigate(appRoutes.overview.path);
    }
  }

  async function handleCreateCustomer(event: FormEvent<HTMLFormElement>): Promise<boolean> {
    event.preventDefault();
    if (!canCreateCustomer) {
      return false;
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
      return true;
    } catch (submitError) {
      handleRequestError(submitError);
      return false;
    } finally {
      setSaving(null);
    }
  }

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>): Promise<boolean> {
    event.preventDefault();
    const name = organizationName.trim();
    if (!name) {
      return false;
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
      return true;
    } catch (submitError) {
      handleRequestError(submitError);
      return false;
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

  async function handleSaveConnectorConfig(): Promise<ConnectorConfig | null> {
    if (!canSaveConnectorConfig) {
      return null;
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
          auth_method: "service_account_domain_wide_delegation",
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
      return savedConnectorConfig;
    } catch (connectorError) {
      if (connectorError instanceof ApiError && connectorError.status === 401) {
        handleRequestError(connectorError);
      } else {
        setConnectorFeedback({ type: "error", message: (connectorError as Error).message });
      }
      return null;
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
        type: testResult.status === "connected" && testResult.persisted ? "success" : "error",
        message: testResult.message
      });
      await loadOrganizationConnectorConfigs(selectedOrganizationId, true);
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
      activateAccountTheme(user.id);
      setCurrentUser(user);
      await loadWorkspace();
      const returnPath = (location.state as { from?: unknown } | null)?.from;
      navigate(
        typeof returnPath === "string" && findRoute(returnPath)
          ? returnPath
          : appRoutes.overview.path,
        { replace: true, state: null }
      );
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

  const sectionClass = (section: ActiveSection, extraClass = "") =>
    `section-view ${activeSection === section ? "active" : ""} ${extraClass}`.trim();

  if (isAuthLoading) {
    return (
      <main className="app-shell login-shell">
        <Card className="login-panel">
          <LockKeyhole aria-hidden="true" />
          <h1>WGASuite</h1>
          <p>Authenticatie controleren.</p>
          <div className="login-loading">
            <Loader2 className="spin" aria-hidden="true" />
            Sessie laden
          </div>
        </Card>
      </main>
    );
  }

  if (!currentUser) {
    if (location.pathname !== "/login") {
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    }
    return (
      <main className="app-shell login-shell">
        <Card className="login-panel">
          <LockKeyhole aria-hidden="true" />
          <span className="eyebrow">Development login</span>
          <h1>WGASuite</h1>
          <p>
            Gebruik het lokaal geconfigureerde development-account om de MVP auth foundation te
            testen. Dit is geen productie-authenticatie.
          </p>

          {feedback ? <Alert variant={feedback.type === "error" ? "danger" : "success"}>{feedback.message}</Alert> : null}

          <form className="login-form" onSubmit={handleLogin}>
            <Input
              label="Email"
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
              placeholder="admin@example.local"
              autoComplete="username"
              required
            />
            <Input
              label="Password"
              type="password"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
            />
            <Button type="submit" loading={isLoginSaving} loadingLabel="Signing in" disabled={!loginEmail.trim() || !loginPassword}>
              {!isLoginSaving ? <LockKeyhole aria-hidden="true" /> : null}
              Inloggen
            </Button>
          </form>

        </Card>
      </main>
    );
  }

  if (location.pathname === "/login") {
    return <Navigate to={appRoutes.overview.path} replace />;
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
                  <h1>WGASuite DREAD Risk Assessment Report</h1>
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

  if (location.pathname === "/") {
    return <Navigate to={appRoutes.overview.path} replace />;
  }

  return (
    <AppShell
      currentUser={currentUser}
      currentRoute={currentRoute}
      navigationRoutes={navigationRoutes}
      customers={customers}
      organizations={visibleOrganizations}
      selectedCustomerId={selectedCustomerId}
      selectedOrganizationId={selectedOrganizationId}
      isLoading={isLoading}
      isConnected={googleWorkspaceConnectorConfig?.status === "connected"}
      theme={theme}
      density={density}
      onThemeChange={setTheme}
      onDensityChange={setDensity}
      onCustomerChange={handleCustomerContextChange}
      onOrganizationChange={handleOrganizationContextChange}
      onLogout={() => handleLogout()}
    >
      {!resolvedRoute ? (
        <RouteUnavailable title="Page not found">
          The requested page does not exist. Choose a destination from the navigation.
        </RouteUnavailable>
      ) : !isRouteAuthorized(currentRoute.id) ? (
        <RouteUnavailable title="Access unavailable">
          Your current role or workspace context does not permit access to this page.
        </RouteUnavailable>
      ) : (
      <>

      {feedback ? <Alert variant={feedback.type === "error" ? "danger" : "success"}>{feedback.message}</Alert> : null}

      <section className={sectionClass("dashboard", "dashboard-view")} aria-label="Dashboard">
        <DashboardOverview
          customerName={selectedCustomer?.name ?? selectedOrganizationCustomer?.name ?? null}
          organizationName={selectedOrganization?.name ?? null}
          connectorConfig={googleWorkspaceConnectorConfig}
          isLoading={isLoading || isConnectorConfigLoading}
          hasLoadError={hasConnectorConfigLoadError}
          canOperateWorkspace={canOperateConnector}
          canViewConnections={canReadSelectedCustomer}
        />
      </section>

      <section
        className={`workflow-layout ${
          activeSection === "dashboard" ||
          activeSection === "platform-admin"
            ? "section-hidden"
            : ""
        } single-column`}
      >
        <div className="setup-column">
          <article className={sectionClass("customers", "administration-route-shell")}>
            <CustomerAdministration
              customers={customers}
              organizations={organizations}
              selectedCustomerId={selectedCustomerId}
              isLoading={isLoading}
              isSaving={saving === "customer"}
              name={customerName}
              slug={customerSlug}
              contactName={customerContactName}
              contactEmail={customerContactEmail}
              status={customerStatus}
              notes={customerNotes}
              onNameChange={setCustomerName}
              onSlugChange={setCustomerSlug}
              onContactNameChange={setCustomerContactName}
              onContactEmailChange={setCustomerContactEmail}
              onStatusChange={setCustomerStatus}
              onNotesChange={setCustomerNotes}
              onCreate={handleCreateCustomer}
              onSelectCustomer={handleCustomerContextChange}
            />
          </article>

          <article className={sectionClass("organizations", "administration-route-shell")}>
            <OrganizationAdministration
              customer={selectedCustomer ?? null}
              organizations={visibleOrganizations}
              selectedOrganizationId={selectedOrganizationId}
              isLoading={isLoading}
              canCreate={canCreateOrganization}
              isSaving={saving === "organization"}
              name={organizationName}
              description={organizationDescription}
              onNameChange={setOrganizationName}
              onDescriptionChange={setOrganizationDescription}
              onCreate={handleCreateOrganization}
              onSelectOrganization={handleOrganizationContextChange}
            />
          </article>


          <article className={sectionClass("google-workspace", "workspace-admin-panel")}>
            {currentRoute.id === "connections" ? (
              <WorkspaceConnectionOverview
                organizationId={selectedOrganizationId}
                organizationName={selectedOrganization?.name ?? null}
                connectorConfig={googleWorkspaceConnectorConfig}
                canManageConnection={canManageConnectorCredentials}
                canTestConnection={canOperateConnector}
                isLoading={isConnectorConfigLoading && !googleWorkspaceConnectorConfig}
                hasLoadError={hasConnectorConfigLoadError}
                isTesting={isConnectorTesting}
                onReload={() => void loadOrganizationConnectorConfigs(selectedOrganizationId, true)}
                onTest={() => void handleTestConnectorConfig()}
                connectionWizard={
                <ConnectionWizard
                  key={`${selectedOrganizationId}:${tenantEpoch}`}
                  connectorConfig={googleWorkspaceConnectorConfig}
                  organizationSelected={Boolean(selectedOrganizationId)}
                  canManageCredentials={canManageConnectorCredentials}
                  displayName={connectorDisplayName}
                  primaryDomain={connectorPrimaryDomain}
                  adminSubjectEmail={connectorAdminSubjectEmail}
                  notes={connectorNotes}
                  isSaving={isConnectorSaving}
                  isTesting={isConnectorTesting}
                  feedback={connectorFeedback}
                  onDisplayNameChange={setConnectorDisplayName}
                  onPrimaryDomainChange={setConnectorPrimaryDomain}
                  onAdminSubjectEmailChange={setConnectorAdminSubjectEmail}
                  onNotesChange={setConnectorNotes}
                  onSave={handleSaveConnectorConfig}
                  onTest={handleTestConnectorConfig}
                  onReload={() => loadOrganizationConnectorConfigs(selectedOrganizationId, true)}
                  onCredentialFeedback={setConnectorFeedback}
                />
                }
                gmailAuthorization={
                  <GmailDelegationAuthorization connectorConfig={googleWorkspaceConnectorConfig} />
                }
              />
            ) : currentRoute.id === "users" || currentRoute.id === "userLookup" ? (
                <UserDirectoryAdministration
                  key={`${selectedOrganizationId}:${tenantEpoch}`}
                  organizationId={selectedOrganizationId}
                  organizationName={selectedOrganization?.name ?? null}
                  connectorConfig={googleWorkspaceConnectorConfig}
                  canSearch={canOperateConnector}
                  canManageDelegates={canManageConnectorCredentials}
                  view={currentRoute.id === "users" ? "directory" : "lookup"}
                  hideNavigation
                  onViewChange={(view) =>
                    navigate(view === "directory" ? appRoutes.users.path : appRoutes.userLookup.path)
                  }
                  onOpenGroup={(groupEmail) => {
                    setGroupNavigationTarget((current) => ({
                      organizationId: selectedOrganizationId,
                      groupEmail,
                      requestId: (current?.requestId ?? 0) + 1
                    }));
                    navigate(appRoutes.groups.path);
                  }}
                />
            ) : currentRoute.id === "groups" ? (
                <GroupManagement
                  key={`${selectedOrganizationId}:${tenantEpoch}`}
                  organizationId={selectedOrganizationId}
                  canSearch={canOperateConnector}
                  canMutate={canManageConnectorCredentials}
                  initialGroupEmail={activeGroupNavigation?.groupEmail}
                  navigationRequestId={activeGroupNavigation?.requestId}
                />
            ) : currentRoute.id === "domains" ? (
                <DomainsInventory
                  key={`${selectedOrganizationId}:${tenantEpoch}:domains`}
                  organizationId={selectedOrganizationId}
                  organizationName={selectedOrganization?.name ?? null}
                  connectorConfig={googleWorkspaceConnectorConfig}
                  canRead={canOperateConnector}
                />
            ) : currentRoute.id === "adminRoles" ? (
                <AdminRolesInventory
                  key={`${selectedOrganizationId}:${tenantEpoch}:admin-roles`}
                  organizationId={selectedOrganizationId}
                  organizationName={selectedOrganization?.name ?? null}
                  connectorConfig={googleWorkspaceConnectorConfig}
                  canRead={canOperateConnector}
                />
            ) : currentRoute.id === "orgUnits" ? (
                <OrganizationalUnits
                  key={`${selectedOrganizationId}:${tenantEpoch}`}
                  organizationId={selectedOrganizationId}
                  organizationName={selectedOrganization?.name ?? null}
                  connectorConfig={googleWorkspaceConnectorConfig}
                  canRead={canOperateConnector}
                  canCreate={canManageConnectorCredentials}
                />
            ) : currentRoute.id === "delegations" ? (
              <GmailDelegationManagement
                key={`${selectedOrganizationId}:${tenantEpoch}:delegations`}
                organizationId={selectedOrganizationId}
                organizationName={selectedOrganization?.name ?? null}
                connectorConfig={googleWorkspaceConnectorConfig}
                canSearch={canOperateConnector}
                canManageDelegates={canManageConnectorCredentials}
              />
            ) : null}
          </article>

          {DEMO_FEATURES_ENABLED && (
          <article className={sectionClass("google-workspace", "panel compact-panel google-workspace-info")}>
            <div className="panel-heading">
              <span className="step-number">S</span>
              <div>
                <h2>Mock scan en check catalog</h2>
                <p>Security scans remain mock-only; user lookup above uses the real Directory API.</p>
              </div>
            </div>

            <div className="google-workspace-explainer">
              <article>
                <strong>Connector configuration</strong>
                <span>Secure read-only Directory connection; credentials remain server-side.</span>
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
              <p>User lookup is real. This separate mock scan still creates demo findings only.</p>

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
          )}

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
        <PlatformAdministration
          overview={platformAdminOverview}
          loading={isPlatformAdminOverviewLoading}
          error={platformAdminOverviewError}
          demoFeaturesEnabled={DEMO_FEATURES_ENABLED}
          onRefresh={() => void loadPlatformAdminOverview()}
        />
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
      </>
      )}
    </AppShell>
  );
}

export default App;
