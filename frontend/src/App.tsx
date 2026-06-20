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
  getStoredAuthToken,
  listAssessmentScanRuns,
  listAssessments,
  listAssets,
  listCustomers,
  listFindings,
  listGoogleWorkspaceChecks,
  listOrganizations,
  login,
  runMockGoogleWorkspaceScan,
  setStoredAuthToken
} from "./api/client";
import type {
  Assessment,
  AssessmentReport,
  Asset,
  Customer,
  DreadScoreCreate,
  Finding,
  FindingCreate,
  GoogleWorkspaceCheck,
  Organization,
  ScanRun,
  User
} from "./types";

type DreadScoreKey = keyof DreadScoreCreate;
type Feedback = { type: "success" | "error"; message: string } | null;
type SavingTarget = "customer" | "organization" | "assessment" | "asset" | "finding" | null;
type ActiveView = "workspace" | "report";

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
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [googleWorkspaceChecks, setGoogleWorkspaceChecks] = useState<GoogleWorkspaceCheck[]>([]);
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
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loginEmail, setLoginEmail] = useState("admin@example.local");
  const [loginPassword, setLoginPassword] = useState("ChangeMe123!");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [isLoginSaving, setIsLoginSaving] = useState(false);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [isScanLoading, setIsScanLoading] = useState(false);
  const [isScanRunning, setIsScanRunning] = useState(false);
  const [showGoogleWorkspaceChecks, setShowGoogleWorkspaceChecks] = useState(false);
  const [saving, setSaving] = useState<SavingTarget>(null);
  const [activeView, setActiveView] = useState<ActiveView>("workspace");
  const [report, setReport] = useState<AssessmentReport | null>(null);

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

  const resetSession = useCallback((message?: string) => {
    clearStoredAuthToken();
    setCurrentUser(null);
    setReport(null);
    setActiveView("workspace");
    setCustomers([]);
    setOrganizations([]);
    setAssessments([]);
    setAssets([]);
    setFindings([]);
    setScanRuns([]);
    setGoogleWorkspaceChecks([]);
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
    setLoginPassword("ChangeMe123!");
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
      setActiveView("report");
    } catch (reportError) {
      handleRequestError(reportError);
    } finally {
      setIsReportLoading(false);
    }
  }

  function handleBackToWorkspace() {
    setActiveView("workspace");
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

  if (isAuthLoading) {
    return (
      <main className="app-shell login-shell">
        <section className="login-panel">
          <LockKeyhole aria-hidden="true" />
          <h1>DREAD Risk Assessment</h1>
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
          <h1>DREAD Risk Assessment</h1>
          <p>
            Gebruik de lokale demo admin om de MVP auth foundation te testen. Dit is geen
            productie-authenticatie.
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
                placeholder="ChangeMe123!"
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

          <div className="demo-credentials">
            <span>Demo user</span>
            <strong>admin@example.local</strong>
            <span>Demo password</span>
            <strong>ChangeMe123!</strong>
          </div>
        </section>
      </main>
    );
  }

  if (activeView === "report") {
    return (
      <main className="app-shell report-shell">
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
              <h3>Rapport laden</h3>
            </div>
          ) : (
            <>
              <header className="report-header">
                <div>
                  <span className="eyebrow">Assessment export</span>
                  <h1>DREAD Risk Assessment Report</h1>
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
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <span className="eyebrow">Security risk workspace</span>
          <h1>DREAD Risk Assessment</h1>
          <p>
            Leg organisaties, assessments, assets en findings vast met een consistente DREAD-score.
          </p>
        </div>
        <div className="hero-side">
          <div className="hero-status" aria-live="polite">
            <BadgeCheck aria-hidden="true" />
            <span className="hero-status-name" title={activeOrganizationLabel}>
              {activeOrganizationLabel}
            </span>
          </div>
          <div className="user-session">
            <div>
              <span>Ingelogd als</span>
              <strong>{currentUser.full_name}</strong>
              <em>{currentUser.role}</em>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleLogout()}>
              <LogOut aria-hidden="true" />
              Logout
            </button>
          </div>
        </div>
      </header>

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

      <section className="summary-grid" aria-label="Assessment overzicht">
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
      </section>

      <section className="workflow-layout">
        <div className="setup-column">
          <article className="panel compact-panel customer-panel">
            <div className="panel-heading">
              <span className="step-number">A</span>
              <div>
                <h2>Klantbeheer</h2>
                <p>Customer hangt boven organizations en is alvast voorbereid voor klantbeheer.</p>
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

          <article className="panel compact-panel">
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

          <article className="panel compact-panel">
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

            <section className="mock-scan-panel" aria-label="Google Workspace scan">
              <div className="inline-heading">
                <ShieldAlert aria-hidden="true" />
                <h3>Google Workspace scan</h3>
              </div>
              <p>Mock scan - no real Google data is accessed.</p>

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

              <div className="check-catalog-panel">
                <div className="check-catalog-toolbar">
                  <div>
                    <strong>Check library</strong>
                    <span>
                      Deze checks zijn nu mock/demo. De echte Google API-koppeling wordt later per
                      check toegevoegd.
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
              </div>

              <div className="scan-run-list" aria-label="Recente scan runs">
                <div className="scan-run-list-heading">
                  <strong>Recente scan runs</strong>
                  {isScanLoading && <span>laden</span>}
                </div>
                {scanRuns.length === 0 ? (
                  <div className="mini-empty-state">Nog geen scan runs voor dit assessment.</div>
                ) : (
                  scanRuns.slice(0, 4).map((scanRun) => (
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
        </div>

        <article className="panel finding-panel composer-panel">
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

      <section className="findings-section">
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

      {isLoading && (
        <div className="loading-overlay" aria-live="polite">
          <Activity className="spin" aria-hidden="true" />
          Workspace laden
        </div>
      )}
    </main>
  );
}

export default App;
