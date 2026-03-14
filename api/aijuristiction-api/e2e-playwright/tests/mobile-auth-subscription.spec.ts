import { expect, test } from '@playwright/test';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const apiKey = process.env.API_KEY ?? 'aijuris';

function uniqueMobileIdentity() {
  const nonce = `${Date.now()}${Math.floor(Math.random() * 10000)}`;
  return {
    phone: `+421900${nonce.slice(-6)}`,
    email: `mobile.playwright.${nonce}@example.com`,
    password: `Playwright-${nonce}`,
  };
}

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('mobile auth + subscription flow: sign-up, sign-in and request subscription change', async ({ request, baseURL }) => {
  const identity = uniqueMobileIdentity();

  const signUpResponse = await request.post(`${baseURL}/v1/users/sign-up`, {
    headers: { 'x-api-key': apiKey },
    data: {
      phone_number: identity.phone,
      email: identity.email,
      password: identity.password,
      first_name: 'Playwright',
      last_name: 'Mobile',
    },
  });
  expect(signUpResponse.status()).toBe(201);
  const signedUpUser = await signUpResponse.json();
  const userId = signedUpUser.user_id as string;
  expect(userId).toBeTruthy();

  const signInByPhoneResponse = await request.post(`${baseURL}/v1/users/sign-in/phone`, {
    headers: { 'x-api-key': apiKey },
    data: { phone_number: identity.phone },
  });
  expect(signInByPhoneResponse.status()).toBe(200);
  await expect(signInByPhoneResponse.json()).resolves.toMatchObject({
    user_id: userId,
    phone_number: identity.phone,
  });

  const signInByEmailResponse = await request.post(`${baseURL}/v1/users/sign-in`, {
    headers: { 'x-api-key': apiKey },
    data: {
      email: identity.email,
      password: identity.password,
    },
  });
  expect(signInByEmailResponse.status()).toBe(200);
  await expect(signInByEmailResponse.json()).resolves.toMatchObject({
    user_id: userId,
    email: identity.email,
  });

  const plansResponse = await request.get(`${baseURL}/v1/users/subscriptions/plans`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(plansResponse.status()).toBe(200);
  const plans = (await plansResponse.json()) as Array<{ plan_code: string }>;
  expect(plans.length).toBeGreaterThan(0);

  const targetPlanCode = plans[plans.length - 1]?.plan_code;
  expect(targetPlanCode).toBeTruthy();

  const createSubscriptionResponse = await request.post(`${baseURL}/v1/users/${userId}/subscriptions`, {
    headers: { 'x-api-key': apiKey },
    data: { plan_code: targetPlanCode },
  });
  expect(createSubscriptionResponse.status()).toBe(201);
  const requestedSubscription = await createSubscriptionResponse.json();
  expect(requestedSubscription.user_id).toBe(userId);
  expect(requestedSubscription.plan_code).toBe(targetPlanCode);
  expect(requestedSubscription.status).toBe('pending');

  const listSubscriptionsResponse = await request.get(`${baseURL}/v1/users/${userId}/subscriptions`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(listSubscriptionsResponse.status()).toBe(200);
  const subscriptions = (await listSubscriptionsResponse.json()) as Array<{ plan_code: string; status: string }>;

  expect(subscriptions.some((item) => item.plan_code === targetPlanCode && item.status === 'pending')).toBeTruthy();
});
