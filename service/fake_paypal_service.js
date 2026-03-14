#!/usr/bin/env node

const http = require('http');
const { randomUUID } = require('crypto');

const host = process.env.PAYMENT_SERVICE_HOST ?? '0.0.0.0';
const port = Number.parseInt(process.env.PAYMENT_SERVICE_PORT ?? '8088', 10);

/** @type {Map<string, {id:string, amount:number, currency:string, payerEmail:string, description:string, status:string, createdAt:string, executedAt:string|null}>} */
const payments = new Map();

const json = (res, code, payload) => {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(payload, null, 2));
};

const parseBody = async (req) => {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  if (chunks.length === 0) {
    return {};
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf-8'));
  } catch {
    const err = new Error('Request body must be valid JSON.');
    err.statusCode = 400;
    throw err;
  }
};

const validateCreatePaymentRequest = (body) => {
  if (typeof body.amount !== 'number' || Number.isNaN(body.amount) || body.amount <= 0) {
    return 'amount must be a positive number';
  }
  if (typeof body.currency !== 'string' || body.currency.trim().length !== 3) {
    return 'currency must be a 3-letter code';
  }
  if (typeof body.payerEmail !== 'string' || !body.payerEmail.includes('@')) {
    return 'payerEmail must be a valid email-like string';
  }
  if (typeof body.description !== 'string' || body.description.trim().length === 0) {
    return 'description must be a non-empty string';
  }
  return null;
};

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);

    if (req.method === 'GET' && url.pathname === '/health') {
      return json(res, 200, {
        service: 'fake-paypal-service',
        status: 'ok',
        payments: payments.size,
      });
    }

    if (req.method === 'POST' && url.pathname === '/paypal/payments') {
      const body = await parseBody(req);
      const validationError = validateCreatePaymentRequest(body);
      if (validationError) {
        return json(res, 400, { error: validationError });
      }

      const paymentId = `PAY-${randomUUID()}`;
      const record = {
        id: paymentId,
        amount: body.amount,
        currency: body.currency.toUpperCase(),
        payerEmail: body.payerEmail,
        description: body.description,
        status: 'CREATED',
        createdAt: new Date().toISOString(),
        executedAt: null,
      };
      payments.set(paymentId, record);

      return json(res, 201, {
        payment: record,
        links: {
          approvalUrl: `https://www.sandbox.paypal.com/checkoutnow?token=${paymentId}`,
          executeUrl: `/paypal/payments/${paymentId}/execute`,
        },
      });
    }

    const executeMatch = url.pathname.match(/^\/paypal\/payments\/(PAY-[a-f0-9-]+)\/execute$/i);
    if (req.method === 'POST' && executeMatch) {
      const paymentId = executeMatch[1];
      const payment = payments.get(paymentId);
      if (!payment) {
        return json(res, 404, { error: 'Payment not found' });
      }
      if (payment.status === 'COMPLETED') {
        return json(res, 409, { error: 'Payment already completed', payment });
      }
      payment.status = 'COMPLETED';
      payment.executedAt = new Date().toISOString();
      return json(res, 200, {
        message: 'Payment executed in fake PayPal sandbox.',
        payment,
      });
    }

    const getMatch = url.pathname.match(/^\/paypal\/payments\/(PAY-[a-f0-9-]+)$/i);
    if (req.method === 'GET' && getMatch) {
      const paymentId = getMatch[1];
      const payment = payments.get(paymentId);
      if (!payment) {
        return json(res, 404, { error: 'Payment not found' });
      }
      return json(res, 200, { payment });
    }

    return json(res, 404, {
      error: 'Not found',
      availableEndpoints: [
        'GET /health',
        'POST /paypal/payments',
        'GET /paypal/payments/:id',
        'POST /paypal/payments/:id/execute',
      ],
    });
  } catch (error) {
    return json(res, error.statusCode ?? 500, {
      error: error.message ?? 'Unexpected server error',
    });
  }
});

server.listen(port, host, () => {
  console.log(`Fake PayPal service is running at http://${host}:${port}`);
});
