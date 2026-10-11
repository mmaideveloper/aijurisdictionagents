import type { AdminDebugTrace } from "../api/adminModelClient";
import type { Language } from "../data/translations";

const copy = {
  en: { title: "Final response assessment", help: "An assessment is not a probability of legal correctness. Existing human review remains required.", missing: "No assessment recorded", incomplete: "Incomplete — required evidence missing", blocked: "Blocked — critical check failed", scored: "Assessed", revision: "Answer revision", policy: "Score policy version", review: "Human review required" },
  sk: { title: "Posúdenie konečnej odpovede", help: "Posúdenie nie je pravdepodobnosťou právnej správnosti. Existujúca ľudská kontrola zostáva povinná.", missing: "Posúdenie nebolo zaznamenané", incomplete: "Neúplné — chýbajú povinné dôkazy", blocked: "Zablokované — kritická kontrola zlyhala", scored: "Posúdené", revision: "Revízia odpovede", policy: "Verzia pravidiel skóre", review: "Vyžaduje sa ľudská kontrola" },
  de: { title: "Bewertung der endgültigen Antwort", help: "Eine Bewertung ist keine Wahrscheinlichkeit rechtlicher Richtigkeit. Bestehende menschliche Prüfung bleibt erforderlich.", missing: "Keine Bewertung erfasst", incomplete: "Unvollständig — erforderliche Nachweise fehlen", blocked: "Blockiert — kritische Prüfung fehlgeschlagen", scored: "Bewertet", revision: "Antwortrevision", policy: "Version der Bewertungsregeln", review: "Menschliche Prüfung erforderlich" },
};

export function ResponseScoreEvidence({ trace, language }: { trace: AdminDebugTrace; language: Language }) {
  const text = copy[language];
  const assessments = trace.response_score_evidence?.assessments ?? [];
  return <section aria-label={text.title}>
    <h3>{text.title}</h3><p>{text.help}</p>
    {!assessments.length ? <p>{text.missing}</p> : <ul>{assessments.map(item => <li key={item.assessment_id}>
      <strong>{text[item.status]}</strong>
      {item.status === "scored" && item.score !== null ? <span> · {item.score} / 100</span> : null}
      <p>{text.revision}: <code>{item.answer_revision}</code> · {text.policy}: {item.policy_version}</p>
      {item.requires_human_review ? <p>{text.review}</p> : null}
      {item.missing_evidence.length ? <ul>{item.missing_evidence.map(code => <li key={code}><code>{code}</code></li>)}</ul> : null}
    </li>)}</ul>}
  </section>;
}
