import { Building2, ClipboardList, Plus, Save, ShieldAlert } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  createAssessment,
  createFinding,
  createOrganization,
  listAssessments,
  listFindings,
  listOrganizations
} from "./api/client";
import type { Assessment, Finding, FindingCreate, Organization } from "./types";

type DreadScoreKey =
  | "dread_damage"
  | "dread_reproducibility"
  | "dread_exploitability"
  | "dread_affected_users"
  | "dread_discoverability";

const initialFinding: FindingCreate = {
  title: "",
  description: "",
  affected_asset: "",
  status: "open",
  mitigation: "",
  dread_damage: 5,
  dread_reproducibility: 5,
  dread_exploitability: 5,
  dread_affected_users: 5,
  dread_discoverability: 5
};

const dreadControls: Array<{ key: DreadScoreKey; label: string }> = [
  { key: "dread_damage", label: "Damage" },
  { key: "dread_reproducibility", label: "Reproducibility" },
  { key: "dread_exploitability", label: "Exploitability" },
  { key: "dread_affected_users", label: "Affected users" },
  { key: "dread_discoverability", label: "Discoverability" }
];

function App() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [selectedAssessmentId, setSelectedAssessmentId] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [organizationDescription, setOrganizationDescription] = useState("");
  const [assessmentTitle, setAssessmentTitle] = useState("");
  const [assessmentScope, setAssessmentScope] = useState("");
  const [finding, setFinding] = useState<FindingCreate>(initialFinding);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const selectedOrganization = useMemo(
    () => organizations.find((organization) => organization.id === selectedOrganizationId),
    [organizations, selectedOrganizationId]
  );
  const selectedAssessment = useMemo(
    () => assessments.find((assessment) => assessment.id === selectedAssessmentId),
    [assessments, selectedAssessmentId]
  );

  const previewScore = useMemo(() => {
    const total =
      finding.dread_damage +
      finding.dread_reproducibility +
      finding.dread_exploitability +
      finding.dread_affected_users +
      finding.dread_discoverability;
    return (total / 5).toFixed(2);
  }, [finding]);

  async function refreshOrganizations(preferredId?: string) {
    const items = await listOrganizations();
    setOrganizations(items);
    setSelectedOrganizationId(preferredId ?? items[0]?.id ?? "");
  }

  async function refreshAssessments(organizationId: string, preferredId?: string) {
    const items = await listAssessments(organizationId);
    setAssessments(items);
    setSelectedAssessmentId(preferredId ?? items[0]?.id ?? "");
  }

  async function refreshFindings(assessmentId: string) {
    const items = await listFindings(assessmentId);
    setFindings(items);
  }

  useEffect(() => {
    refreshOrganizations().catch((loadError: Error) => setError(loadError.message));
  }, []);

  useEffect(() => {
    if (!selectedOrganizationId) {
      setAssessments([]);
      setSelectedAssessmentId("");
      return;
    }

    refreshAssessments(selectedOrganizationId).catch((loadError: Error) => setError(loadError.message));
  }, [selectedOrganizationId]);

  useEffect(() => {
    if (!selectedAssessmentId) {
      setFindings([]);
      return;
    }

    refreshFindings(selectedAssessmentId).catch((loadError: Error) => setError(loadError.message));
  }, [selectedAssessmentId]);

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    try {
      const organization = await createOrganization({
        name: organizationName,
        description: organizationDescription || null
      });
      setOrganizationName("");
      setOrganizationDescription("");
      setNotice("Organisatie aangemaakt.");
      await refreshOrganizations(organization.id);
    } catch (submitError) {
      setError((submitError as Error).message);
    }
  }

  async function handleCreateAssessment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!selectedOrganizationId) {
      setError("Selecteer eerst een organisatie.");
      return;
    }

    try {
      const assessment = await createAssessment(selectedOrganizationId, {
        title: assessmentTitle,
        scope_summary: assessmentScope || null
      });
      setAssessmentTitle("");
      setAssessmentScope("");
      setNotice("Assessment gestart.");
      await refreshAssessments(selectedOrganizationId, assessment.id);
    } catch (submitError) {
      setError((submitError as Error).message);
    }
  }

  async function handleCreateFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!selectedAssessmentId) {
      setError("Selecteer eerst een assessment.");
      return;
    }

    try {
      await createFinding(selectedAssessmentId, {
        ...finding,
        description: finding.description || null,
        affected_asset: finding.affected_asset || null,
        mitigation: finding.mitigation || null
      });
      setFinding(initialFinding);
      setNotice("Finding toegevoegd.");
      await refreshFindings(selectedAssessmentId);
    } catch (submitError) {
      setError((submitError as Error).message);
    }
  }

  function updateFindingScore(key: DreadScoreKey, value: number) {
    setFinding((current) => ({ ...current, [key]: value }));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">MVP foundation</span>
          <h1>DREAD Risk Assessment</h1>
        </div>
        <div className="status-pill" aria-live="polite">
          {selectedOrganization?.name ?? "Geen organisatie"}
        </div>
      </header>

      {(error || notice) && (
        <section className={error ? "message error" : "message success"}>
          {error || notice}
        </section>
      )}

      <section className="workspace-grid">
        <div className="panel">
          <div className="panel-heading">
            <Building2 aria-hidden="true" />
            <h2>Organisatie</h2>
          </div>

          <form className="form-stack" onSubmit={handleCreateOrganization}>
            <label>
              Naam
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
                rows={3}
              />
            </label>
            <button type="submit" title="Organisatie aanmaken">
              <Plus aria-hidden="true" />
              Aanmaken
            </button>
          </form>

          <label className="selector">
            Actieve organisatie
            <select
              value={selectedOrganizationId}
              onChange={(event) => setSelectedOrganizationId(event.target.value)}
            >
              <option value="">Selecteer</option>
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <ClipboardList aria-hidden="true" />
            <h2>Assessment</h2>
          </div>

          <form className="form-stack" onSubmit={handleCreateAssessment}>
            <label>
              Titel
              <input
                value={assessmentTitle}
                onChange={(event) => setAssessmentTitle(event.target.value)}
                placeholder="Q3 identity review"
                required
              />
            </label>
            <label>
              Scope
              <textarea
                value={assessmentScope}
                onChange={(event) => setAssessmentScope(event.target.value)}
                rows={3}
              />
            </label>
            <button type="submit" title="Assessment starten">
              <Save aria-hidden="true" />
              Starten
            </button>
          </form>

          <label className="selector">
            Actief assessment
            <select
              value={selectedAssessmentId}
              onChange={(event) => setSelectedAssessmentId(event.target.value)}
            >
              <option value="">Selecteer</option>
              {assessments.map((assessment) => (
                <option key={assessment.id} value={assessment.id}>
                  {assessment.title}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="panel finding-panel">
          <div className="panel-heading">
            <ShieldAlert aria-hidden="true" />
            <h2>Finding</h2>
          </div>

          <form className="finding-form" onSubmit={handleCreateFinding}>
            <label>
              Titel
              <input
                value={finding.title}
                onChange={(event) => setFinding((current) => ({ ...current, title: event.target.value }))}
                placeholder="Onvoldoende MFA dekking"
                required
              />
            </label>
            <label>
              Asset
              <input
                value={finding.affected_asset ?? ""}
                onChange={(event) =>
                  setFinding((current) => ({ ...current, affected_asset: event.target.value }))
                }
              />
            </label>
            <label className="wide">
              Beschrijving
              <textarea
                value={finding.description ?? ""}
                onChange={(event) =>
                  setFinding((current) => ({ ...current, description: event.target.value }))
                }
                rows={3}
              />
            </label>
            <label className="wide">
              Mitigatie
              <textarea
                value={finding.mitigation ?? ""}
                onChange={(event) =>
                  setFinding((current) => ({ ...current, mitigation: event.target.value }))
                }
                rows={3}
              />
            </label>

            <div className="score-grid wide">
              {dreadControls.map((control) => (
                <label className="score-control" key={control.key}>
                  <span>
                    {control.label}
                    <strong>{String(finding[control.key])}</strong>
                  </span>
                  <input
                    type="range"
                    min="0"
                    max="10"
                    value={Number(finding[control.key])}
                    onChange={(event) => updateFindingScore(control.key, Number(event.target.value))}
                  />
                </label>
              ))}
            </div>

            <div className="form-footer wide">
              <output>DREAD {previewScore}</output>
              <button type="submit" title="Finding opslaan">
                <Plus aria-hidden="true" />
                Toevoegen
              </button>
            </div>
          </form>
        </div>

        <section className="findings-list">
          <div className="list-heading">
            <h2>{selectedAssessment?.title ?? "Findings"}</h2>
            <span>{findings.length} totaal</span>
          </div>

          {findings.length === 0 ? (
            <p className="empty-state">Geen findings geregistreerd.</p>
          ) : (
            findings.map((item) => (
              <article className="finding-row" key={item.id}>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.affected_asset ?? "Geen asset opgegeven"}</p>
                </div>
                <strong>{item.risk_score.toFixed(2)}</strong>
              </article>
            ))
          )}
        </section>
      </section>
    </main>
  );
}

export default App;
