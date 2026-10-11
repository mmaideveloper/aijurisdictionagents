import type { AdminDebugTrace } from "../api/adminModelClient";

type Props = { flow: AdminDebugTrace["flow"]; t: (key: "adminDebugFlow" | "adminCausalFlowHelp" | "adminCausalParent" | "adminCausalPartial" | "adminCausalUnverified") => string };

export function CausalAuditFlow({ flow, t }: Props) {
  const labels = new Map(flow.nodes.map((node) => [node.id, node.label]));
  return <section aria-label={t("adminDebugFlow")}>
    <p>{t("adminCausalFlowHelp")}</p>
    {flow.evidence_gaps?.length ? <p role="status">
      {t("adminCausalPartial")}: {flow.evidence_gaps.join(", ")}
    </p> : null}
    <ol className="admin-debug__timeline">
      {flow.nodes.map((node) => <li key={node.id}>
        <strong>{node.label}</strong><code>{node.id}</code>
        {node.parent_link_source === "request_header_unverified" ? <small>{t("adminCausalUnverified")}</small> : null}
        {flow.edges.filter((edge) => edge.to === node.id).map((edge) => <p key={edge.from}>
          {t("adminCausalParent")}: {labels.get(edge.from) ?? edge.from} <code>{edge.from}</code>
        </p>)}
        {node.observations?.map((event) => <p key={event.event_id}>
          <time>{event.created_at}</time> {event.component}: {event.stage} — {event.status}
        </p>)}
      </li>)}
    </ol>
  </section>;
}
