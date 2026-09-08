import React from "react";
import { FaCheck, FaClone, FaLock, FaPlay, FaSearch, FaSyncAlt } from "react-icons/fa";

import {
  AdminAuthContext,
  FlowEvaluationRun,
  FlowEvaluationSuite,
  FlowPackCatalogItem,
  RegisteredCaseWorkflowGraph,
  createDraftFlowPackVersion,
  createFlowEvaluationRun,
  createFlowEvaluationSuite,
  fetchFlowEvaluationSuite,
  fetchFlowPackCatalog,
  lockFlowPackVersionForTesting,
  updateDraftFlowPackVersion
} from "../api/adminModelClient";
import { useLanguage } from "../components/LanguageProvider";

interface AdminFlowPackagesProps {
  adminAuth: AdminAuthContext;
  graphs: RegisteredCaseWorkflowGraph[];
  onStatus: (message: string) => void;
  onError: (message: string) => void;
}

interface DraftForm {
  domain: string;
  title: string;
  description: string;
  questionKind: string;
  legalDomain: string;
  requestedOutcome: string;
  positiveExamples: string;
  negativeExamples: string;
  definitionJson: string;
  clarificationPolicyJson: string;
}

const EMPTY_DRAFT: DraftForm = {
  domain: "",
  title: "",
  description: "",
  questionKind: "legal_question",
  legalDomain: "",
  requestedOutcome: "legal_information",
  positiveExamples: "",
  negativeExamples: "",
  definitionJson: "{}",
  clarificationPolicyJson: "{\n  \"on_low_confidence\": \"ask_user\"\n}"
};

const flowRef = (flow: FlowPackCatalogItem): string => `${flow.jurisdiction}|${flow.flow_key}|${flow.version}`;

const flowSupportsGraph = (flow: FlowPackCatalogItem, graphReference: string): boolean => {
  if (!graphReference) return true;
  const [graphKey, graphVersion] = graphReference.split("@");
  const definitionGraph = flow.definition.graph;
  const definitionGraphKey = flow.definition.graph_key;
  const definitionGraphVersion = flow.definition.graph_version;
  return (definitionGraph === graphReference || definitionGraph === graphKey)
    || (definitionGraphKey === graphKey
      && (definitionGraphVersion === undefined || String(definitionGraphVersion) === graphVersion));
};

const parseObject = (value: string, label: string): Record<string, unknown> => {
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
};

