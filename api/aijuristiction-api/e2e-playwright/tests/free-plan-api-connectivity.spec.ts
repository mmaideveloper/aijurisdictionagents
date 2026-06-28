import { expect, test } from '@playwright/test';
import { randomUUID } from 'crypto';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const apiKey = process.env.API_KEY ?? 'aijuris';

type ChatSession = {
  id: string;
  user_id: string;
};

type EffectiveRoute = {
  plan_code: string;
  route_type: string;
  provider: string;
  model: string;
  is_local: boolean;
  is_external: boolean;
};

type ChatMessage = {
  role: string;
  content: string;
};

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('free plan user can connect to JurisDigta API and receive a local-model chat reply', async ({
  request,
  baseURL,
}) => {
  test.setTimeout(Number(process.env.FREE_PLAN_API_E2E_TIMEOUT_MS ?? 180_000));

  const userId = randomUUID();
  const routeResponse = await request.get(
    `${baseURL}/v1/model-routing/effective?task_type=chat_reply&user_id=${userId}`,
    {
      headers: { 'x-api-key': apiKey },
    }
  );
  expect(routeResponse.status()).toBe(200);
  const route = (await routeResponse.json()) as EffectiveRoute;
  expect(route).toMatchObject({
    plan_code: 'free',
    route_type: 'free_local',
    provider: 'local_ollama',
    model: 'qwen3:1.7b',
    is_local: true,
    is_external: false,
  });

  const sessionResponse = await request.post(`${baseURL}/v1/chat/sessions`, {
    headers: { 'x-api-key': apiKey },
    data: {
      user_id: userId,
      country: 'SK',
      language: 'sk',
      discussion_type: 'advice',
    },
  });
  expect(sessionResponse.status()).toBe(200);
  const session = (await sessionResponse.json()) as ChatSession;
  expect(session.id).toBeTruthy();
  expect(session.user_id).toBe(userId);

  const replyResponse = await request.post(`${baseURL}/v1/chat/sessions/${session.id}/reply`, {
    headers: { 'x-api-key': apiKey },
    data: {
      content:
        'Chcem pripravit splnomocnenie pre dceru na vedenie motoroveho vozidla mojej firmy v slovenskom jazyku.',
    },
    timeout: Number(process.env.FREE_PLAN_API_E2E_TIMEOUT_MS ?? 180_000),
  });
  expect(replyResponse.status()).toBe(200);
  const reply = (await replyResponse.json()) as ChatMessage;
  expect(reply.role).toBe('assistant');
  expect(reply.content.trim().length).toBeGreaterThan(40);
  expect(reply.content).not.toMatch(/Connection error|internal_server_error|network/i);
});
