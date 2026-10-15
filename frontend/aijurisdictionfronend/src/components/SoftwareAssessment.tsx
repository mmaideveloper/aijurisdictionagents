import React from "react";
import { chatApiRuntimeConfig, parseApiErrorResponse } from "../api/chatClient";
import { correlationHeaders } from "../api/correlation";
import { useAuth } from "../auth/webAuth";
import { useCases } from "../state/CaseProvider";

type Action = { action_id: string; finding: string; classification: string; evidence_id?: string;
  excerpt: string; source_ids: string[]; priority: string; action: string; owner: string;
  verification: string; status: "open" | "evidence_requested" | "ready_for_review" | "verified" };
type Assessment = { assessment_id: string; revision: number; warning: string; created_at: string;
  provider: string; model: string; fallback_reason: string; coverage: string[];
  documents: { evidence_id: string; filename: string; version: number; section: string; uncertainty: string }[];
  sources: { source_id: string; title: string; provision: string; source_url: string }[];
  output: { summary: string; questions: string[]; actions: Action[];
    applicability: { regime: string; status: string; reason: string }[];
    supplier_checklist: { title: string; category: string; purpose: string; owner: string; acceptance_criteria: string; status: string }[];
    verification_plan: { title: string; kind: string; method: string; acceptance_criteria: string; reviewer: string }[];
    recommended_documents: string[]; architecture_recommendations: string[]; responsibilities: string[]; release_blockers: string[] };
  drafts: { title: string; text: string; warning: string; provider?: string; model?: string }[] };
const booleanQuestions = {
  personal_data: "Processes personal data?", health_data: "Processes health, genetic or biometric data?",
  uses_ai: "Uses AI?", medical_purpose: "Has an intended medical purpose?",
  specimen_analysis: "Analyses human specimen/laboratory information?", automated_decisions: "Makes decisions without meaningful human review?"
};

