import React from "react";
import { useParams } from "react-router-dom";
import {
  fetchSharedDocumentPdf,
  requestDocumentShareCode,
  verifyDocumentShareCode
} from "../api/documentShareClient";
import { useLanguage } from "../components/LanguageProvider";

type ShareLocale = "en" | "sk" | "de";

const copy = {
  en: {
    title: "Protected legal document",
    intro: "Request a code at the email address selected by the sender. Registration is not required.",
    request: "Send verification code",
    sent: "A verification code was sent to the recipient email.",
    code: "Six-digit verification code",
    verify: "Verify and open document",
    loading: "Opening protected document…",
    warning: "AI-assisted legal documents require qualified human review before filing, signing, or reliance.",
    error: "The document link or verification code is unavailable or expired."
  },
  sk: {
    title: "Chránený právny dokument",
    intro: "Vyžiadajte si kód na e-mailovú adresu zvolenú odosielateľom. Registrácia nie je potrebná.",
    request: "Odoslať overovací kód",
    sent: "Overovací kód bol odoslaný na e-mail príjemcu.",
    code: "Šesťmiestny overovací kód",
    verify: "Overiť a otvoriť dokument",
    loading: "Otvára sa chránený dokument…",
    warning: "Právne dokumenty vytvorené s podporou AI vyžadujú pred podaním, podpisom alebo použitím kvalifikovanú ľudskú kontrolu.",
    error: "Odkaz na dokument alebo overovací kód nie je dostupný alebo vypršal."
  },
  de: {
    title: "Geschütztes Rechtsdokument",
    intro: "Fordern Sie einen Code an die vom Absender ausgewählte E-Mail-Adresse an. Keine Registrierung erforderlich.",
    request: "Bestätigungscode senden",
    sent: "Ein Bestätigungscode wurde an die Empfänger-E-Mail gesendet.",
    code: "Sechsstelliger Bestätigungscode",
    verify: "Bestätigen und Dokument öffnen",
    loading: "Geschütztes Dokument wird geöffnet…",
    warning: "KI-unterstützte Rechtsdokumente erfordern vor Einreichung, Unterzeichnung oder Verwendung eine qualifizierte menschliche Prüfung.",
    error: "Der Dokumentlink oder Bestätigungscode ist nicht verfügbar oder abgelaufen."
  }
} as const;

const SharedDocumentViewer: React.FC = () => {
  const { shareToken = "" } = useParams();
  const { language, setLanguage } = useLanguage();
  const [locale, setLocale] = React.useState<ShareLocale>(language);
  const [code, setCode] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [pdfUrl, setPdfUrl] = React.useState("");
  const labels = copy[locale];

  React.useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  const requestCode = async () => {
    setBusy(true); setError("");
    try {
      const result = await requestDocumentShareCode(shareToken);
      setLocale(result.locale); setLanguage(result.locale); setNotice(copy[result.locale].sent);
    } catch { setError(labels.error); }
    finally { setBusy(false); }
  };

  const verify = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const verified = await verifyDocumentShareCode(shareToken, code);
      setLocale(verified.locale); setLanguage(verified.locale);
      const pdf = await fetchSharedDocumentPdf(verified.session_token);
      setPdfUrl(URL.createObjectURL(pdf)); setNotice("");
    } catch { setError(labels.error); }
    finally { setBusy(false); }
  };

  return (
    <div className="page shared-document-page">
      <section className="shared-document-shell">
        <h1>{labels.title}</h1>
        {!pdfUrl ? <>
          <p>{labels.intro}</p>
          <button type="button" className="button primary" onClick={requestCode} disabled={busy}>{labels.request}</button>
          {notice ? <p className="hint" role="status">{notice}</p> : null}
          <form onSubmit={verify} className="shared-document-verification">
            <label><span>{labels.code}</span><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} required /></label>
            <button type="submit" className="button primary" disabled={busy || code.length !== 6}>{labels.verify}</button>
          </form>
        </> : <iframe className="document-viewer-frame" src={pdfUrl} title={labels.title} referrerPolicy="no-referrer" />}
        {busy ? <p className="hint">{labels.loading}</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <p className="shared-document-warning">{labels.warning}</p>
      </section>
    </div>
  );
};

export default SharedDocumentViewer;
