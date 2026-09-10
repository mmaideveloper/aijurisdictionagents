import React from "react";
import { chatApiRuntimeConfig, parseApiErrorResponse } from "../api/chatClient";
import { correlationHeaders } from "../api/correlation";
import { useAuth } from "../auth/webAuth";
import "./DocumentReview.css";

type Change = { id: string; paragraph: number; original: string; replacement: string; reason: string;
  source_ids: string[]; section: number | null; category?: "legal" | "wording"; decision: "accepted" | "rejected" | "pending" };
type Review = { review_id: string; revision: number; paragraphs: string[]; proposals: Change[];
  warning: string; questions: string[]; review_date: string; preview_text: string;
  citations: { source_id: string; title: string; law_number: string; source_url?: string; effective_from?: string }[] };

export function DocumentReview({ caseId, docId, userId }: { caseId: string; docId: string; userId: string }) {
  const { user } = useAuth();
  const [review, setReview] = React.useState<Review | null>(null);
  const [text, setText] = React.useState("");
  const [facts, setFacts] = React.useState("");
  const [external, setExternal] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const requestId = React.useRef(crypto.randomUUID());
  const config = chatApiRuntimeConfig();
  const base = `${config.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(docId)}/review`;
  const request = React.useCallback(async (suffix: string, method = "GET", body?: unknown) => {
    if (!user?.deviceId || !user.deviceAuthToken) throw new Error("Prihláste sa pred kontrolou súkromného dokumentu.");
    const response = await fetch(`${base}${suffix}${suffix.includes("?") ? "&" : "?"}user_id=${encodeURIComponent(userId)}`, {
      method, headers: { ...correlationHeaders(), "x-api-key": config.apiKey, "Content-Type": "application/json",
        "x-jurisdigta-device-id": user.deviceId, "x-jurisdigta-device-token": user.deviceAuthToken },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!response.ok) throw new Error((await parseApiErrorResponse(response)).message);
    return response;
  }, [base, config.apiKey, userId, user?.deviceId, user?.deviceAuthToken]);
  const load = React.useCallback(async () => {
    setBusy(true); setError("");
    try { const result = await (await request("")).json(); setReview(result.review); setText(result.text); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Načítanie zlyhalo."); }
    finally { setBusy(false); }
  }, [request]);
  React.useEffect(() => { setReview(null); setText(""); void load(); }, [load]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await action(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Operácia zlyhala."); }
    finally { setBusy(false); }
  };
  const decide = (change: Change, decision: Change["decision"]) => run(async () => {
    if (!review) return;
    setReview(await (await request(`/${review.review_id}`, "PATCH", {
      expected_revision: review.revision, decisions: { [change.id]: decision }
    })).json());
  });
  const download = (format: "docx" | "pdf") => run(async () => {
    if (!review) return;
    const response = await request(`/${review.review_id}/export?revision=${review.revision}&format=${format}`);
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a"); anchor.href = url;
    anchor.download = `review-v${review.revision}.${format}`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const accepted = review ? review.paragraphs.map((paragraph, index) => {
    const change = review.proposals.find(item => item.paragraph === index && item.decision === "accepted");
    return change ? change.replacement : paragraph;
  }).join("\n\n") : "";
  return <section aria-label="Právna kontrola dokumentu" className="document-review">
    <h2>Kontrola a aktualizácia dokumentu</h2>
    <p>AI návrh vyžaduje ľudskú právnu kontrolu. Originál zostáva zachovaný.</p>
    <button type="button" disabled={busy} onClick={() => void load()}>Obnoviť stav</button>
    {error && <p role="alert">{error}</p>}
    {busy && <p role="status">Spracúva sa…</p>}
    {text && <>
      <details><summary>Extrahovaný text – skontrolujte údaje zo skenov</summary><pre style={{ whiteSpace: "pre-wrap" }}>{text}</pre></details>
      <label>Doplňujúce fakty (dátum zmluvy, postavenie strán, predmet kúpy)
        <textarea value={facts} maxLength={6000} onChange={event => setFacts(event.target.value)} />
      </label>
      <label><input type="checkbox" checked={external} onChange={event => setExternal(event.target.checked)} />
        Súhlasím s použitím schváleného externého AI poskytovateľa pre túto kontrolu, ak ho vyžaduje nastavená trasa.</label>
      <button type="button" disabled={busy} onClick={() => void run(async () => {
        setReview(await (await request("", "POST", { request_id: requestId.current, facts, external_acknowledged: external })).json());
        requestId.current = crypto.randomUUID();
      })}>Skontrolovať podľa slovenského práva</button>
    </>}
    {review && <>
      <p role="status">{review.warning} · Dátum kontroly: {review.review_date}</p>
      {review.questions.map((question, index) => <p key={index}>{question}</p>)}
      {review.proposals.length === 0 && <p>Neboli pripravené žiadne zmeny. To neznamená potvrdenie právnej správnosti.</p>}
      {review.proposals.map(change => <article key={change.id}>
        <h3>Odsek {change.paragraph + 1} · {change.decision === "accepted" ? "Prijaté" : change.decision === "rejected" ? "Odmietnuté" : "Čaká na rozhodnutie"}</h3>
        <p>{change.category === "wording" ? "Voliteľná jazyková úprava" : "Návrh právnej úpravy – vyžaduje kontrolu"}</p>
        <p>Pôvodné znenie:</p><del style={{ whiteSpace: "pre-wrap" }}>{change.original}</del>
        <p>Navrhované znenie:</p><ins style={{ whiteSpace: "pre-wrap" }}>{change.replacement || "(odstránenie)"}</ins>
        <p>{change.reason}</p>
        {change.source_ids.map(id => { const source = review.citations.find(item => item.source_id === id);
          return <p key={id}>§ {change.section} · {source?.law_number} · {source?.title}
            {source?.source_url?.startsWith("https://") && <> · <a href={source.source_url} target="_blank" rel="noreferrer">Zdroj</a></>}</p>;
        })}
        <button type="button" disabled={busy} onClick={() => void decide(change, "accepted")}>Prijať</button>
        <button type="button" disabled={busy} onClick={() => void decide(change, "rejected")}>Odmietnuť</button>
      </article>)}
      <details open><summary>Náhľad s prijatými zmenami</summary><pre style={{ whiteSpace: "pre-wrap" }}>{review.preview_text || accepted}</pre></details>
      <button type="button" disabled={busy || review.proposals.some(item => item.decision === "pending")} onClick={() => void download("docx")}>Stiahnuť DOCX</button>
      <button type="button" disabled={busy || review.proposals.some(item => item.decision === "pending")} onClick={() => void download("pdf")}>Stiahnuť PDF</button>
    </>}
  </section>;
}