const parseArray = (value: string, label: string): unknown[] => {
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON array.`);
  }
  return parsed;
};

const lines = (value: string): string[] => value
  .split("\n")
  .map((item) => item.trim())
  .filter(Boolean);

const toDraft = (flow: FlowPackCatalogItem): DraftForm => ({
  domain: flow.domain ?? "",
  title: flow.title,
  description: flow.description,
  questionKind: flow.question_kind ?? "legal_question",
  legalDomain: flow.legal_domain ?? flow.domain ?? "",
  requestedOutcome: flow.requested_outcome ?? "legal_information",
  positiveExamples: (flow.positive_examples ?? []).join("\n"),
  negativeExamples: (flow.negative_examples ?? []).join("\n"),
  definitionJson: JSON.stringify(flow.definition, null, 2),
  clarificationPolicyJson: JSON.stringify(flow.clarification_policy ?? {}, null, 2)
});

const draftSnapshot = (flow: FlowPackCatalogItem | undefined): Record<string, unknown> => flow ? {
  title: flow.title,
  description: flow.description,
  domain: flow.domain,
  question_kind: flow.question_kind,
  legal_domain: flow.legal_domain,
  requested_outcome: flow.requested_outcome,
  positive_examples: flow.positive_examples,
  negative_examples: flow.negative_examples,
  clarification_policy: flow.clarification_policy,
  definition: flow.definition
} : {};

const AdminFlowPackages: React.FC<AdminFlowPackagesProps> = ({ adminAuth, graphs, onStatus, onError }) => {
  const { t } = useLanguage();
  const [flows, setFlows] = React.useState<FlowPackCatalogItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [selectedRef, setSelectedRef] = React.useState("");
  const [jurisdiction, setJurisdiction] = React.useState("SK");
  const [query, setQuery] = React.useState("");
  const [domainFilter, setDomainFilter] = React.useState("");
  const [kindFilter, setKindFilter] = React.useState("");
  const [outcomeFilter, setOutcomeFilter] = React.useState("");
  const [lifecycleFilter, setLifecycleFilter] = React.useState("");
  const [graphFilter, setGraphFilter] = React.useState("");
  const [draft, setDraft] = React.useState<DraftForm>(EMPTY_DRAFT);
  const [graphRef, setGraphRef] = React.useState("");
  const [validation, setValidation] = React.useState<string[]>([]);
  const [lockReason, setLockReason] = React.useState("");
  const [suite, setSuite] = React.useState<FlowEvaluationSuite | null>(null);
  const [suiteId, setSuiteId] = React.useState("");
  const [suiteKey, setSuiteKey] = React.useState("");
  const [suiteTitle, setSuiteTitle] = React.useState("");
  const [suiteThreshold, setSuiteThreshold] = React.useState("0.9");
  const [suiteRetention, setSuiteRetention] = React.useState("14");
  const [suiteCasesJson, setSuiteCasesJson] = React.useState("[]");
  const [syntheticConfirmed, setSyntheticConfirmed] = React.useState(false);
  const [evaluationMode, setEvaluationMode] = React.useState<"routing_only" | "full_graph">("routing_only");
  const [routingPolicyJson, setRoutingPolicyJson] = React.useState("{\n  \"confidence_threshold\": 0.85,\n  \"margin\": 0.15\n}");
  const [provider, setProvider] = React.useState("azurefoundry");
  const [model, setModel] = React.useState("");
  const [providerRoute, setProviderRoute] = React.useState("offline-admin-evaluation");
  const [observationsJson, setObservationsJson] = React.useState("[]");
  const [humanReviewed, setHumanReviewed] = React.useState(false);
  const [run, setRun] = React.useState<FlowEvaluationRun | null>(null);
  const [busy, setBusy] = React.useState<"" | "save" | "lock" | "suite" | "run">("");
  const pendingRunId = React.useRef("");
  const onErrorRef = React.useRef(onError);
  const translateRef = React.useRef(t);

  onErrorRef.current = onError;
  translateRef.current = t;

  const selected = flows.find((flow) => flowRef(flow) === selectedRef);
  const prior = selected
    ? flows.find((flow) => flow.flow_key === selected.flow_key && flow.jurisdiction === selected.jurisdiction && flow.version === selected.version - 1)
    : undefined;

  const loadFlows = React.useCallback(async () => {
    setLoading(true);
    onErrorRef.current("");
    try {
      const response = await fetchFlowPackCatalog(adminAuth, jurisdiction);
      setFlows(response.items);
      setSelectedRef((current) => response.items.some((flow) => flowRef(flow) === current)
        ? current
        : response.items[0] ? flowRef(response.items[0]) : "");
    } catch (reason) {
      onErrorRef.current(reason instanceof Error ? reason.message : translateRef.current("adminFlowPackagesLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [adminAuth, jurisdiction]);

  React.useEffect(() => {
    void loadFlows();
  }, [loadFlows]);

  React.useEffect(() => {
    if (!selected) return;
    setDraft(toDraft(selected));
    setValidation([]);
    setRun(null);
    pendingRunId.current = "";
    setSuiteCasesJson(JSON.stringify([{
      case_key: "synthetic-routing-case",
      mode: "routing_only",
      synthetic_input: { question: selected.positive_examples?.[0] ?? "Synthetic legal question" },
      expected_route: selected.flow_key,
      required_source_ids: [],
      human_review_required: true
    }], null, 2));
    setObservationsJson(JSON.stringify([{
      case_key: "synthetic-routing-case",
      actual_route: selected.flow_key,
      source_ids: [],
      schema_valid: true,
      provenance_valid: true,
      privacy_violation_count: 0,
      unsupported_auto_finalization: false,
      human_review_present: true
    }], null, 2));
  }, [selectedRef]); // eslint-disable-line react-hooks/exhaustive-deps

  const visibleFlows = React.useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return flows.filter((flow) => (
      (!normalized || `${flow.flow_key} ${flow.title} ${flow.description}`.toLowerCase().includes(normalized))
      && (!domainFilter || (flow.legal_domain ?? flow.domain) === domainFilter)
      && (!kindFilter || flow.question_kind === kindFilter)
      && (!outcomeFilter || flow.requested_outcome === outcomeFilter)
      && (!lifecycleFilter || flow.lifecycle_state === lifecycleFilter)
      && flowSupportsGraph(flow, graphFilter)
    ));
  }, [domainFilter, flows, graphFilter, kindFilter, lifecycleFilter, outcomeFilter, query]);

  const validateDraft = (): string[] => {
    const failures: string[] = [];
    if (!draft.title.trim() || !draft.description.trim() || !draft.domain.trim()) failures.push(t("adminFlowValidationIdentity"));
    if (!draft.questionKind.trim() || !draft.legalDomain.trim() || !draft.requestedOutcome.trim()) failures.push(t("adminFlowValidationRouting"));
    if (!lines(draft.positiveExamples).length) failures.push(t("adminFlowValidationExamples"));
    try { parseObject(draft.definitionJson, t("adminFlowDefinitionJson")); } catch (reason) { failures.push(String(reason)); }
    try {
      const policy = parseObject(draft.clarificationPolicyJson, t("adminFlowClarificationJson"));
      if (!policy.on_low_confidence) failures.push(t("adminFlowValidationOversight"));
    } catch (reason) { failures.push(String(reason)); }
    if (!graphs.some((graph) => `${graph.graph_key}@${graph.graph_version}` === graphRef)) failures.push(t("adminFlowValidationGraph"));
    setValidation(failures.length ? failures : [t("adminFlowValidationPassed")]);
    return failures;
  };

  const saveDraft = async () => {
    if (!selected || selected.lifecycle_state !== "draft" || validateDraft().length) return;
    setBusy("save");
    onError("");
    try {
      const updated = await updateDraftFlowPackVersion(adminAuth, selected.flow_key, selected.version, selected.jurisdiction, {
        domain: draft.domain.trim(), title: draft.title.trim(), description: draft.description.trim(),
        question_kind: draft.questionKind.trim(), legal_domain: draft.legalDomain.trim(),
        requested_outcome: draft.requestedOutcome.trim(),
        positive_examples: lines(draft.positiveExamples), negative_examples: lines(draft.negativeExamples),
        definition: parseObject(draft.definitionJson, t("adminFlowDefinitionJson")),
        clarification_policy: parseObject(draft.clarificationPolicyJson, t("adminFlowClarificationJson"))
      });
      setFlows((items) => items.map((item) => flowRef(item) === selectedRef ? updated : item));
      onStatus(t("adminFlowDraftSaved"));
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : t("adminSaveFailed"));
    } finally { setBusy(""); }
  };

  const cloneDraft = async () => {
    if (!selected) return;
    setBusy("save");
    onError("");
    try {
      const created = await createDraftFlowPackVersion(adminAuth, selected.flow_key, selected.jurisdiction);
      setFlows((items) => [created, ...items]);
      setSelectedRef(flowRef(created));
      onStatus(t("adminFlowDraftCloned"));
    } catch (reason) { onError(reason instanceof Error ? reason.message : t("adminSaveFailed")); }
    finally { setBusy(""); }
  };

  const lockDraft = async () => {
    if (!selected || selected.lifecycle_state !== "draft" || validateDraft().length || !lockReason.trim()) return;
    setBusy("lock");
    onError("");
    try {
      const locked = await lockFlowPackVersionForTesting(
        adminAuth, selected.flow_key, selected.version, selected.jurisdiction, lockReason
      );
      setFlows((items) => items.map((item) => flowRef(item) === selectedRef ? locked : item));
      setLockReason("");
      onStatus(t("adminFlowLocked"));
    } catch (reason) { onError(reason instanceof Error ? reason.message : t("adminSaveFailed")); }
    finally { setBusy(""); }
  };

  const createSuite = async () => {
    if (!selected || !syntheticConfirmed) return;
    setBusy("suite");
    onError("");
    try {
      const created = await createFlowEvaluationSuite(adminAuth, {
        suite_key: suiteKey.trim(), version: 1, jurisdiction: selected.jurisdiction,
        title: suiteTitle.trim(), synthetic_only: true, synthetic_data_confirmed: true,
        routing_accuracy_threshold: Number(suiteThreshold), retention_days: Number(suiteRetention),
        cases: parseArray(suiteCasesJson, t("adminFlowCasesJson"))
      });
      setSuite(created);
      setSuiteId(created.suite_id);
      onStatus(t("adminFlowSuiteCreated"));
    } catch (reason) { onError(reason instanceof Error ? reason.message : t("adminSaveFailed")); }
    finally { setBusy(""); }
  };

  const loadSuite = async () => {
    if (!suiteId.trim()) return;
    setBusy("suite");
    onError("");
    try { setSuite(await fetchFlowEvaluationSuite(adminAuth, suiteId.trim())); }
    catch (reason) { onError(reason instanceof Error ? reason.message : t("adminFlowSuiteLoadFailed")); }
    finally { setBusy(""); }
  };

  const runEvaluation = async () => {
    if (!selected || selected.lifecycle_state !== "test_ready" || !suite || !humanReviewed || !model.trim()) return;
    setBusy("run");
    onError("");
    try {
      const requestId = pendingRunId.current || (
        globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${selected.version}`
      );
      pendingRunId.current = requestId;
      const result = await createFlowEvaluationRun(adminAuth, {
        idempotency_key: `admin-ui-${requestId}`, synthetic_run_id: `synthetic-${requestId}`,
        suite_id: suite.suite_id, flow_key: selected.flow_key, flow_version: selected.version,
        jurisdiction: selected.jurisdiction, graph_version: graphRef,
        routing_policy: parseObject(routingPolicyJson, t("adminFlowRoutingPolicyJson")),
        provider: provider.trim(), model: model.trim(), provider_route: providerRoute.trim(),
        mode: evaluationMode, observations: parseArray(observationsJson, t("adminFlowObservationsJson"))
      });
      setRun(result);
      pendingRunId.current = "";
      await loadFlows();
      onStatus(result.status === "passed" ? t("adminFlowRunPassed") : t("adminFlowRunFailed"));
    } catch (reason) { onError(reason instanceof Error ? reason.message : t("adminSaveFailed")); }
    finally { setBusy(""); }
  };

  const domains = [...new Set(flows.map((flow) => flow.legal_domain ?? flow.domain).filter(Boolean))].sort();
  const kinds = [...new Set(flows.map((flow) => flow.question_kind).filter(Boolean))].sort();
  const outcomes = [...new Set(flows.map((flow) => flow.requested_outcome).filter(Boolean))].sort();
  const diff = selected && prior
    ? Object.entries(draftSnapshot(selected)).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(draftSnapshot(prior)[key]))
    : [];
  const editable = selected?.lifecycle_state === "draft";

  return (
    <section className="admin-grid admin-flow-packages">
      <section className="admin-panel admin-panel--wide">
        <div className="admin-section-heading">
          <div><h2>{t("adminFlowPackagesTitle")}</h2><p className="admin-muted">{t("adminFlowPackagesHelp")}</p></div>
          <button className="secondary-button" type="button" onClick={() => void loadFlows()} disabled={loading}>
            <FaSyncAlt aria-hidden="true" />{t("adminRefresh")}
          </button>
        </div>
        <p className="admin-alert"><strong>{t("adminFlowOfflineOnly")}</strong><span>{t("adminFlowPrivacyNote")}</span></p>
        <div className="admin-flow-filters">
          <label>{t("adminFlowJurisdiction")}<input value={jurisdiction} maxLength={8} onChange={(event) => setJurisdiction(event.target.value.toUpperCase())} /></label>
          <label>{t("adminFlowSearch")}<span className="admin-input-icon"><FaSearch aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} /></span></label>
          <label>{t("adminFlowDomain")}<select value={domainFilter} onChange={(event) => setDomainFilter(event.target.value)}><option value="">{t("adminFlowAll")}</option>{domains.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>{t("adminFlowQuestionKind")}<select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}><option value="">{t("adminFlowAll")}</option>{kinds.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>{t("adminFlowOutcome")}<select value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value)}><option value="">{t("adminFlowAll")}</option>{outcomes.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>{t("adminFlowLifecycle")}<select value={lifecycleFilter} onChange={(event) => setLifecycleFilter(event.target.value)}><option value="">{t("adminFlowAll")}</option>{["draft", "test_ready", "testing", "test_passed", "production_approved", "published", "retired"].map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>{t("adminFlowGraphCompatibility")}<select value={graphFilter} onChange={(event) => setGraphFilter(event.target.value)}><option value="">{t("adminFlowAll")}</option>{graphs.map((graph) => <option key={`${graph.graph_key}@${graph.graph_version}`} value={`${graph.graph_key}@${graph.graph_version}`}>{graph.graph_key}@{graph.graph_version}</option>)}</select></label>
        </div>
        {loading ? <p role="status">{t("adminFlowPackagesLoading")}</p> : null}
        <label>{t("adminFlowSelectVersion")}<select value={selectedRef} onChange={(event) => setSelectedRef(event.target.value)}><option value="">{t("adminSelect")}</option>{visibleFlows.map((flow) => <option key={flowRef(flow)} value={flowRef(flow)}>{flow.title} — {flow.flow_key}@{flow.version} [{flow.lifecycle_state}]</option>)}</select></label>
        {selected ? <div className="admin-inline-actions"><button className="secondary-button" type="button" onClick={() => void cloneDraft()} disabled={Boolean(busy)}><FaClone aria-hidden="true" />{t("adminFlowCloneDraft")}</button><span className={`admin-flow-state admin-flow-state--${selected.lifecycle_state}`}>{selected.lifecycle_state}</span>{selected.definition_hash ? <code>{selected.definition_hash.slice(0, 16)}…</code> : null}</div> : null}
      </section>

      {selected ? <>
        <section className="admin-panel admin-panel--wide">
          <h3>{t("adminFlowDraftEditor")}</h3>
          {!editable ? <p className="admin-muted"><FaLock aria-hidden="true" /> {t("adminFlowImmutableNotice")}</p> : null}
          <div className="admin-price-grid">
            <label>{t("adminFlowDomain")}<input disabled={!editable} value={draft.domain} onChange={(event) => setDraft({ ...draft, domain: event.target.value })} /></label>
            <label>{t("adminFlowQuestionKind")}<input disabled={!editable} value={draft.questionKind} onChange={(event) => setDraft({ ...draft, questionKind: event.target.value })} /></label>
            <label>{t("adminFlowLegalDomain")}<input disabled={!editable} value={draft.legalDomain} onChange={(event) => setDraft({ ...draft, legalDomain: event.target.value })} /></label>
            <label>{t("adminFlowOutcome")}<input disabled={!editable} value={draft.requestedOutcome} onChange={(event) => setDraft({ ...draft, requestedOutcome: event.target.value })} /></label>
          </div>
          <label>{t("adminFlowTitle")}<input disabled={!editable} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
          <label>{t("adminFlowDescription")}<textarea disabled={!editable} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <div className="admin-price-grid">
            <label>{t("adminFlowPositiveExamples")}<textarea disabled={!editable} value={draft.positiveExamples} onChange={(event) => setDraft({ ...draft, positiveExamples: event.target.value })} /></label>
            <label>{t("adminFlowNegativeExamples")}<textarea disabled={!editable} value={draft.negativeExamples} onChange={(event) => setDraft({ ...draft, negativeExamples: event.target.value })} /></label>
          </div>
          <details><summary>{t("adminFlowAdvancedJson")}</summary><label>{t("adminFlowDefinitionJson")}<textarea className="admin-code-input" disabled={!editable} value={draft.definitionJson} onChange={(event) => setDraft({ ...draft, definitionJson: event.target.value })} /></label><label>{t("adminFlowClarificationJson")}<textarea className="admin-code-input" disabled={!editable} value={draft.clarificationPolicyJson} onChange={(event) => setDraft({ ...draft, clarificationPolicyJson: event.target.value })} /></label></details>
          <label>{t("adminFlowRegisteredGraph")}<select value={graphRef} onChange={(event) => setGraphRef(event.target.value)}><option value="">{t("adminSelect")}</option>{graphs.map((graph) => <option key={`${graph.graph_key}@${graph.graph_version}`} value={`${graph.graph_key}@${graph.graph_version}`}>{graph.graph_key}@{graph.graph_version}</option>)}</select></label>
          {validation.length ? <ul className={validation.length === 1 && validation[0] === t("adminFlowValidationPassed") ? "form-success" : "form-error"}>{validation.map((item) => <li key={item}>{item}</li>)}</ul> : null}
          <div className="admin-inline-actions"><button className="secondary-button" type="button" onClick={validateDraft}><FaCheck aria-hidden="true" />{t("adminFlowValidate")}</button><button className="primary-button" type="button" disabled={!editable || Boolean(busy)} onClick={() => void saveDraft()}>{t("adminFlowSaveDraft")}</button></div>
          <div className="admin-flow-lock"><label>{t("adminReason")}<input disabled={!editable} value={lockReason} onChange={(event) => setLockReason(event.target.value)} /></label><button className="secondary-button" type="button" disabled={!editable || !lockReason.trim() || Boolean(busy)} onClick={() => void lockDraft()}><FaLock aria-hidden="true" />{t("adminFlowLockTesting")}</button></div>
        </section>

        <section className="admin-panel">
          <h3>{t("adminFlowVersionDiff")}</h3>
          {!prior ? <p className="admin-muted">{t("adminFlowNoPriorVersion")}</p> : diff.length ? <dl className="admin-flow-diff">{diff.map(([key, value]) => <div key={key}><dt>{key}</dt><dd><del>{JSON.stringify(draftSnapshot(prior)[key])}</del><ins>{JSON.stringify(value)}</ins></dd></div>)}</dl> : <p>{t("adminFlowNoChanges")}</p>}
        </section>

        <section className="admin-panel">
          <h3>{t("adminFlowSuiteTitle")}</h3>
          <div className="admin-flow-inline-load"><label>{t("adminFlowSuiteId")}<input value={suiteId} onChange={(event) => setSuiteId(event.target.value)} /></label><button className="secondary-button" type="button" onClick={() => void loadSuite()} disabled={!suiteId.trim() || Boolean(busy)}>{t("adminFlowLoadSuite")}</button></div>
          {suite ? <p className="admin-highlight"><strong>{suite.title}</strong><span>{suite.suite_key}@{suite.version} · {suite.case_count} · {suite.suite_hash.slice(0, 12)}…</span></p> : null}
          <details><summary>{t("adminFlowCreateSuite")}</summary><label>{t("adminFlowSuiteKey")}<input value={suiteKey} onChange={(event) => setSuiteKey(event.target.value)} /></label><label>{t("adminFlowSuiteName")}<input value={suiteTitle} onChange={(event) => setSuiteTitle(event.target.value)} /></label><div className="admin-price-grid"><label>{t("adminFlowThreshold")}<input type="number" min="0.5" max="1" step="0.01" value={suiteThreshold} onChange={(event) => setSuiteThreshold(event.target.value)} /></label><label>{t("adminFlowRetention")}<input type="number" min="1" max="30" value={suiteRetention} onChange={(event) => setSuiteRetention(event.target.value)} /></label></div><label>{t("adminFlowCasesJson")}<textarea className="admin-code-input" value={suiteCasesJson} onChange={(event) => setSuiteCasesJson(event.target.value)} /></label><label><input type="checkbox" checked={syntheticConfirmed} onChange={(event) => setSyntheticConfirmed(event.target.checked)} />{t("adminFlowSyntheticConfirm")}</label><button className="secondary-button" type="button" disabled={!syntheticConfirmed || !suiteKey.trim() || !suiteTitle.trim() || Boolean(busy)} onClick={() => void createSuite()}>{t("adminFlowCreateSuite")}</button></details>
        </section>

        <section className="admin-panel admin-panel--wide">
          <h3>{t("adminFlowRunTitle")}</h3>
          <p className="admin-muted">{t("adminFlowReviewerRoles")}</p>
          <div className="admin-price-grid"><label>{t("adminFlowMode")}<select value={evaluationMode} onChange={(event) => setEvaluationMode(event.target.value as "routing_only" | "full_graph")}><option value="routing_only">routing_only</option><option value="full_graph">full_graph</option></select></label><label>{t("adminFlowProvider")}<input value={provider} onChange={(event) => setProvider(event.target.value)} /></label><label>{t("adminFlowModel")}<input value={model} onChange={(event) => setModel(event.target.value)} /></label><label>{t("adminFlowProviderRoute")}<input value={providerRoute} onChange={(event) => setProviderRoute(event.target.value)} /></label></div>
          <label>{t("adminFlowRoutingPolicyJson")}<textarea className="admin-code-input" value={routingPolicyJson} onChange={(event) => setRoutingPolicyJson(event.target.value)} /></label>
          <label>{t("adminFlowObservationsJson")}<textarea className="admin-code-input" value={observationsJson} onChange={(event) => setObservationsJson(event.target.value)} /></label>
          <label><input type="checkbox" checked={humanReviewed} onChange={(event) => setHumanReviewed(event.target.checked)} />{t("adminFlowHumanReview")}</label>
          <button className="primary-button" type="button" disabled={selected.lifecycle_state !== "test_ready" || !suite || !humanReviewed || !model.trim() || Boolean(busy)} onClick={() => void runEvaluation()}><FaPlay aria-hidden="true" />{busy === "run" ? t("adminFlowRunning") : t("adminFlowRun")}</button>
          {busy === "run" ? <p role="status" aria-live="polite">{t("adminFlowRunning")}</p> : null}
          {run ? <div className={`admin-flow-result admin-flow-result--${run.status}`}><h4>{run.status === "passed" ? t("adminFlowRunPassed") : t("adminFlowRunFailed")}</h4><p>{run.flow_key}@{run.flow_version} · {run.graph_version} · {run.provider}/{run.model}</p><ul>{Object.entries(run.gates).map(([gate, passed]) => <li key={gate}>{passed ? "✓" : "✕"} {gate}</li>)}</ul><small>{run.run_id} · {t("adminFlowExpires")} {run.expires_at}</small></div> : null}
        </section>
      </> : <section className="admin-panel"><p>{t("adminFlowNoFlows")}</p></section>}
    </section>
  );
};

export default AdminFlowPackages;
