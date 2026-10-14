import React, { useEffect, useState } from "react";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "./LanguageProvider";
import { chatApiRuntimeConfig } from "../api/chatClient";

const copy = {
  en: { title: "Privacy controls", export: "Export my data", restrict: "Restrict processing", release: "Resume processing", deletion: "Request deletion", anonymize: "Request anonymization", pending: "Requests require operator review. Accounting obligations and legal holds may limit erasure. Approval does not mean erasure is complete.", error: "Privacy action failed. Please try again or contact info@jurisdigta.eu.", saved: "Privacy settings saved.", requested: "Request submitted. Processing is restricted pending review.", loading: "Loading privacy settings…", scopes: { external_models: "Allow necessary case content to be sent to an approved external AI provider", external_checks: "Allow necessary facts to be sent to external verification tools; per-run approval is also required", marketing: "Receive optional marketing communications", sensitive_processing: "Allow sensitive processing where explicit consent is the approved lawful condition" } },
  sk: { title: "Ochrana osobných údajov", export: "Exportovať moje údaje", restrict: "Obmedziť spracúvanie", release: "Obnoviť spracúvanie", deletion: "Požiadať o vymazanie", anonymize: "Požiadať o anonymizáciu", pending: "Žiadosti preveruje zodpovedná osoba. Účtovné povinnosti a právne dôvody môžu obmedziť vymazanie. Schválenie neznamená dokončené vymazanie.", error: "Operácia zlyhala. Skúste to znova alebo kontaktujte info@jurisdigta.eu.", saved: "Nastavenia boli uložené.", requested: "Žiadosť bola odoslaná. Spracúvanie je obmedzené do jej preverenia.", loading: "Načítavanie nastavení…", scopes: { external_models: "Povoliť odoslanie nevyhnutného obsahu prípadu schválenému externému poskytovateľovi AI", external_checks: "Povoliť odoslanie nevyhnutných údajov externým overovacím nástrojom; vyžaduje sa aj súhlas pre konkrétne použitie", marketing: "Prijímať voliteľné marketingové správy", sensitive_processing: "Povoliť spracúvanie citlivých údajov, ak je výslovný súhlas schválenou zákonnou podmienkou" } },
  de: { title: "Datenschutz", export: "Meine Daten exportieren", restrict: "Verarbeitung einschränken", release: "Verarbeitung fortsetzen", deletion: "Löschung beantragen", anonymize: "Anonymisierung beantragen", pending: "Anträge werden geprüft. Buchführungspflichten und rechtliche Aufbewahrung können die Löschung begrenzen. Eine Genehmigung bedeutet keine abgeschlossene Löschung.", error: "Aktion fehlgeschlagen. Bitte erneut versuchen oder info@jurisdigta.eu kontaktieren.", saved: "Einstellungen gespeichert.", requested: "Antrag eingereicht. Die Verarbeitung ist bis zur Prüfung eingeschränkt.", loading: "Einstellungen werden geladen…", scopes: { external_models: "Erforderliche Fallinhalte an einen genehmigten externen KI-Anbieter übermitteln", external_checks: "Erforderliche Daten an externe Prüfwerkzeuge übermitteln; die einzelne Nutzung benötigt ebenfalls eine Zustimmung", marketing: "Optionale Marketingnachrichten erhalten", sensitive_processing: "Sensible Verarbeitung erlauben, soweit ausdrückliche Einwilligung die genehmigte Rechtsgrundlage ist" } }
};
type Scope = keyof typeof copy.en.scopes;
type State = { notice_version: string; consents: Record<Scope, boolean>; restricted: boolean; requests: Array<{ request_id: string; operation: string; status: string }> };

export const PrivacyControls: React.FC = () => {
  const { user } = useAuth();
  const { language } = useLanguage();
  const text = copy[language as keyof typeof copy] ?? copy.en;
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const config = chatApiRuntimeConfig();
  const base = `${config.baseUrl}/v1/privacy/subjects/${encodeURIComponent(user?.userId ?? "")}`;
  const headers = { "x-api-key": config.apiKey, "Content-Type": "application/json", "x-jurisdigta-device-id": user?.deviceId ?? "", "x-jurisdigta-device-token": user?.deviceAuthToken ?? "" };
  const load = async (signal?: AbortSignal) => {
    const result = await fetch(base, { headers, signal, cache: "no-store" });
    if (!result.ok) throw new Error("privacy_unavailable");
    const data = await result.json();
    if (!data || typeof data.notice_version !== "string" || typeof data.restricted !== "boolean"
      || !Array.isArray(data.requests) || !data.consents
      || !(Object.keys(text.scopes) as Scope[]).every(scope => typeof data.consents[scope] === "boolean")) {
      throw new Error("privacy_response_invalid");
    }
    setState(data);
  };
  useEffect(() => {
    setState(null);
    if (!user) return;
    const controller = new AbortController();
    void load(controller.signal).catch(() => { if (!controller.signal.aborted) setError(text.error); });
    return () => controller.abort();
    // The user's authenticated session is the identity boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.userId, user?.deviceAuthToken, language]);
  const act = async (suffix: string, method = "POST", body?: object) => {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await fetch(base + suffix, { method, headers, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
      if (!result.ok) throw new Error("privacy_action_failed");
      if (suffix === "/export") {
        const url = URL.createObjectURL(await result.blob());
        const link = document.createElement("a");
        link.href = url; link.download = "privacy-export.zip";
        link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else {
        await load();
        setMessage(suffix === "/requests" ? text.requested : text.saved);
      }
    } catch { setError(text.error); }
    finally { setBusy(false); }
  };
  if (!user) return null;
  return <section className="card" aria-label={text.title}>
    <h2>{text.title}</h2>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!state ? <p>{text.loading}</p> : <>
      <p>{text.pending}</p>
      <p>{state.notice_version}</p>
      {(Object.keys(text.scopes) as Scope[]).map(scope => <label key={scope} style={{ display: "block", marginBottom: "0.75rem" }}>
        <input type="checkbox" checked={state.consents[scope]} disabled={busy} onChange={event => void act("/consents", "POST", { scope, text_version: state.notice_version, granted: event.target.checked })} /> {text.scopes[scope]}
      </label>)}
      <button disabled={busy} onClick={() => void act("/export", "GET")}>{text.export}</button>{" "}
      <button disabled={busy} onClick={() => void act("/restriction", "PUT", { restricted: !state.restricted })}>{state.restricted ? text.release : text.restrict}</button>{" "}
      <button disabled={busy} onClick={() => void act("/requests", "POST", { operation: "delete" })}>{text.deletion}</button>{" "}
      <button disabled={busy} onClick={() => void act("/requests", "POST", { operation: "anonymize" })}>{text.anonymize}</button>
      <ul>{state.requests.map(item => <li key={item.request_id}>{item.operation}: {item.status}</li>)}</ul>
    </>}
  </section>;
};
