import React from "react";
import { FiMic } from "react-icons/fi";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "./LanguageProvider";
import { fetchSpeechRoute, setSpeechOverride, startStreamingSpeech, TranscriptSegments, type SpeechRoute } from "../audio/streamingSpeech";
import { languageToSpeechLocale } from "../audio/speechToText";

export function SpeechDictation({ caseId, onFinal, onBusy }: {
  caseId: string | null; onFinal: (text: string) => void; onBusy: (busy: boolean) => void;
}) {
  const { user } = useAuth();
  const { t, language } = useLanguage();
  const [state, setState] = React.useState("idle");
  const [route, setRoute] = React.useState<SpeechRoute | null>(null);
  const [text, setText] = React.useState("");
  const [error, setError] = React.useState("");
  const [elapsed, setElapsed] = React.useState(0);
  const [level, setLevel] = React.useState(0);
  const generation = React.useRef(0);
  const session = React.useRef<ReturnType<typeof startStreamingSpeech> | null>(null);
  const request = React.useRef<AbortController | null>(null);
  const callbacks = React.useRef({ onFinal, onBusy });
  callbacks.current = { onFinal, onBusy };
  const busy = ["permission", "recording", "stopping"].includes(state);
  React.useEffect(() => { callbacks.current.onBusy(busy); }, [busy]);
  React.useEffect(() => {
    setState("idle"); setText(""); session.current = null;
    const attempt = generation;
    return () => {
      attempt.current++; request.current?.abort(); session.current?.cancel(); callbacks.current.onBusy(false);
    };
  }, [caseId, user?.userId, user?.deviceAuthToken, language]);
  React.useEffect(() => {
    if (state !== "recording") return;
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 250);
    return () => clearInterval(timer);
  }, [state]);
  const open = React.useCallback(async () => {
    if (!user || !caseId || session.current) return;
    const attempt = ++generation.current;
    request.current?.abort(); request.current = new AbortController();
    setError(""); setText(""); setState("loading");
    try {
      const selected = await fetchSpeechRoute(user, caseId, request.current.signal);
      if (attempt !== generation.current) return;
      setRoute(selected); setState("consent");
    } catch {
      if (attempt !== generation.current) return;
      setState("error"); setError(t("sttUnavailable"));
    }
  }, [user, caseId, t]);
  React.useEffect(() => {
    const listener = () => { void open(); };
    window.addEventListener("jurisdigta-speech-open", listener);
    return () => window.removeEventListener("jurisdigta-speech-open", listener);
  }, [open]);
  const cancel = () => {
    generation.current++; request.current?.abort(); session.current?.cancel(); session.current = null;
    setText(""); setState("idle"); callbacks.current.onBusy(false);
  };
  React.useEffect(() => {
    const leave = () => {
      generation.current++; request.current?.abort(); session.current?.cancel(); session.current = null;
      setText(""); setState("idle"); callbacks.current.onBusy(false);
    };
    window.addEventListener("pagehide", leave);
    return () => window.removeEventListener("pagehide", leave);
  }, []);
  const start = () => {
    if (!user || !caseId || !route) return;
    const attempt = ++generation.current;
    const transcript = new TranscriptSegments();
    setText(""); setElapsed(0); setState("permission"); callbacks.current.onBusy(true);
    session.current = startStreamingSpeech({ user, caseId, route, locale: languageToSpeechLocale(language),
      onLevel: (value) => { if (generation.current === attempt) setLevel(value); },
      onEvent: (event) => {
        if (generation.current !== attempt) return;
        if (event.type === "ready") setState("recording");
        if (event.type === "stopping") setState("stopping");
        if (event.type === "partial" || event.type === "final") setText(transcript.update(event));
        if (event.type === "done") {
          callbacks.current.onFinal(transcript.text()); setState("ready"); session.current = null;
          callbacks.current.onBusy(false);
        }
        if (event.type === "error") {
          session.current = null; callbacks.current.onBusy(false); setState("error");
          setText(""); setError(t(event.code === "permission_denied" ? "sttPermissionDenied" : event.code === "no_speech" ? "sttNoSpeech" : "sttFailed"));
        }
      }
    });
  };
  return <div className="speech-dictation">
    <button type="button" aria-label={t("sttDictate")} disabled={!caseId || !user || busy || state === "loading"} onClick={() => void open()}><FiMic aria-hidden="true" /> {t("sttDictate")}</button>
    {state === "loading" && <span role="status">{t("sttLoading")}</span>}
    {state === "consent" && route && <div className="speech-dictation__consent">
      <p>{t("sttDisclosure", { provider: route.provider, region: route.region })}</p>
      {route.profiles.length > 0 && <label>{t("sttModel")}<select value={route.model_profile_id} onChange={async (event) => {
        if (!user || !caseId) return;
        const attempt = ++generation.current; setState("loading");
        try { await setSpeechOverride(user, caseId, event.target.value); if (attempt === generation.current) await open(); }
        catch { if (attempt === generation.current) { setState("error"); setError(t("sttUnavailable")); } }
      }}>{route.profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.label}</option>)}</select></label>}
      <button type="button" onClick={start} disabled={!route.locales.includes(languageToSpeechLocale(language))}>{t("sttConsentStart")}</button>
      <button type="button" onClick={cancel}>{t("sttCancel")}</button>
    </div>}
    {busy && <div className="speech-dictation__recording">
      <span role="status">{t(state === "recording" ? "sttRecording" : state === "stopping" ? "sttFinalizing" : "sttPermission")} {elapsed}s</span>
      <meter aria-label={t("sttActivity")} min={0} max={1} value={level} />
      <button type="button" className="speech-dictation__stop" disabled={state !== "recording"} onClick={() => void session.current?.stop()}>{t("sttStop")}</button>
      <button type="button" onClick={cancel}>{t("sttCancel")}</button>
    </div>}
    {text && busy && <div data-testid="speech-live-transcript" className="speech-dictation__transcript" aria-label={t("sttDraft")} aria-live="polite">{text}</div>}
    {state === "ready" && <span role="status">{t("sttReady")}</span>}
    {error && state === "error" && <p role="alert">{error} <button type="button" onClick={() => void open()}>{t("sttRetry")}</button></p>}
  </div>;
}
