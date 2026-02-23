import { expect, test } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { ensureLiveApiOrFail } from './helpers/liveApi';

type SimulatorInput = {
  country: string;
  language: string;
  discussionType: 'advice' | 'court';
  firstQuestion: string;
  questionTimeoutSeconds: number;
  maxDiscussionMinutes: number;
  communicationMinutes: number;
  userSimulationMode: 'ReadUser' | 'AIUserSimulatorAgent';
};

type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};

const apiKey = process.env.API_KEY ?? 'aijuris';
const fixturesDir = path.join(__dirname, 'fixtures');

function parseSseBlock(block: string): StreamEvent[] {
  const events: StreamEvent[] = [];
  for (const rawEvent of block.split('\n\n')) {
    const lines = rawEvent
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) continue;

    const event = lines.find((line) => line.startsWith('event:'))?.slice('event:'.length).trim();
    const dataRaw = lines.find((line) => line.startsWith('data:'))?.slice('data:'.length).trim();
    if (!event || !dataRaw) continue;

    try {
      events.push({ event, data: JSON.parse(dataRaw) as Record<string, unknown> });
    } catch {
      events.push({ event, data: { raw: dataRaw } });
    }
  }
  return events;
}

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('chat simulator stream: load first question, upload txt doc, AI user simulation over selected minutes, persist Q/A', async ({ request, baseURL }, testInfo) => {
  const simulatorInput = JSON.parse(
    await readFile(path.join(fixturesDir, 'chat-simulator-input.json'), 'utf8'),
  ) as SimulatorInput;
  const simpleDoc = await readFile(path.join(fixturesDir, 'simple-case.txt'), 'utf8');

  const createSession = await request.post(`${baseURL}/v1/chat/sessions`, {
    headers: { 'x-api-key': apiKey },
    data: {
      country: simulatorInput.country,
      language: simulatorInput.language,
      discussion_type: simulatorInput.discussionType,
    },
  });
  expect(createSession.ok()).toBeTruthy();
  const session = (await createSession.json()) as { id: string };
  expect(session.id).toBeTruthy();

  const streamResponse = await fetch(`${baseURL}/v1/chat/sessions/${session.id}/stream`, {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      instruction: simulatorInput.firstQuestion,
      documents: [
        {
          doc_id: 'simple-case',
          path: 'simple-case.txt',
          content: simpleDoc,
        },
      ],
      question_timeout_seconds: simulatorInput.questionTimeoutSeconds,
      max_discussion_minutes: simulatorInput.maxDiscussionMinutes,
      communication_minutes: simulatorInput.communicationMinutes,
      user_simulation_mode: simulatorInput.userSimulationMode,
    }),
  });

  expect(streamResponse.ok).toBeTruthy();
  expect(streamResponse.headers.get('content-type')).toContain('text/event-stream');
  expect(streamResponse.body).toBeTruthy();

  const decoder = new TextDecoder();
  let pendingChunk = '';
  const streamEvents: StreamEvent[] = [];

  const reader = streamResponse.body?.getReader();
  while (reader) {
    const { done, value } = await reader.read();
    if (done) break;
    pendingChunk += decoder.decode(value, { stream: true });
    const sections = pendingChunk.split('\n\n');
    pendingChunk = sections.pop() ?? '';

    for (const section of sections) {
      streamEvents.push(...parseSseBlock(`${section}\n\n`));
    }
  }

  if (pendingChunk.trim()) {
    streamEvents.push(...parseSseBlock(pendingChunk));
  }

  const messageEvents = streamEvents.filter((event) => event.event === 'message');
  const coreMessages = messageEvents.filter((event) => event.data.role !== 'user');

  expect(messageEvents.length).toBeGreaterThan(0);
  expect(coreMessages.length).toBeGreaterThan(0);
  expect(streamEvents.some((event) => event.event === 'done')).toBeTruthy();

  const coreQuestions = coreMessages
    .map((event) => String(event.data.content ?? ''))
    .filter((content) => content.includes('?'));

  const userAnswers = messageEvents
    .filter((event) => event.data.role === 'user')
    .map((event) => String(event.data.content ?? ''));

  if (coreQuestions.length > 0) {
    expect(userAnswers.length).toBeGreaterThan(0);
  }

  const qaPairs = coreQuestions.map((question, index) => ({
    question,
    answer: userAnswers[index] ?? null,
  }));

  const outputFile = testInfo.outputPath('chat-simulator-qa.json');
  await writeFile(
    outputFile,
    JSON.stringify(
      {
        sessionId: session.id,
        language: simulatorInput.language,
        userSimulationMode: simulatorInput.userSimulationMode,
        communicationMinutes: simulatorInput.communicationMinutes,
        instruction: simulatorInput.firstQuestion,
        qaPairs,
        streamEventCount: streamEvents.length,
      },
      null,
      2,
    ),
    'utf8',
  );
  await testInfo.attach('chat-simulator-qa', { path: outputFile, contentType: 'application/json' });
});
