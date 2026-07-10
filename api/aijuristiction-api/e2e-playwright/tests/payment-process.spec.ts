import { APIRequestContext, expect, test } from '@playwright/test';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const apiKey = process.env.API_KEY ?? 'aijuris';

type Plan = {
  plan_code: string;
  display_name: string;
  price_eur: number;
};

type CheckoutResponse = {
  subscription_id: string;
  plan_code: string;
  payment_provider: string;
  payment_id: string;
  payment_status: string;
  amount_eur: number;
  checkout_url: string;
};

type SubscriptionResponse = {
  subscription_id: string;
  user_id: string;
  plan_code: string;
  status: string;
};

function uniquePaymentIdentity() {
  const nonce = `${Date.now()}${Math.floor(Math.random() * 10000)}`;
  return {
    phone: `+421901${nonce.slice(-6)}`,
    email: `payment.playwright.${nonce}@example.com`,
    password: `Payment-${nonce}`,
  };
}

async function createSyntheticUser(request: APIRequestContext, baseURL: string | undefined) {
  const identity = uniquePaymentIdentity();

  const signUpResponse = await request.post(`${baseURL}/v1/users/sign-up`, {
    headers: { 'x-api-key': apiKey },
    data: {
      phone_number: identity.phone,
      email: identity.email,
      password: identity.password,
      first_name: 'Payment',
      last_name: 'Simulator',
      data_processing_consent_accepted: true,
      data_processing_consent_version: 'e2e-payment-process',
    },
  });
  expect(signUpResponse.status()).toBe(201);

  const user = (await signUpResponse.json()) as { user_id: string; email: string };
  expect(user.user_id).toBeTruthy();
  expect(user.email).toBe(identity.email);
  return user;
}

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('payment process: user checks out Case plan and confirms sandbox payment', async ({ request, baseURL }) => {
  const user = await createSyntheticUser(request, baseURL);

  const plansResponse = await request.get(`${baseURL}/v1/users/subscriptions/plans`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(plansResponse.status()).toBe(200);
  const plans = (await plansResponse.json()) as Plan[];
  const casePlan = plans.find((plan) => plan.plan_code === 'case');
  expect(casePlan).toBeTruthy();
  expect(casePlan?.price_eur).toBe(10);

  const checkoutResponse = await request.post(`${baseURL}/v1/users/${user.user_id}/subscriptions/checkout`, {
    headers: { 'x-api-key': apiKey },
    data: { plan_code: 'case', payment_provider: 'paypal' },
  });
  expect(checkoutResponse.status()).toBe(201);
  const checkout = (await checkoutResponse.json()) as CheckoutResponse;

  expect(checkout).toMatchObject({
    plan_code: 'case',
    payment_provider: 'paypal',
    payment_status: 'pending',
    amount_eur: 10,
  });
  expect(checkout.subscription_id).toBeTruthy();
  expect(checkout.payment_id).toMatch(/^PAY-/);
  const checkoutUrl = new URL(checkout.checkout_url);
  expect(checkoutUrl.origin).toBe('https://www.sandbox.paypal.com');
  expect(checkoutUrl.searchParams.get('paymentId')).toBe(checkout.payment_id);
  expect(checkoutUrl.searchParams.get('token')).toBeTruthy();

  const pendingSubscriptionsResponse = await request.get(`${baseURL}/v1/users/${user.user_id}/subscriptions`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(pendingSubscriptionsResponse.status()).toBe(200);
  const pendingSubscriptions = (await pendingSubscriptionsResponse.json()) as SubscriptionResponse[];
  expect(
    pendingSubscriptions.some(
      (subscription) =>
        subscription.subscription_id === checkout.subscription_id &&
        subscription.plan_code === 'case' &&
        subscription.status === 'pending'
    )
  ).toBeTruthy();

  const confirmResponse = await request.post(
    `${baseURL}/v1/users/subscriptions/${checkout.subscription_id}/confirm-payment`,
    {
      headers: { 'x-api-key': apiKey },
      data: { payment_id: checkout.payment_id },
    }
  );
  expect(confirmResponse.status()).toBe(200);
  const confirmedSubscription = (await confirmResponse.json()) as SubscriptionResponse;
  expect(confirmedSubscription).toMatchObject({
    subscription_id: checkout.subscription_id,
    user_id: user.user_id,
    plan_code: 'case',
    status: 'paid',
  });

  const finalSubscriptionsResponse = await request.get(`${baseURL}/v1/users/${user.user_id}/subscriptions`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(finalSubscriptionsResponse.status()).toBe(200);
  const finalSubscriptions = (await finalSubscriptionsResponse.json()) as SubscriptionResponse[];
  expect(
    finalSubscriptions.some(
      (subscription) =>
        subscription.subscription_id === checkout.subscription_id &&
        subscription.plan_code === 'case' &&
        subscription.status === 'paid'
    )
  ).toBeTruthy();
});

test('payment process guards: disabled plans and unknown payments do not activate subscriptions', async ({
  request,
  baseURL,
}) => {
  const user = await createSyntheticUser(request, baseURL);

  const disabledCheckoutResponse = await request.post(
    `${baseURL}/v1/users/${user.user_id}/subscriptions/checkout`,
    {
      headers: { 'x-api-key': apiKey },
      data: { plan_code: 'premium', payment_provider: 'paypal' },
    }
  );
  expect(disabledCheckoutResponse.status()).toBe(503);
  await expect(disabledCheckoutResponse.json()).resolves.toMatchObject({
    detail: 'This subscription plan is coming soon.',
  });

  const checkoutResponse = await request.post(`${baseURL}/v1/users/${user.user_id}/subscriptions/checkout`, {
    headers: { 'x-api-key': apiKey },
    data: { plan_code: 'case', payment_provider: 'google_pay' },
  });
  expect(checkoutResponse.status()).toBe(201);
  const checkout = (await checkoutResponse.json()) as CheckoutResponse;
  expect(checkout.payment_provider).toBe('google_pay');
  expect(new URL(checkout.checkout_url).origin).toBe('https://pay.google.com');

  const wrongPaymentResponse = await request.post(
    `${baseURL}/v1/users/subscriptions/${checkout.subscription_id}/confirm-payment`,
    {
      headers: { 'x-api-key': apiKey },
      data: { payment_id: 'PAY-not-created-by-checkout' },
    }
  );
  expect(wrongPaymentResponse.status()).toBe(404);
  await expect(wrongPaymentResponse.json()).resolves.toMatchObject({ detail: 'Payment not found' });

  const subscriptionsResponse = await request.get(`${baseURL}/v1/users/${user.user_id}/subscriptions`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(subscriptionsResponse.status()).toBe(200);
  const subscriptions = (await subscriptionsResponse.json()) as SubscriptionResponse[];
  const subscription = subscriptions.find((item) => item.subscription_id === checkout.subscription_id);
  expect(subscription?.status).toBe('pending');
});
