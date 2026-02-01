import { useMemo, useRef, useState } from "react";
import * as SpeechSDK from "microsoft-cognitiveservices-speech-sdk";
import { azureSpeechConfig, isAzureSpeechConfigured } from "./config";

const highlights = [
  {
    title: "Secure Intake",
    body: "Collect user instructions and uploads in a single flow before agents begin."
  },
  {
    title: "Live Orchestration",
    body: "Stream status updates from judge and lawyer agents in real time."
  },
  {
    title: "Traceable Outputs",
    body: "Keep decisions and next steps visible, searchable, and export-ready."
  }
];

const workflow = [
  "Authenticate and start a case session",
  "Upload evidence and set instructions",
  "Watch the agent dialog unfold",
  "Stop or export the final summary"
];

type MouthVariant = "rest" | "open" | "wide" | "round" | "closed" | "narrow";

const visemeToMouth: Record<number, MouthVariant> = {
  0: "rest",
  1: "open",
  2: "open",
  3: "wide",
  4: "wide",
  5: "round",
  6: "closed",
  7: "closed",
  8: "narrow",
  9: "wide",
  10: "open",
  11: "open",
  12: "open",
  13: "closed",
  14: "open",
  15: "wide",
  16: "round",
  17: "wide",
  18: "open",
  19: "open",
  20: "open",
  21: "rest"
};

const defaultText =
  "Hello. This is a proof of concept for the AI Jurisdiction avatar lipsync demo.";

