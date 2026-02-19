import { expect, test } from '@playwright/test';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const apiKey = process.env.API_KEY ?? 'aijuris';

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('chat roundtrip: create session, create message, list messages', async ({ request, baseURL }) => {
  const createSession = await request.post(`${baseURL}/v1/chat/sessions`, {
    headers: { 'x-api-key': apiKey },
    data: {},
  });
  expect(createSession.ok()).toBeTruthy();
  const session = await createSession.json();
  const sessionId = session.id as string;
  expect(sessionId).toBeTruthy();

  const createMessage = await request.post(`${baseURL}/v1/chat/messages`, {
    headers: { 'x-api-key': apiKey },
    data: {
      session_id: sessionId,
      role: 'user',
      content: 'Hello from playwright e2e',
    },
  });
  expect(createMessage.ok()).toBeTruthy();
  const message = await createMessage.json();
  expect(message.content).toBe('Hello from playwright e2e');
  expect(message.role).toBe('user');

  const listMessages = await request.get(`${baseURL}/v1/chat/sessions/${sessionId}/messages`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(listMessages.ok()).toBeTruthy();
  const messages = (await listMessages.json()) as Array<{ content: string; role: string }>;
  expect(messages.length).toBe(1);
  expect(messages[0].content).toBe('Hello from playwright e2e');
  expect(messages[0].role).toBe('user');
});

test('chat endpoint requires API key', async ({ request, baseURL }) => {
  const response = await request.post(`${baseURL}/v1/chat/sessions`, { data: {} });
  expect(response.status()).toBe(401);
});
