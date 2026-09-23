/* global AudioWorkletProcessor, sampleRate, registerProcessor */
// Audio is converted continuously to mono PCM16/16kHz; it is never persisted.
class SpeechCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.stopped = false;
    this.port.onmessage = () => {
      this.stopped = true;
      this.flush();
      this.port.postMessage({ stopped: true });
    };
  }
  flush() {
    if (!this.samples.length) return;
    const pcm = new Int16Array(this.samples);
    this.samples = [];
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
  }
  process(inputs) {
    if (this.stopped) return false;
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const sample of input) {
      this.sum += sample;
      this.count++;
      this.phase += 16000;
      if (this.phase >= sampleRate) {
        this.phase -= sampleRate;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.samples.push(Math.round(value * (value < 0 ? 32768 : 32767)));
        this.sum = 0;
        this.count = 0;
        if (this.samples.length >= 1600) this.flush();
      }
    }
    return true;
  }
}
registerProcessor("speech-capture", SpeechCapture);
