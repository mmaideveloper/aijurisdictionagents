# Manual Infrastructure Setup

This document tracks infrastructure setup that cannot be completed only by repository code, CI, or local scripts.

## Rule

Whenever a task adds or changes manual infrastructure requirements, update this file in the same change. Include:

- Provider or portal name.
- Required account or owner.
- Test and production environment steps.
- Secrets, environment variables, certificates, keys, callback URLs, domains, or app identifiers.
- Validation steps after setup.
- Rollback or deletion steps.
- GDPR and EU AI Act notes when personal data, legal-risk outputs, or user transparency are involved.

Do not commit real secrets, private keys, certificates, Firebase config files containing sensitive project data, or Apple credentials.

## Firebase Cloud Messaging For Document-Ready Mobile Push

Related task: https://github.com/mmaideveloper/aijurisdictionagents/issues/343

Purpose: send privacy-safe Android and iOS push notifications when a user's document package is ready.

### Provider Decision

Use Firebase Cloud Messaging directly.

- Android receives push notifications through FCM.
- iOS receives push notifications through APNs configured in Firebase/FCM.
- Do not use Azure Notification Hubs for this task unless a later task explicitly changes the provider decision.

### Manual Setup Steps

1. Create or select the Firebase project for JurisDigta.
2. Enable Firebase Cloud Messaging.
3. Register the Android app using the production Android package name.
4. Download the Android Firebase configuration file required by Flutter/Android setup.
5. Register the iOS app using the production iOS bundle identifier.
6. Download the iOS Firebase configuration file required by Flutter/iOS setup.
7. In Apple Developer, create or identify the APNs key/certificate for JurisDigta push notifications.
8. Upload the APNs key/certificate details to Firebase for the iOS app.
9. Create a Firebase service account or workload identity configuration for the backend sender.
10. Store backend Firebase credentials in GitHub Environments and Azure runtime secrets for `test` and `prod`.
11. Add documented example entries to `.env.example` for any new local configuration variables.
12. Update `docs/GITHUB_ENVIRONMENTS.md` with the exact required GitHub Environment secrets and variables for `test` and `prod`.
13. Configure mobile deep links/universal links for opening the ready document view from a notification.
14. Verify Android push delivery on a physical or emulator device with Google Play services.
15. Verify iOS push delivery on a physical iOS device.
16. Verify notification tap opens the authenticated document view or a safe loading/error state.

### Privacy And Compliance Notes

- Require explicit user opt-in before registering a device token for document-ready notifications.
- Provide localized consent and notification text per supported country/language.
- Delete or deactivate device tokens on opt-out, logout where applicable, and account deletion.
- Push payloads must not contain document text, legal facts, case names, party names, email addresses, or other personal data beyond the minimum routing data.
- Notification text should stay generic, for example: `Documents are ready` and `Open JurisDigta to review them`.
- Document URLs or deep links must be authenticated or short-lived/signed and must not expose document contents or sensitive metadata.
- Logs must redact device tokens and avoid document contents or legal facts.

### Rollback Notes

- Disable the backend push sender configuration if push delivery causes operational issues.
- Keep document generation and in-app document-ready status functional even when push sending is disabled.
- Revoke compromised Firebase service account credentials immediately and rotate the corresponding GitHub/Azure secrets.
