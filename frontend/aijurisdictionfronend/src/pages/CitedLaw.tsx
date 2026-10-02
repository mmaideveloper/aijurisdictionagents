import React from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";
import { chatApiRuntimeConfig } from "../api/chatClient";

const labels = {
  sk: { loading: "Načítavam úplné znenie zákona…", error: "Citované znenie zákona nie je dostupné alebo k nemu nemáte prístup.", effective: "Účinné od", notice: "Znenie použité v odpovedi. Právny výklad vyžaduje odborné overenie." },
  en: { loading: "Loading the full law…", error: "The cited law version is unavailable or you do not have access.", effective: "Effective from", notice: "Version used in the answer. Legal interpretation requires professional review." },
  de: { loading: "Vollständiges Gesetz wird geladen…", error: "Die zitierte Gesetzesfassung ist nicht verfügbar oder der Zugriff fehlt.", effective: "Gültig ab", notice: "In der Antwort verwendete Fassung. Die rechtliche Auslegung erfordert fachliche Prüfung." }
};
type Law = { title: string; law_number: string; effective_from: string; content: string };

export default function CitedLaw() {
  const { caseId, citationId } = useParams();
  const { user } = useAuth();
  const { language } = useLanguage();
  const copy = labels[language];
  const [law, setLaw] = React.useState<Law | null>(null);
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => {
    if (!user || !caseId || !citationId) return;
    const abort = new AbortController();
    const config = chatApiRuntimeConfig();
    setLaw(null); setFailed(false);
    void fetch(`${config.baseUrl}/v1/cases/${encodeURIComponent(caseId)}/citations/${encodeURIComponent(citationId)}/full-law?user_id=${encodeURIComponent(user.userId)}`, {
      signal: abort.signal,
      headers: { "x-api-key": config.apiKey, "x-jurisdigta-device-id": user.deviceId ?? "", "x-jurisdigta-device-token": user.deviceAuthToken ?? "" }
    }).then(async response => {
      if (!response.ok) throw new Error("source unavailable");
      setLaw(await response.json() as Law);
    }).catch(() => { if (!abort.signal.aborted) setFailed(true); });
    return () => abort.abort();
  }, [caseId, citationId, user]);
  return <article style={{ maxWidth: 1000, margin: "2rem auto", padding: "0 2rem" }}>
    {failed ? <p role="alert">{copy.error}</p> : !law ? <p role="status">{copy.loading}</p> : <>
      <h1>{law.law_number}</h1><h2>{law.title}</h2>
      <p>{copy.effective}: {law.effective_from}</p><p>{copy.notice}</p>
      <div data-testid="full-law-text" style={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>{law.content}</div>
    </>}
  </article>;
}
