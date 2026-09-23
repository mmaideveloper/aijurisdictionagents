// Invoked by scripts/run_speech_e2e.py. Credentials arrive through stdin only.
// This is real acceptance: no route interception, injected transcripts, or mocked UI.
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
input = '';
const normalize = (value) => value.normalize('NFC').replace(/\s+/g, ' ').trim();
const words = (value) => normalize(value).toLowerCase().replace(/sto(?=\s+(?:eur|euro))/g, '100').replace(/€/g, ' eur').replace(/\beuro\b/g, 'eur').replace(/[^\p{L}\p{N}\s]/gu, '').trim().split(/\s+/);
function errorRate(expected, actual) {
  let row = Array.from({ length: actual.length + 1 }, (_, i) => i);
  for (let i = 0; i < expected.length; i++) {
    const next = [i + 1];
    for (let j = 0; j < actual.length; j++) next.push(Math.min(next[j] + 1, row[j + 1] + 1, row[j] + Number(expected[i] !== actual[j])));
    row = next;
  }
  return row[actual.length] / expected.length;
}
await mkdir(config.output, { recursive: true });
const manifest = { run_id: config.runId, synthetic: true, status: 'failed',
  frontend: config.frontend, api: config.api, mcp: config.mcp,
  expected: config.lines, seed_user_id: config.user.userId, seed_case_id: config.caseId,
  retention: 'Delete synthetic evidence within 7 days. No traces, tokens or passwords retained.' };