export default function App() {
  const [text, setText] = useState(defaultText);
  const [status, setStatus] = useState("Idle");
  const [error, setError] = useState<string | null>(null);
  const [visemeId, setVisemeId] = useState<number | null>(null);
  const [mouth, setMouth] = useState<MouthVariant>("rest");
  const [isSpeaking, setIsSpeaking] = useState(false);

  const synthesizerRef = useRef<SpeechSDK.SpeechSynthesizer | null>(null);
  const timersRef = useRef<number[]>([]);
  const startTimestampRef = useRef<number>(0);

  const configSummary = useMemo(
    () => ({
      region: azureSpeechConfig.region || "Not set",
      voice: azureSpeechConfig.voice
    }),
    []
  );

  const clearTimers = () => {
    timersRef.current.forEach((timerId) => window.clearTimeout(timerId));
    timersRef.current = [];
  };

  const resetSynthesizer = () => {
    clearTimers();
    if (synthesizerRef.current) {
      synthesizerRef.current.close();
      synthesizerRef.current = null;
    }
  };

  const stopSpeech = () => {
    setError(null);
    setStatus("Stopped");
    setIsSpeaking(false);
    setMouth("rest");
    setVisemeId(null);

    const synthesizer = synthesizerRef.current;
    clearTimers();

    if (synthesizer) {
      try {
        const stop = (synthesizer as unknown as { stopSpeakingAsync?: () => void })
          .stopSpeakingAsync;
        if (stop) {
          stop.call(synthesizer);
        }
      } finally {
        synthesizer.close();
      }
    }

    synthesizerRef.current = null;
  };

  const startSpeech = () => {
    setError(null);

    if (!isAzureSpeechConfigured) {
      setError("Azure Speech is not configured. Add VITE_AZURE_SPEECH_KEY and VITE_AZURE_SPEECH_REGION.");
      return;
    }

    if (!text.trim()) {
      setError("Enter some text to synthesize.");
      return;
    }

    stopSpeech();

    const speechConfig = SpeechSDK.SpeechConfig.fromSubscription(
      azureSpeechConfig.key,
      azureSpeechConfig.region
    );
    speechConfig.speechSynthesisVoiceName = azureSpeechConfig.voice;

    const audioConfig = SpeechSDK.AudioConfig.fromDefaultSpeakerOutput();
    const synthesizer = new SpeechSDK.SpeechSynthesizer(speechConfig, audioConfig);
    synthesizerRef.current = synthesizer;

    setStatus("Speaking");
    setIsSpeaking(true);
    setMouth("rest");
    setVisemeId(null);

    startTimestampRef.current = performance.now();

    synthesizer.visemeReceived = (_sender, event) => {
      const offsetMs = event.audioOffset / 10000;
      const elapsed = performance.now() - startTimestampRef.current;
      const delay = Math.max(0, offsetMs - elapsed);
      const timerId = window.setTimeout(() => {
        setVisemeId(event.visemeId);
        setMouth(visemeToMouth[event.visemeId] ?? "rest");
      }, delay);
      timersRef.current.push(timerId);
    };

    synthesizer.synthesisCompleted = () => {
      setStatus("Completed");
      setIsSpeaking(false);
      setMouth("rest");
      resetSynthesizer();
    };

    synthesizer.synthesisCanceled = (_sender, event) => {
      setStatus("Canceled");
      setIsSpeaking(false);
      setMouth("rest");
      setError(event.errorDetails || "Speech synthesis canceled.");
      resetSynthesizer();
    };

    synthesizer.speakTextAsync(
      text,
      () => {},
      (err) => {
        setStatus("Error");
        setIsSpeaking(false);
        setMouth("rest");
        setError(String(err));
        resetSynthesizer();
      }
    );
  };

  return (
    <div className="page">
      <header className="hero">
        <div className="hero__badge">Frontend demo</div>
        <h1>AI Jurisdiction Frontend</h1>
        <p>
          A React + TypeScript starter for the AI Jurisdiction system. Build the
          client workspace, orchestrate live sessions, and keep every decision in view.
        </p>
        <div className="hero__actions">
          <button className="btn btn--primary" type="button">Start session</button>
          <button className="btn btn--ghost" type="button">View agent stream</button>
        </div>
        <div className="hero__panel">
          <div>
            <span className="label">Status</span>
            <p className="value">Awaiting intake</p>
          </div>
          <div>
            <span className="label">Region</span>
            <p className="value">Slovakia (SK)</p>
          </div>
          <div>
            <span className="label">Mode</span>
            <p className="value">Advice</p>
          </div>
        </div>
      </header>

      <section className="grid">
        {highlights.map((item) => (
          <article key={item.title} className="card">
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </article>
        ))}
      </section>

      <section className="avatar-demo">
        <div className="avatar-demo__intro">
          <div>
            <span className="label">POC</span>
            <h2>Avatar lipsync demo</h2>
            <p>
              Text-to-speech uses Azure Speech to emit visemes. The avatar is a
              lightweight SVG with mouth shapes mapped to the viseme stream for a
              fast demo without WebGL or video assets.
            </p>
          </div>
          <div className="avatar-demo__meta">
            <div>
              <span className="label">Azure region</span>
              <p className="value">{configSummary.region}</p>
            </div>
            <div>
              <span className="label">Voice</span>
              <p className="value">{configSummary.voice}</p>
            </div>
            <div>
              <span className="label">Status</span>
              <p className="value">{status}</p>
            </div>
          </div>
        </div>

        <div className="avatar-demo__workspace">
          <div className="avatar-demo__input">
            <label className="label" htmlFor="avatar-text">Text to speak</label>
            <textarea
              id="avatar-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Type text to speak..."
              rows={6}
            />
            <div className="avatar-demo__controls">
              <button
                className="btn btn--primary"
                type="button"
                onClick={startSpeech}
                disabled={!isAzureSpeechConfigured || isSpeaking}
              >
                Speak
              </button>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={stopSpeech}
                disabled={!isSpeaking}
              >
                Stop
              </button>
            </div>
            <p className="avatar-demo__hint">
              Configure <span className="code">VITE_AZURE_SPEECH_KEY</span> and
              <span className="code">VITE_AZURE_SPEECH_REGION</span> in a local
              <span className="code">.env</span> file to enable Azure TTS.
            </p>
          </div>

          <div className="avatar-demo__avatar">
            <div className={`avatar__frame ${isSpeaking ? "avatar__frame--active" : ""}`}>
              <svg className="avatar__svg" viewBox="0 0 220 220" role="img" aria-label="Avatar demo">
                <defs>
                  <linearGradient id="faceGlow" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#1f2a44" />
                    <stop offset="100%" stopColor="#0f172a" />
                  </linearGradient>
                </defs>
                <circle cx="110" cy="110" r="88" fill="url(#faceGlow)" stroke="#4f5d7f" strokeWidth="2" />
                <circle cx="80" cy="90" r="10" fill="#e2e8f0" />
                <circle cx="140" cy="90" r="10" fill="#e2e8f0" />
                <circle cx="80" cy="90" r="4" fill="#1f2937" />
                <circle cx="140" cy="90" r="4" fill="#1f2937" />
                <path d="M70 140 C85 170 135 170 150 140" stroke="#94a3b8" strokeWidth="5" fill="none" />
                <g className="avatar__mouth">
                  <path
                    className={`mouth mouth--rest ${mouth === "rest" ? "is-active" : ""}`}
                    d="M85 135 Q110 150 135 135"
                  />
                  <ellipse
                    className={`mouth mouth--open ${mouth === "open" ? "is-active" : ""}`}
                    cx="110"
                    cy="145"
                    rx="18"
                    ry="12"
                  />
                  <ellipse
                    className={`mouth mouth--round ${mouth === "round" ? "is-active" : ""}`}
                    cx="110"
                    cy="145"
                    rx="10"
                    ry="14"
                  />
                  <rect
                    className={`mouth mouth--closed ${mouth === "closed" ? "is-active" : ""}`}
                    x="92"
                    y="142"
                    width="36"
                    height="6"
                    rx="3"
                  />
                  <path
                    className={`mouth mouth--wide ${mouth === "wide" ? "is-active" : ""}`}
                    d="M80 145 Q110 130 140 145"
                  />
                  <path
                    className={`mouth mouth--narrow ${mouth === "narrow" ? "is-active" : ""}`}
                    d="M90 145 Q110 150 130 145"
                  />
                </g>
              </svg>
            </div>
            <div className="avatar__status">
              <div>
                <span className="label">Viseme</span>
                <p className="value">{visemeId ?? "--"}</p>
              </div>
              <div>
                <span className="label">Mouth</span>
                <p className="value">{mouth}</p>
              </div>
            </div>
          </div>
        </div>

        {error ? <div className="avatar-demo__error">{error}</div> : null}
      </section>

      <section className="callout">
        <div>
          <h2>Workflow snapshot</h2>
          <p>
            This demo layout mirrors the future dashboard: intake on the left,
            streamed dialogue on the right, and actions pinned for clarity.
          </p>
          <ul>
            {workflow.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div className="callout__panel">
          <span className="label">Next milestone</span>
          <h3>Hook up API events</h3>
          <p>
            Connect to the orchestration endpoints and map the messages to this
            layout in the next iteration.
          </p>
          <button className="btn btn--accent" type="button">Open API docs</button>
        </div>
      </section>
    </div>
  );
}
