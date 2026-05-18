export type SpeechRuntime = "browser-native" | "unsupported";
export type SpeechResult = { transcript: string; runtime: SpeechRuntime };
export type SpeechErrorCode = "unsupported" | "permission-denied" | "no-speech" | "aborted" | "unknown";
export class SpeechToTextError extends Error { constructor(public readonly code: SpeechErrorCode, message: string){ super(message);} }
type BrowserSpeechCtor = new () => { lang: string; interimResults: boolean; maxAlternatives: number; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onerror: ((event: { error: string }) => void) | null; onend: (() => void) | null; start: () => void; stop: () => void; };
export const isBrowserSpeechAvailable = (): boolean => {
  if (typeof window === "undefined") return false;
  const w = window as Window & { webkitSpeechRecognition?: BrowserSpeechCtor; SpeechRecognition?: BrowserSpeechCtor };
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
};
export const recognizeOnce = (lang: string): Promise<SpeechResult> => {
  if (!isBrowserSpeechAvailable()) throw new SpeechToTextError("unsupported", "Speech recognition is not available in this browser.");
  const w = window as Window & { webkitSpeechRecognition?: BrowserSpeechCtor; SpeechRecognition?: BrowserSpeechCtor };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) throw new SpeechToTextError("unsupported", "Speech recognition is not available in this browser.");
  const recognition = new Ctor(); recognition.lang = lang; recognition.interimResults = false; recognition.maxAlternatives = 1;
  return new Promise<SpeechResult>((resolve, reject) => {
    let settled = false;
    recognition.onresult = (event) => { const transcript = event.results[0]?.[0]?.transcript?.trim() ?? ""; settled = true; if (!transcript) return reject(new SpeechToTextError("no-speech", "No speech detected.")); resolve({ transcript, runtime: "browser-native" }); };
    recognition.onerror = (event) => { settled = true; const mapped: SpeechErrorCode = event.error === "not-allowed" ? "permission-denied" : event.error === "aborted" ? "aborted" : event.error === "no-speech" ? "no-speech" : "unknown"; reject(new SpeechToTextError(mapped, `Speech recognition failed: ${event.error}`)); };
    recognition.onend = () => { if (!settled) reject(new SpeechToTextError("aborted", "Speech recognition ended unexpectedly.")); };
    recognition.start();
  });
};

export const languageToSpeechLocale = (language: "en" | "sk" | "de"): string => {
  switch (language) {
    case "sk":
      return "sk-SK";
    case "de":
      return "de-DE";
    case "en":
    default:
      return "en-US";
  }
};
