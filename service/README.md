# Fake PayPal Payment Service

A lightweight local fake payment service that simulates a subset of the PayPal payment flow.

## Run

```bash
node service/fake_paypal_service.js
```

Environment variables:

- `PAYMENT_SERVICE_HOST` (default `0.0.0.0`)
- `PAYMENT_SERVICE_PORT` (default `8088`)

## Endpoints

- `GET /health`
- `POST /paypal/payments`
- `GET /paypal/payments/:id`
- `POST /paypal/payments/:id/execute`

## Minimal runnable example

1. Start the service:

```bash
node service/fake_paypal_service.js
```

2. In another terminal run:

```bash
./service/examples/paypal_payment_demo.sh
```

The script creates a payment, fetches it, and executes it.

## Local test

```bash
node service/tests/fake_paypal_service.test.js
```