export function SoftwareAssessment({ selectedModelProfileId }: { selectedModelProfileId?: string }) {
  const { activeCase, uploadDocumentsToCase } = useCases();
  const { user } = useAuth();
  const [facts, setFacts] = React.useState<Record<string, string>>({ description: "", intended_purpose: "", users: "", lifecycle: "", role: "", suppliers: "" });
  const [flags, setFlags] = React.useState<Record<string, string>>({});
  const [selected, setSelected] = React.useState<string[]>([]);
  const [external, setExternal] = React.useState(false);
  const [assessment, setAssessment] = React.useState<Assessment | null>(null);
  const [history, setHistory] = React.useState<{ assessment_id: string; created_at: string }[]>([]);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [opened, setOpened] = React.useState(false);
  const config = chatApiRuntimeConfig();
  const request = React.useCallback(async (suffix: string, method = "GET", body?: unknown) => {
    if (!user?.deviceId || !user.deviceAuthToken || !activeCase) throw new Error("Sign in and select a case first.");
    const response = await fetch(`${config.baseUrl}/v1/cases/${encodeURIComponent(activeCase.id)}/software-assessments${suffix}${suffix.includes("?") ? "&" : "?"}user_id=${encodeURIComponent(user.userId)}`, {
      method, headers: { ...correlationHeaders(), "x-api-key": config.apiKey, "Content-Type": "application/json",
        "x-jurisdigta-device-id": user.deviceId, "x-jurisdigta-device-token": user.deviceAuthToken },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!response.ok) throw new Error((await parseApiErrorResponse(response)).message);
    return response;
  }, [activeCase, config.apiKey, config.baseUrl, user]);
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await operation(); } catch (failure) { setError(failure instanceof Error ? failure.message : "Assessment request failed."); }
    finally { setBusy(false); }
  };
  React.useEffect(() => {
    if (!opened) return;
    let current = true;
    void request("").then(response => response.json()).then(result => { if (current) setHistory(result.items); })
      .catch(failure => { if (current) setError(failure instanceof Error ? failure.message : "Cannot load assessments."); });
    return () => { current = false; };
  }, [opened, request]);
  const start = () => perform(async () => {
    const booleans = Object.fromEntries(Object.keys(booleanQuestions).map(key => [key, flags[key] === "yes" ? true : flags[key] === "no" ? false : null]));
    const result: Assessment = await (await request("", "POST", { request_id: crypto.randomUUID(), facts: { ...facts, ...booleans },
      document_ids: selected, external_acknowledged: external, selected_model_profile_id: selectedModelProfileId ?? null })).json();
    setAssessment(result); setHistory(await (await request("")).json().then(value => value.items));
  });
  const decide = (action: Action, status: Action["status"]) => perform(async () => {
    if (!assessment) return;
    setAssessment(await (await request(`/${assessment.assessment_id}/actions/${encodeURIComponent(action.action_id)}`, "PATCH", {
      expected_revision: assessment.revision, status, evidence_note: note, evidence_document_ids: status === "verified" ? selected : []
    })).json());
  });
  const download = () => perform(async () => {
    if (!assessment) return;
    const response = await request(`/${assessment.assessment_id}/export?revision=${assessment.revision}`);
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a");
    link.href = url; link.download = `software-assessment-v${assessment.revision}.pdf`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  if (!activeCase) return null;
  return <details className="document-review-panel" onToggle={event => setOpened(event.currentTarget.open)}>
    <summary>Software regulatory assessment · SK + EU</summary>
    {opened && <>
    <p>Assess software and supplier documentation, including medical/IVD software. Preliminary findings require expert review.</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy}>
      <legend>Software facts</legend>
      {Object.keys(facts).map(key => <label key={key} style={{ display: "block" }}>{key.replaceAll("_", " ")}
        <textarea aria-label={key} value={facts[key]} maxLength={key === "description" ? 8000 : key === "role" || key === "users" ? 1000 : key === "lifecycle" ? 500 : 2000}
          onChange={event => setFacts({ ...facts, [key]: event.target.value })} />
      </label>)}
      {Object.entries(booleanQuestions).map(([key, label]) => <label key={key} style={{ display: "block" }}>{label}
        <select aria-label={label} value={flags[key] ?? ""} onChange={event => setFlags({ ...flags, [key]: event.target.value })}>
          <option value="">Unknown — ask me</option><option value="yes">Yes</option><option value="no">No</option>
        </select>
      </label>)}
      <label>Upload supplier/software documents<input type="file" multiple accept=".pdf,.docx,.txt,.md,.json,.csv,.html,.xml,.jpg,.jpeg,.png"
        onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = "";
          if (files.length) void perform(async () => { await uploadDocumentsToCase(activeCase.id, files); }); }} /></label>
      <p>Select up to 10 original documents. Scans without embedded text remain an explicit evidence gap.</p>
      {activeCase.documents.filter(doc => doc.kind === "uploaded").map(doc => <label key={doc.id} style={{ display: "block" }}>
        <input type="checkbox" checked={selected.includes(doc.id)} disabled={!selected.includes(doc.id) && selected.length >= 10}
          onChange={event => setSelected(event.target.checked ? [...selected, doc.id] : selected.filter(id => id !== doc.id))} />{doc.originalFilename}
      </label>)}
      <label><input type="checkbox" checked={external} onChange={event => setExternal(event.target.checked)} />I acknowledge processing selected confidential documents and software facts by the configured external AI provider.</label>
      <button type="button" disabled={(facts.description ?? "").trim().length < 10} onClick={() => void start()}>Assess / reassess software</button>
    </fieldset>
    {busy && <p role="status">Processing assessment…</p>}
    {history.length > 0 && <label>Previous assessments<select value={assessment?.assessment_id ?? ""} disabled={busy}
      onChange={event => { const id = event.target.value; if (id) void perform(async () => setAssessment(await (await request(`/${id}`)).json())); }}>
      <option value="">Select an assessment</option>{history.map(item => <option key={item.assessment_id} value={item.assessment_id}>{item.created_at}</option>)}
    </select></label>}
    {assessment && <>
      <h3>Assessment v{assessment.revision}</h3><p role="status">{assessment.warning}</p>
      <p>Model: {assessment.provider} / {assessment.model} {assessment.fallback_reason && `· Fallback: ${assessment.fallback_reason}`}</p>
      <p>{assessment.output.summary}</p>{assessment.coverage.map((text, i) => <p key={i}>{text}</p>)}
      {assessment.output.questions.map((question, i) => <p key={i}>Question: {question}</p>)}
      <h4>Applicable regulations</h4>{assessment.output.applicability.map((item, i) => <p key={i}>{item.regime} · {item.status} · {item.reason}</p>)}
      <h4>Required actions</h4><label>Evidence/reviewer note<textarea aria-label="Evidence/reviewer note" value={note} maxLength={2000} onChange={event => setNote(event.target.value)} /></label>
      {assessment.output.actions.length === 0 && <p>No grounded actions yet. This does not establish compliance.</p>}
      {assessment.output.actions.map(action => { const evidence = assessment.documents.find(item => item.evidence_id === action.evidence_id);
        return <article key={action.action_id}>
          <h4>{action.priority} · {action.finding}</h4>
          {evidence && <p>{evidence.filename} v{evidence.version}, {evidence.section} · {evidence.uncertainty}</p>}
          <blockquote>{action.excerpt}</blockquote><p>{action.classification} · {action.status}</p>
          <p>Action: {action.action}</p><p>Owner: {action.owner}</p><p>Verification: {action.verification}</p>
          {action.source_ids.map(id => { const source = assessment.sources.find(item => item.source_id === id); return source && <p key={id}><a href={source.source_url} target="_blank" rel="noreferrer">{source.title} · {source.provision}</a></p>; })}
          <select aria-label={`Status ${action.action_id}`} value={action.status} disabled={busy || note.trim().length < 10}
            onChange={event => void decide(action, event.target.value as Action["status"])}>
            <option value="open">Open</option><option value="evidence_requested">Evidence requested</option><option value="ready_for_review">Ready for review</option>
            <option value="verified" disabled={action.status !== "ready_for_review" && action.status !== "verified"}>Verified by reviewer</option>
          </select>
        </article>; })}
      <h4>Supplier documents</h4>{assessment.output.supplier_checklist.map((item, i) => <article key={i}><p><strong>{item.title} · {item.category}</strong><br />{item.purpose} · Owner: {item.owner}<br />Acceptance: {item.acceptance_criteria}</p>
        <select aria-label={`Supplier status ${i}`} value={item.status} disabled={busy || note.trim().length < 10} onChange={event => { const status = event.target.value; void perform(async () => {
          setAssessment(await (await request(`/${assessment.assessment_id}/supplier-checklist/${i}`, "PATCH", { expected_revision: assessment.revision, status, evidence_note: note })).json());
        }); }}><option value="missing">Missing</option><option value="received">Received</option><option value="reviewed" disabled={item.status !== "received" && item.status !== "reviewed"}>Reviewed</option></select>
      </article>)}
      <h4>Verification plan</h4>{assessment.output.verification_plan.map((item, i) => <p key={i}><strong>{item.title} · {item.kind}</strong><br />{item.method}<br />Acceptance: {item.acceptance_criteria} · Reviewer: {item.reviewer}</p>)}
      <h4>Architecture, responsibilities and release blockers</h4>{[...assessment.output.architecture_recommendations, ...assessment.output.responsibilities, ...assessment.output.release_blockers].map((text, i) => <p key={i}>{text}</p>)}
      <h4>Prepare short documentation</h4>{assessment.output.recommended_documents.map(title => <button key={title} disabled={busy} type="button" onClick={() => void perform(async () => {
        setAssessment(await (await request(`/${assessment.assessment_id}/drafts`, "POST", { expected_revision: assessment.revision, document_title: title, external_acknowledged: external })).json());
      })}>Draft {title}</button>)}
      {assessment.drafts.map((draft, i) => <DraftEditor key={`${assessment.assessment_id}-${i}`} draft={draft} busy={busy} save={text => perform(async () => {
        setAssessment(await (await request(`/${assessment.assessment_id}/drafts/${i}`, "PATCH", { expected_revision: assessment.revision, text })).json());
      })} />)}
      <button disabled={busy} type="button" onClick={() => void download()}>Download assessment and drafts PDF</button>
      <button disabled={busy} type="button" onClick={() => void perform(async () => {
        await request(`/${assessment.assessment_id}`, "DELETE"); setAssessment(null); setHistory(await (await request("")).json().then(value => value.items));
      })}>Delete this assessment</button>
    </>}
    </>}
  </details>;
}

function DraftEditor({ draft, busy, save }: { draft: { title: string; text: string; warning: string; provider?: string; model?: string }; busy: boolean; save: (text: string) => Promise<void> }) {
  const [text, setText] = React.useState(draft.text);
  React.useEffect(() => setText(draft.text), [draft.text]);
  return <article><h4>{draft.title}</h4><p>{draft.warning}</p>{draft.provider && <p>Draft model: {draft.provider} / {draft.model}</p>}<textarea aria-label={`Draft ${draft.title}`} value={text} maxLength={12000} disabled={busy} onChange={event => setText(event.target.value)} />
    <button type="button" disabled={busy || !text.trim()} onClick={() => void save(text)}>Save edited draft</button></article>;
}
