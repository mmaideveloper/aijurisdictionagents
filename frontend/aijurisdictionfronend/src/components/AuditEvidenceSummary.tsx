import { useState } from "react";
import { fetchAdminDebugTrace, type AdminAuthContext, type AdminDebugTrace, type AdminLangGraphEvidence } from "../api/adminModelClient";
import type { Language } from "../data/translations";

const copy = {
  en: { title: "Audit evidence coverage", help: "Missing evidence does not prove that a check ran or passed. These results cover retained records only.", unavailable: "Some telemetry is unavailable; retained local records remain visible.", unknown: "Not recorded / unknown", next: "Next graph evidence page", previous: "Previous graph evidence page", partial: "Partial graph evidence", noGraph: "Graph execution evidence is not recorded; the engine is unknown.", version: "Validator version", link: "Answer revision linkage", categories: ["Input structure", "Input security", "Output quality", "Output security", "Grounding", "Hallucination assessment"], states: { recorded: "Recorded", missing_evidence: "Missing evidence", not_run: "Not run", unsupported: "Unsupported", not_applicable: "Not applicable", expired: "Expired", unavailable: "Unavailable", partial: "Partial", passed: "Passed", failed: "Failed", blocked: "Blocked", error: "Error" } },
  sk: { title: "Pokrytie auditnými dôkazmi", help: "Chýbajúce dôkazy nepotvrdzujú vykonanie ani úspech kontroly. Výsledky zahŕňajú iba uchované záznamy.", unavailable: "Časť telemetrie nie je dostupná; uchované lokálne záznamy zostávajú viditeľné.", unknown: "Nezaznamenané / neznáme", next: "Ďalšia stránka dôkazov grafu", previous: "Predchádzajúca stránka dôkazov grafu", partial: "Čiastočné dôkazy grafu", noGraph: "Dôkazy vykonania grafu nie sú zaznamenané; použitý systém nie je známy.", version: "Verzia validátora", link: "Prepojenie na revíziu odpovede", categories: ["Štruktúra vstupu", "Bezpečnosť vstupu", "Kvalita výstupu", "Bezpečnosť výstupu", "Podloženie zdrojmi", "Posúdenie halucinácií"], states: { recorded: "Zaznamenané", missing_evidence: "Chýbajúce dôkazy", not_run: "Nevykonané", unsupported: "Nepodporované", not_applicable: "Neuplatňuje sa", expired: "Platnosť uplynula", unavailable: "Nedostupné", partial: "Čiastočné", passed: "Úspešné", failed: "Neúspešné", blocked: "Zablokované", error: "Chyba" } },
  de: { title: "Abdeckung der Auditnachweise", help: "Fehlende Nachweise belegen weder die Ausführung noch den Erfolg einer Prüfung. Die Ergebnisse umfassen nur gespeicherte Datensätze.", unavailable: "Ein Teil der Telemetrie ist nicht verfügbar; gespeicherte lokale Nachweise bleiben sichtbar.", unknown: "Nicht erfasst / unbekannt", next: "Nächste Seite der Graphnachweise", previous: "Vorherige Seite der Graphnachweise", partial: "Unvollständige Graphnachweise", noGraph: "Graph-Ausführungsnachweise fehlen; die Engine ist unbekannt.", version: "Validatorversion", link: "Verknüpfung zur Antwortrevision", categories: ["Eingabestruktur", "Eingabesicherheit", "Ausgabequalität", "Ausgabesicherheit", "Quellenfundierung", "Halluzinationsbewertung"], states: { recorded: "Erfasst", missing_evidence: "Fehlende Nachweise", not_run: "Nicht ausgeführt", unsupported: "Nicht unterstützt", not_applicable: "Nicht zutreffend", expired: "Abgelaufen", unavailable: "Nicht verfügbar", partial: "Unvollständig", passed: "Bestanden", failed: "Fehlgeschlagen", blocked: "Blockiert", error: "Fehler" } },
};
const categories = ["input_structure", "input_security", "output_quality", "output_security", "grounding", "hallucination_assessment"];

export function AuditEvidenceSummary({ trace, language, adminAuth, onGraphPage }: {
  trace: AdminDebugTrace; language: Language; adminAuth: AdminAuthContext;
  onGraphPage: (correlation: string, evidence: AdminLangGraphEvidence) => void;
}) {
  const text = copy[language];
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const label = (state: string | null | undefined) => text.states[state as keyof typeof text.states] ?? text.unknown;
  const graph = trace.langgraph_evidence;
  async function page(offset: number) {
    setLoading(true); setError(false);
    try { const result = await fetchAdminDebugTrace(adminAuth, trace.correlation_id, offset); onGraphPage(trace.correlation_id, result.langgraph_evidence); }
    catch { setError(true); }
    finally { setLoading(false); }
  }
  return <section aria-label={text.title}>
    <h3>{text.title}</h3><p>{text.help}</p>
    {trace.warnings.length || error ? <p role="status">{text.unavailable}</p> : null}
    {!graph.runs.length ? <p role="status">{text.noGraph}</p> : null}
    {graph.completeness === "partial" || graph.page.has_more ? <p role="status">{text.partial}</p> : null}
    {graph.page.offset > 0 ? <button type="button" disabled={loading} onClick={() => void page(Math.max(0, graph.page.offset - graph.page.limit))}>{text.previous}</button> : null}
    {graph.page.has_more && graph.page.next_offset !== null ? <button type="button" disabled={loading} onClick={() => void page(graph.page.next_offset!)}>{text.next}</button> : null}
    <dl>{categories.map((category, index) => <div key={category}>
      <dt>{text.categories[index]}</dt><dd>{label(trace.validation_evidence?.categories.find(item => item.category === category)?.evidence_status)}</dd>
    </div>)}</dl>
    <ul>{trace.validation_evidence?.checks.map((check, index) => <li key={check.execution_id ?? index}>
      <code>{check.validator_id ?? text.unknown}</code> — <span>{label(check.outcome)}</span>
      <p>{text.version}: {check.validator_version ?? text.unknown} · {text.link}: {label(check.artifact_link_status)}</p>
    </li>)}</ul>
  </section>;
}
