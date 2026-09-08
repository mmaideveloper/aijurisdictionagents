import React from "react";

import type { AdminLangGraphEvidence, AdminLangGraphRunEvidence } from "../api/adminModelClient";
import type { TranslationKey } from "../data/translations";

type Props = {
  evidence: AdminLangGraphEvidence;
  t: (key: TranslationKey) => string;
};

type Point = { x: number; y: number };

export const LangGraphAuditGraph: React.FC<Props> = ({ evidence, t }) => {
  const [runId, setRunId] = React.useState(evidence.runs[0]?.workflow_run_id ?? "");
  const [selectedNode, setSelectedNode] = React.useState("");
  const [zoom, setZoom] = React.useState(1);
  React.useEffect(() => {
    setRunId(evidence.runs[0]?.workflow_run_id ?? "");
    setSelectedNode("");
    setZoom(1);
  }, [evidence]);
  const run = evidence.runs.find((item) => item.workflow_run_id === runId) ?? evidence.runs[0];
  if (!run) {
    return <p className="admin-muted">{t("adminDebugGraphUnavailable")}</p>;
  }
  return <section className="langgraph-audit" aria-label={t("adminDebugLangGraph")}>
    <div className="langgraph-audit__heading">
      <label>{t("adminDebugRun")}
        <select value={run.workflow_run_id} onChange={(event) => {
          setRunId(event.target.value);
          setSelectedNode("");
        }}>
          {evidence.runs.map((item) => <option key={item.workflow_run_id} value={item.workflow_run_id}>
            {item.workflow_run_id} · {item.graph_key}@{item.graph_version}
          </option>)}
        </select>
      </label>
      <div className="langgraph-audit__badges">
        <span>{run.graph_key}@{run.graph_version}</span>
        <span>{run.flow_key}@{run.flow_version}</span>
        <span>{run.run_status}</span>
        <span>{run.evidence_completeness}</span>
      </div>
    </div>
    {run.topology ? <GraphCanvas run={run} selectedNode={selectedNode} onSelectNode={setSelectedNode} zoom={zoom} t={t} /> : (
      <p role="status" className="admin-warning">{t("adminDebugGraphUnavailable")}</p>
    )}
    {run.topology ? <div className="langgraph-audit__controls">
      <button type="button" className="button ghost" aria-label={t("adminDebugZoomOut")} onClick={() => setZoom((value) => Math.max(0.55, value - 0.15))}>−</button>
      <button type="button" className="button ghost" onClick={() => setZoom(1)}>{t("adminDebugFitGraph")}</button>
      <button type="button" className="button ghost" aria-label={t("adminDebugZoomIn")} onClick={() => setZoom((value) => Math.min(1.8, value + 0.15))}>+</button>
    </div> : null}
    <p className="admin-muted">{t("adminDebugTopologyDigest")}: {run.topology_digest || t("adminDebugUnknown")}</p>
    {run.evidence_gaps.length ? <div className="admin-warning" role="status">
      <strong>{t("adminDebugIncomplete")}</strong> {run.evidence_gaps.join(", ")}
    </div> : null}
    {selectedNode ? <NodeEvidence run={run} nodeId={selectedNode} t={t} /> : null}
    <h3>{t("adminDebugExecutionList")}</h3>
    <ol className="langgraph-audit__execution-list">
      {run.occurrences.map((item) => <li key={item.occurrence_id}>
        <button type="button" onClick={() => setSelectedNode(item.node_id)}>{item.sequence}. {item.node_id}</button>
        <span>{item.status} · {t("adminDebugAttempt")} {item.attempt}</span>
        <code>{item.event_id}</code>
        {item.transition_id ? <small>{item.transition_id}</small> : <small>{t("adminDebugTransitionUnknown")}</small>}
      </li>)}
    </ol>
  </section>;
};

