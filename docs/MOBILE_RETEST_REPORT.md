# Mobile App Retest Report

## Scope
Retest requested areas:
- AIUserSimulator automatic ask/answer flow.
- PDF document creation and download from mobile app.
- Language and country selection behavior.
- AIAgentsValidator final accuracy score.
- Law citation presence and click-through redirect behavior.

## Test Execution Summary

### 1) AIUserSimulator ask/answer flow
**Result:** ✅ PASS (backend agent logic)

Executed unit tests for agent behavior and orchestrated flow:
- `tests/test_agents.py`
- `tests/test_orchestrator.py`

These verify simulator agent creation/use and orchestrated message progression, including citations in orchestrator output.

### 2) PDF creation/download from mobile app
**Result:** ❌ FAIL (feature not present in current mobile UI code)

Retest found no mobile UI actions or API calls wired for:
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary`
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document`

The current Flutter app code includes chat/session/reply/stream and document-path attachment, but no explicit PDF export/download button or handler.

### 3) Language and country selection
**Result:** ✅ PASS (implemented in mobile UI)

Retest confirms a `Language & Country` dropdown exists with locale options and session reset on change.

### 4) AIAgentsValidator final accuracy score
**Result:** ✅ PASS

`python examples/validator_demo.py` output:
- **Weighted accuracy: 66.97**

### 5) Citation from law + clickable redirect
**Result:** ❌ FAIL (not implemented in current mobile UI)

Retest confirms:
- Backend/orchestrator tests validate citation objects exist.
- Current mobile chat bubble rendering displays message text only and does not render citation links or click handlers for source redirect.

## Environment Notes
- Flutter CLI is not installed in this environment (`flutter: command not found`), so widget/integration tests could not be executed here.
- Python backend test coverage used as primary executable validation.

## Recommendation
To fully satisfy mobile citation and PDF requirements:
1. Add API client methods for export endpoints.
2. Add UI controls for summary/document PDF download/open.
3. Extend message model to include source citations with URL/path metadata.
4. Render citations as tappable links and open source documents via a URL launcher / in-app webview.
5. Add Flutter widget/integration tests for locale selection, export buttons, and citation link taps.

## 0.1.3+4 hotfix notes (auth/orientation)
- Added Android-oriented autofill hints (`telephoneNumberDevice`) for both sign-in and sign-up phone fields so the OS can propose the device phone number during login/registration.
- Wrapped the auth tabs with an `AutofillGroup` to improve autofill session behavior on Android.
- Reworked auth screen layout sizing to be responsive after orientation changes (landscape -> portrait), replacing a rigid fixed panel with viewport-aware height and outer scroll support so registration controls remain reachable.

### Minimal runnable example
- Backend sanity demo (project default): `python examples/minimal_demo.py`

## 0.1.3+5 release update
- Bumped Flutter mobile app version from `0.1.3+4` to `0.1.3+5` in `mobile_app/pubspec.yaml`.
- Performed a dev sign-in verification attempt for phone `+421944400166` via `POST /v1/users/sign-in/phone` with API key `aijuris`.
- Current environment does not expose a configured dev API URL (`AIJ_PUBLIC_DEV_API_URL`, `PUBLIC_DEV_API_BASE_URL`, or `API_BASE_URL`), so remote dev login could not be executed from this runner.

### Minimal runnable example
- `python examples/minimal_demo.py`
