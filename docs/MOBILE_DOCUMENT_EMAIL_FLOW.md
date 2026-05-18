# Mobile Document Email Flow

The mobile document email flow lives in
`mobile_app/lib/chat/document_email_flow.dart`.

## State Machine

The state order is:

`requested -> generating -> ready -> awaiting_email_confirmation -> sending -> sent/failed`

The mobile client normalizes backend and chat simulator stages before updating
the state machine. Existing simulator/API events such as
`document_package_ready`, `document_ready`, and `document_status` with
`details.status=ready` map to the mobile event
`DocumentEmailMobileEvent.documentPackageReady` and state `ready`.

## Safety And Compliance

The flow treats the recipient email address as personal data. It does not send
documents automatically when the backend reports that a package is ready.
Before sending, it reads the normalized recipient address aloud and waits for an
explicit spoken confirmation parsed as "yes" or "áno". A rejection or timeout
moves the flow to `failed` without calling the backend.

This preserves GDPR data minimization and EU AI Act human-oversight safeguards:
the client stores only the current recipient, state, attempt count, and backend
email id, and the retry logic never logs or stores document contents.

## Retry Policy

Temporary send failures are retried with bounded exponential backoff. Permanent
backend failures fail immediately. The default policy uses three attempts.

## Minimal Example

Run the mobile-specific example with:

```powershell
cd mobile_app
dart run examples/document_email_flow_demo.dart
```

The repository-level minimal example remains:

```powershell
python examples/minimal_demo.py
```
