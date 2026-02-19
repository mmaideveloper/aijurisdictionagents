import { APIRequestContext } from '@playwright/test';

const DEFAULT_TIMEOUT_MS = 2000;

function healthTimeoutMs(): number {
  const raw = process.env.API_HEALTH_TIMEOUT_MS;
  if (!raw) {
    return DEFAULT_TIMEOUT_MS;
  }

  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_TIMEOUT_MS;
  }

  return parsed;
}

export async function ensureLiveApiOrFail(
  request: APIRequestContext,
  baseURL: string | undefined
): Promise<void> {
  const target = baseURL ?? 'http://127.0.0.1:8080';
  const message =
    `Live API is unavailable at ${target}. ` +
    'Start the API first (uvicorn app.main:app --port 8080) or set API_BASE_URL.';

  try {
    const response = await request.get(`${target}/health`, {
      timeout: healthTimeoutMs(),
    });

    if (response.ok()) {
      return;
    }
    throw new Error(`${message} Health status: ${response.status()}.`);
  } catch (error) {
    const details = error instanceof Error ? error.message : String(error);
    throw new Error(`${message} Root cause: ${details}`);
  }
}
