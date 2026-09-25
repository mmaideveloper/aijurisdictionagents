import { chatApiRuntimeConfig } from "../api/chatClient";
import type { AuthUser } from "../auth/webAuth";

export type SpeechRoute = {
  provider: string; model: string; region: string; external: boolean;
  model_profile_id: string; route_revision: string; max_seconds: number;
  locales: string[]; profiles: { id: string; label: string }[];
};
export type SpeechEvent = { type: string; segment?: number; text?: string; code?: string };

function headers(user: AuthUser) {
  return { "Content-Type": "application/json", "x-api-key": chatApiRuntimeConfig().apiKey,
    "x-jurisdigta-device-id": user.deviceId ?? "", "x-jurisdigta-device-token": user.deviceAuthToken ?? "" };
}

export async function fetchSpeechRoute(user: AuthUser, caseId: string, signal?: AbortSignal): Promise<SpeechRoute> {
  const response = await fetch(`${chatApiRuntimeConfig().baseUrl}/v1/speech/cases/${encodeURIComponent(caseId)}/route?user_id=${encodeURIComponent(user.userId)}`, { headers: headers(user), signal });
  if (!response.ok) throw new Error(response.status === 401 ? "authentication_required" : "route_unavailable");
  return response.json() as Promise<SpeechRoute>;
}

export async function setSpeechOverride(user: AuthUser, caseId: string, profile: string) {
  const response = await fetch(`${chatApiRuntimeConfig().baseUrl}/v1/speech/cases/${encodeURIComponent(caseId)}/override?user_id=${encodeURIComponent(user.userId)}`, {
    method: "PUT", headers: headers(user), body: JSON.stringify({ model_profile_id: profile || null })
  });
  if (!response.ok) throw new Error("route_unavailable");
}

export class TranscriptSegments {
  private finals = new Map<number, string>();
  private partial: { id: number; text: string } | null = null;
  update(event: SpeechEvent): string {
    if (typeof event.segment !== "number" || typeof event.text !== "string") return this.text();
    if (event.type === "final") {
      if (!this.finals.has(event.segment)) this.finals.set(event.segment, event.text);
      if (this.partial?.id === event.segment) this.partial = null;
    } else if (event.type === "partial" && !this.finals.has(event.segment)) {
      this.partial = { id: event.segment, text: event.text };
    }
    return this.text();
  }
  text() {
    const segments = new Map(this.finals);
    if (this.partial) segments.set(this.partial.id, this.partial.text);
    return [...segments].sort(([a], [b]) => a - b).map(([, value]) => value).join("\n");
  }
}

export function startStreamingSpeech(options: {
  user: AuthUser; caseId: string; locale: string; route: SpeechRoute;
  onEvent: (event: SpeechEvent) => void; onLevel: (level: number) => void;
}) {
  let socket: WebSocket | null = null;
  let media: MediaStream | null = null;
  let context: AudioContext | null = null;
  let capture: AudioWorkletNode | null = null;
  let cancelled = false;
  let stopping = false;
  let terminal = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let flushResolve: (() => void) | null = null;
  const releaseMic = () => {
    media?.getTracks().forEach((track) => track.stop());
    capture?.disconnect();
    void context?.close().catch(() => undefined);
    media = null; capture = null; context = null;
  };
  const cleanup = () => { clearTimeout(timer); releaseMic(); socket?.close(); };
  const fail = (code: string) => {
    if (cancelled || terminal) return;
    terminal = true; cleanup(); options.onEvent({ type: "error", code });
  };
  const stop = async () => {
    if (stopping || cancelled || terminal) return;
    stopping = true;
    options.onEvent({ type: "stopping" });
    if (capture) {
      await Promise.race([new Promise<void>((resolve) => { flushResolve = resolve; capture?.port.postMessage("stop"); }), new Promise<void>((resolve) => setTimeout(resolve, 500))]);
    }
    releaseMic();
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "stop" }));
    clearTimeout(timer); timer = setTimeout(() => fail("timeout"), 20000);
  };
  void Promise.resolve().then(async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === "undefined") throw new Error("unsupported");
      media = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (cancelled) { releaseMic(); return; }
      context = new AudioContext();
      await context.audioWorklet.addModule(`${import.meta.env.BASE_URL}speech-capture.js`);
      if (cancelled) { releaseMic(); return; }
      await context.resume();
      const base = new URL(chatApiRuntimeConfig().baseUrl, window.location.href);
      base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
      base.pathname = `${base.pathname.replace(/\/$/, "")}/v1/speech/stream`;
      base.search = "";
      socket = new WebSocket(base);
      timer = setTimeout(() => fail("timeout"), 20000);
      socket.onopen = () => {
        if (cancelled) { cleanup(); return; }
        socket?.send(JSON.stringify({ type: "start", user_id: options.user.userId,
          device_id: options.user.deviceId, device_token: options.user.deviceAuthToken,
          api_key: chatApiRuntimeConfig().apiKey, case_id: options.caseId,
          locale: options.locale, consent: true, route_revision: options.route.route_revision,
          format: "pcm_s16le_16000_mono" }));
      };
      socket.onmessage = (message) => {
        if (cancelled || terminal) return;
        let event: SpeechEvent;
        try { event = JSON.parse(String(message.data)) as SpeechEvent; } catch { fail("provider_failed"); return; }
        if (event.type === "ready" && context && media) {
          capture = new AudioWorkletNode(context, "speech-capture");
          capture.port.onmessage = ({ data }: MessageEvent<ArrayBuffer | { stopped: boolean }>) => {
            if (!(data instanceof ArrayBuffer)) { flushResolve?.(); return; }
            if (cancelled || terminal || socket?.readyState !== WebSocket.OPEN) return;
            if (socket.bufferedAmount > 64000) { fail("network"); return; }
            const samples = new Int16Array(data);
            options.onLevel(Math.min(1, Math.sqrt(samples.reduce((sum, n) => sum + (n / 32768) ** 2, 0) / samples.length) * 8));
            socket.send(data);
          };
          context.createMediaStreamSource(media).connect(capture);
          const mute = context.createGain(); mute.gain.value = 0;
          capture.connect(mute).connect(context.destination);
          clearTimeout(timer); timer = setTimeout(() => void stop(), options.route.max_seconds * 1000 - 1000);
        }
        if (event.type === "error") { fail(event.code ?? "provider_failed"); return; }
        if (event.type === "done") { terminal = true; cleanup(); }
        options.onEvent(event);
      };
      socket.onerror = () => fail("network");
      socket.onclose = () => { if (!terminal && !cancelled) fail("network"); };
    } catch (error) {
      fail(error instanceof DOMException && error.name === "NotAllowedError" ? "permission_denied" : error instanceof Error && error.message === "unsupported" ? "unsupported" : "network");
    }
  });
  return { stop, cancel: () => {
    cancelled = true;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "cancel" }));
    cleanup();
  } };
}