const GraphCanvas: React.FC<{
  run: AdminLangGraphRunEvidence;
  selectedNode: string;
  onSelectNode: (nodeId: string) => void;
  zoom: number;
  t: (key: TranslationKey) => string;
}> = ({ run, selectedNode, onSelectNode, zoom, t }) => {
  const topology = run.topology!;
  const columns = Math.min(4, Math.max(topology.nodes.length, 1));
  const width = columns * 210 + 40;
  const rows = Math.ceil(topology.nodes.length / columns);
  const height = rows * 145 + 50;
  const positions = new Map<string, Point>();
  topology.nodes.forEach((node, index) => {
    const row = Math.floor(index / columns);
    const rawColumn = index % columns;
    const column = row % 2 ? columns - rawColumn - 1 : rawColumn;
    positions.set(node.id, { x: 125 + column * 210, y: 75 + row * 145 });
  });
  const observedNodes = new Set(run.occurrences.map((item) => item.node_id));
  const observedEdges = new Set(run.observed_transition_ids);
  return <div className="langgraph-audit__viewport" tabIndex={0} aria-label={t("adminDebugGraphCanvas")}>
    <svg width={`${zoom * 100}%`} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${run.graph_key} ${t("adminDebugGraphCanvas")}`}>
      <defs><marker id="langgraph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" /></marker></defs>
      {topology.edges.map((edge) => {
        const source = positions.get(edge.source);
        const target = positions.get(edge.target);
        if (!source || !target) return null;
        const bend = source.y === target.y ? 0 : (target.x < source.x ? -45 : 45);
        const midX = (source.x + target.x) / 2 + bend;
        const midY = (source.y + target.y) / 2 - (target.x < source.x ? 38 : 0);
        return <g key={edge.id} className={observedEdges.has(edge.id) ? "is-observed" : "is-unobserved"}>
          <path className={edge.conditional ? "is-conditional" : ""} d={`M ${source.x} ${source.y} Q ${midX} ${midY} ${target.x} ${target.y}`} markerEnd="url(#langgraph-arrow)" />
          {edge.branch ? <text x={midX} y={midY - 5}>{edge.branch}</text> : null}
        </g>;
      })}
      {topology.nodes.map((node) => {
        const point = positions.get(node.id)!;
        const active = observedNodes.has(node.id);
        const current = run.current_node_id === node.id;
        return <g key={node.id} role="button" tabIndex={0} aria-label={`${node.label}: ${active ? t("adminDebugObserved") : t("adminDebugNotObserved")}`} className={`langgraph-audit__node ${active ? "is-observed" : "is-unobserved"} ${current ? "is-current" : ""} ${selectedNode === node.id ? "is-selected" : ""}`} onClick={() => onSelectNode(node.id)} onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") onSelectNode(node.id);
        }}>
          <rect x={point.x - 78} y={point.y - 28} width="156" height="56" rx="9" />
          <text x={point.x} y={point.y + 4} textAnchor="middle">{node.label.slice(0, 24)}</text>
        </g>;
      })}
    </svg>
  </div>;
};

const NodeEvidence: React.FC<{ run: AdminLangGraphRunEvidence; nodeId: string; t: (key: TranslationKey) => string }> = ({ run, nodeId, t }) => {
  const occurrences = run.occurrences.filter((item) => item.node_id === nodeId);
  return <aside className="langgraph-audit__details" aria-live="polite">
    <h3>{nodeId}</h3>
    <p>{occurrences.length} {t("adminDebugOccurrences")}</p>
    {occurrences.map((item) => <dl key={item.occurrence_id}>
      <div><dt>{t("adminDebugAttempt")}</dt><dd>{item.attempt}</dd></div>
      <div><dt>{t("adminDebugStatus")}</dt><dd>{item.status}</dd></div>
      <div><dt>{t("adminDebugEvidence")}</dt><dd>{item.event_id}</dd></div>
      <div><dt>{t("adminDebugReason")}</dt><dd>{item.reason_code || t("adminDebugUnknown")}</dd></div>
    </dl>)}
  </aside>;
};