const browser = await chromium.launch({ headless: true, args: [
  '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
  `--use-file-for-fake-audio-capture=${config.wav}%noloop`,
] });
const context = await browser.newContext({ permissions: ['microphone'], viewport: { width: 1280, height: 960 } });
const page = await context.newPage();
let sentText = null;
let partials = 0;
let firstPartial = null;
let beforeStop = true;
let ttsCalls = 0;
let begun = null;
page.on('websocket', (socket) => {
  if (!socket.url().endsWith('/v1/speech/stream')) return;
  socket.on('framereceived', ({ payload }) => {
    try {
      const event = JSON.parse(String(payload));
      if (event.type === 'partial' && beforeStop && begun !== null) { partials++; firstPartial ??= Date.now() - begun; }
      if (event.type === 'ready') manifest.speech_route = {
        provider: event.provider, model: event.model, region: event.region, profile: event.model_profile_id,
      };
    } catch { /* binary audio is never retained */ }
  });
});
page.on('request', (request) => {
  if (/\/v1\/chat\/sessions\/[^/]+\/stream$/.test(request.url()) && request.method() === 'POST') {
    const body = request.postDataJSON();
    sentText = body.instruction ?? body.message ?? body.content ?? body.text;
  }
});
await page.exposeFunction('speechE2ETtsCall', () => { ttsCalls++; });
await page.addInitScript(({ user }) => {
  window.sessionStorage.setItem('jurisdigta.web.auth.user.v1', JSON.stringify(user));
  window.localStorage.setItem('aj_frontend_lang', 'sk');
  window.localStorage.setItem('jurisdigta.web.auth.device.v1', user.deviceId);
  const speak = window.speechSynthesis?.speak.bind(window.speechSynthesis);
  if (speak) window.speechSynthesis.speak = (utterance) => { void window.speechE2ETtsCall(); speak(utterance); };
}, { user: config.user });
try {
  const headers = { 'x-api-key': config.apiKey };
  const list = await context.request.get(`${config.api}/v1/cases?user_id=${config.user.userId}`, { headers });
  if (!list.ok() || !JSON.stringify(await list.json()).includes(config.caseId)) throw new Error('seed_case_not_visible');
  manifest.stage = 'open_case';
  await page.goto(`${config.frontend}/case/${encodeURIComponent(config.caseId)}`);
  const dictate = page.getByTestId('speech-mode-toggle');
  await expect(dictate).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#speech-microphone-status')).toHaveText('Mikrofón vypnutý');
  manifest.stage = 'open_dictation';
  await dictate.click();
  manifest.stage = 'consent';
  await expect(dictate).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#speech-microphone-status')).toHaveText('Mikrofón vypnutý');
  begun = Date.now();
  await page.getByRole('button', { name: 'Súhlasím — zapnúť mikrofón', exact: true }).click();
  manifest.stage = 'live_recognition';
  await expect(dictate).toHaveAttribute('data-speech-state', 'recording', { timeout: 20000 });
  await expect(page.locator('#speech-microphone-status')).toHaveText('Mikrofón zapnutý · Počúvam');
  await expect.poll(async () => Number(await page.getByRole('meter').getAttribute('aria-valuenow')), { timeout: 20000 }).toBeGreaterThan(0);
  const live = page.getByTestId('speech-live-transcript');
  await expect(live).toContainText('bicykel', { timeout: 60000 });
  await expect(live).toContainText('skontrolovať', { timeout: 60000 });
  // Actual rendered text spans at least two lines, not just a fixed-height empty box.
  const lineCount = await live.evaluate((element) => {
    const range = document.createRange(); range.selectNodeContents(element);
    return new Set([...range.getClientRects()].filter((rect) => rect.width > 0).map((rect) => Math.round(rect.top))).size;
  });
  if (lineCount < 2 || partials < 1 || sentText !== null) throw new Error('live_two_line_or_no_autosend_assertion');
  await page.screenshot({ path: path.join(config.output, 'recording-two-lines.png'), fullPage: true });
  manifest.stage = 'stop';
  beforeStop = false;
  const stopped = Date.now();
  await page.getByRole('button', { name: 'Zastaviť', exact: true }).click();
  await page.getByText('Skontrolujte a upravte prepis, potom stlačte Odoslať.', { exact: true }).waitFor({ timeout: 20000 });
  await expect(dictate).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#speech-microphone-status')).toHaveText('Mikrofón vypnutý');
  manifest.microphone_state_and_activity_verified = true;
  manifest.stop_to_final_ms = Date.now() - stopped;
  manifest.stage = 'review';
  const composer = page.locator('.assistant-composer__input');
  const recognized = await composer.inputValue();
  manifest.observed = recognized;
  manifest.word_error_rate = errorRate(words(config.lines.join(' ')), words(recognized));
  if (manifest.word_error_rate > 0.2 || !words(recognized).join(' ').includes('100 eur')) throw new Error('synthetic_slovak_accuracy');
  if (sentText !== null || ttsCalls) throw new Error('automatic_send_or_tts');
  // Deliberate human-review edit proves the exact approved text is submitted.
  const reviewed = `${recognized}\nToto je syntetický test.`;
  await composer.fill(reviewed);
  await page.screenshot({ path: path.join(config.output, 'reviewed-two-lines.png'), fullPage: true });
  manifest.stage = 'send';
  const answerFinished = page.waitForResponse((response) => /\/v1\/chat\/sessions\/[^/]+\/stream$/.test(response.url()) && response.request().method() === 'POST', { timeout: 180000 }).then((response) => response.finished());
  await page.locator('.assistant-composer__send').click();
  await expect.poll(() => sentText, { timeout: 15000 }).not.toBeNull();
  if (normalize(sentText) !== normalize(reviewed)) throw new Error('submitted_text_differs_from_review');
  manifest.stage = 'real_chat_response';
  await expect.poll(async () => {
    const response = await context.request.get(`${config.api}/v1/cases/${config.caseId}/history?user_id=${config.user.userId}`, { headers });
    if (!response.ok()) return false;
    const history = await response.json();
    return history.messages?.some((message) => message.role === 'assistant');
  }, { timeout: 180000 }).toBeTruthy();
  await answerFinished;
  await expect(page.locator('.assistant-message').last()).not.toContainText('Spracovávam...', { timeout: 15000 });
  await expect(page.locator('.assistant-message').last()).not.toContainText('Premýšľam...', { timeout: 15000 });
  await page.screenshot({ path: path.join(config.output, 'final-state.png'), fullPage: true });
  manifest.reviewed = reviewed;
  manifest.submitted = sentText;
  manifest.visible_lines = lineCount;
  manifest.partials_before_stop = partials;
  manifest.first_partial_ms = firstPartial;
  manifest.tts_calls = ttsCalls;
  manifest.status = 'browser_passed_pending_server_route_audit';
} catch (error) {
  // Do not retain Playwright traces or raw errors that may embed authenticated requests.
  manifest.failure = error instanceof Error && /^[a-z_]+$/.test(error.message) ? error.message : 'browser_assertion_failed';
  await page.screenshot({ path: path.join(config.output, 'failure-state.png'), fullPage: true }).catch(() => undefined);
  process.exitCode = 1;
} finally {
  await writeFile(path.join(config.output, 'result.json'), JSON.stringify(manifest, null, 2), 'utf8');
  await browser.close();
}
