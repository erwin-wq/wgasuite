import {
  Activity,
  AlertCircle,
  BadgeCheck,
  Building2,
  CheckCircle2,
  ClipboardList,
  Database,
  Flag,
  Layers3,
  Loader2,
  Plus,
  ShieldAlert,
  Target,
  TrendingUp
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  createAssessment,
  createAsset,
  createFinding,
  createOrganization,
  listAssessments,
  listAssets,
  listFindings,
  listOrganizations
} from "./api/client";
import type {
  Assessment,
  Asset,
  DreadScoreCreate,
  Finding,
  FindingCreate,
  Organization
} from "./types";

type DreadScoreKey = keyof DreadScoreCreate;
type Feedback = { type: "success" | "error"; message: string } | null;
type SavingTarget = "organization" | "assessment" | "asset" | "finding" | null;

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

function App() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [selectedAssessmentId, setSelectedAssessmentId] = useState("");
  const [selectedAssetId, setSelectedAssetId] = useState("");
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
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<SavingTarget>(null);

  const selectedOrganization = useMemo(
    () => organizations.find((organization) => organization.id === selectedOrganizationId),
    [organizations, selectedOrganizationId]
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

  const canCreateAssessment = Boolean(selectedOrganizationId && assessmentTitle.trim());
  const canCreateAsset = Boolean(selectedOrganizationId && assetName.trim());
  const canCreateFinding = Boolean(selectedAssessmentId && findingTitle.trim());

  const loadWorkspace = useCallback(
    async (preferredOrganizationId?: string, preferredAssessmentId?: string) => {
      setIsLoading(true);
      try {
        const [loadedOrganizations, loadedAssessments, loadedAssets, loadedFindings] =
          await Promise.all([listOrganizations(), listAssessments(), listAssets(), listFindings()]);

        setOrganizations(loadedOrganizations);
        setAssessments(loadedAssessments);
        setAssets(loadedAssets);
        setFindings(loadedFindings);

        const nextOrganizationId = preferredOrganizationId ?? loadedOrganizations[0]?.id ?? "";
        const nextAssessmentId =
          preferredAssessmentId ??
          loadedAssessments.find((assessment) => assessment.organization_id === nextOrganizationId)
            ?.id ??
          "";

        setSelectedOrganizationId(nextOrganizationId);
        setSelectedAssessmentId(nextAssessmentId);
      } catch (loadError) {
        setFeedback({
          type: "error",
          message: `Backend data laden is mislukt: ${(loadError as Error).message}`
        });
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (!selectedOrganizationId) {
      setSelectedAssessmentId("");
      setSelectedAssetId("");
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
        description: organizationDescription.trim() || null
      });
      setOrganizationName("");
      setOrganizationDescription("");
      setSelectedOrganizationId(organization.id);
      setFeedback({ type: "success", message: "Organisatie aangemaakt." });
      await loadWorkspace(organization.id);
    } catch (submitError) {
      setFeedback({ type: "error", message: (submitError as Error).message });
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
      await loadWorkspace(selectedOrganizationId, assessment.id);
    } catch (submitError) {
      setFeedback({ type: "error", message: (submitError as Error).message });
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
      await loadWorkspace(selectedOrganizationId, selectedAssessmentId);
      setSelectedAssetId(asset.id);
    } catch (submitError) {
      setFeedback({ type: "error", message: (submitError as Error).message });
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
      await loadWorkspace(selectedOrganizationId, selectedAssessmentId);
    } catch (submitError) {
      setFeedback({ type: "error", message: (submitError as Error).message });
    } finally {
      setSaving(null);
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
        <div className="hero-status" aria-live="polite">
          <BadgeCheck aria-hidden="true" />
          {isLoading ? "Data laden" : selectedOrganization?.name ?? "Geen organisatie geselecteerd"}
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
          <Building2 aria-hidden="true" />
          <div>
            <span className="metric-label">Actieve organisatie</span>
            <strong className="metric-value">{selectedOrganization?.name ?? "Niet gekozen"}</strong>
          </div>
        </article>
        <article className="metric-card">
          <ClipboardList aria-hidden="true" />
          <div>
            <span className="metric-label">Actief assessment</span>
            <strong className="metric-value">{selectedAssessment?.title ?? "Niet gekozen"}</strong>
          </div>
        </article>
        <article className="metric-card">
          <Flag aria-hidden="true" />
          <div>
            <span className="metric-label">Findings</span>
            <strong className="metric-value metric-number">{assessmentFindings.length}</strong>
          </div>
        </article>
        <article className="metric-card">
          <TrendingUp aria-hidden="true" />
          <div>
            <span className="metric-label">Gemiddelde score</span>
            <strong className="metric-value metric-number">{formatScore(averageRiskScore)}</strong>
          </div>
        </article>
        <article className="metric-card">
          <ShieldAlert aria-hidden="true" />
          <div>
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
        <article className="panel compact-panel">
          <div className="panel-heading">
            <span className="step-number">1</span>
            <div>
              <h2>Organisatie</h2>
              <p>Kies een bestaande organisatie of maak een nieuwe aan.</p>
            </div>
          </div>

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
              disabled={organizations.length === 0}
            >
              <option value="">Selecteer organisatie</option>
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
                </option>
              ))}
            </select>
          </label>
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
              <p>{selectedAssessment?.title ?? "Geen assessment geselecteerd"}</p>
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
                  <div>
                    <h3>{finding.title}</h3>
                    <p>{finding.description ?? "Geen beschrijving opgegeven."}</p>
                  </div>
                  <span className="asset-name">{asset?.name ?? "Niet gekoppeld"}</span>
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
