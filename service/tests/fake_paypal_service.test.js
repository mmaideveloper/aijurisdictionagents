#!/usr/bin/env node

const assert = require('assert/strict');
const { spawn } = require('child_process');

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const run = async () => {
  const port = 18088;
  const server = spawn('node', ['service/fake_paypal_service.js'], {
    env: { ...process.env, PAYMENT_SERVICE_PORT: String(port), PAYMENT_SERVICE_HOST: '127.0.0.1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let startupLogs = '';
  server.stdout.on('data', (chunk) => {
    startupLogs += chunk.toString('utf-8');
  });
  server.stderr.on('data', (chunk) => {
    startupLogs += chunk.toString('utf-8');
  });

  try {
    for (let i = 0; i < 30; i += 1) {
      try {
        const health = await fetch(`http://127.0.0.1:${port}/health`);
        if (health.ok) {
          break;
        }
      } catch {
        await wait(100);
      }
    }

    const createResponse = await fetch(`http://127.0.0.1:${port}/paypal/payments`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        amount: 12.34,
        currency: 'usd',
        payerEmail: 'buyer@example.com',
        description: 'Test payment',
      }),
    });

    assert.equal(createResponse.status, 201);
    const created = await createResponse.json();
    assert.equal(created.payment.status, 'CREATED');
    assert.ok(created.payment.id.startsWith('PAY-'));

    const executeResponse = await fetch(
      `http://127.0.0.1:${port}/paypal/payments/${created.payment.id}/execute`,
      { method: 'POST' },
    );

    assert.equal(executeResponse.status, 200);
    const executed = await executeResponse.json();
    assert.equal(executed.payment.status, 'COMPLETED');

    const duplicateExecute = await fetch(
      `http://127.0.0.1:${port}/paypal/payments/${created.payment.id}/execute`,
      { method: 'POST' },
    );

    assert.equal(duplicateExecute.status, 409);
    console.log('fake_paypal_service test passed');
  } finally {
    server.kill('SIGTERM');
    await wait(50);
    if (server.exitCode === null) {
      server.kill('SIGKILL');
    }
    if (startupLogs.length > 0) {
      process.stderr.write(startupLogs);
    }
  }
};

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
