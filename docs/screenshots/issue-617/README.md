# Issue 617 E2E evidence

`issue-617-admin-users-after-retry.png` is the reviewed final-state screenshot produced by:

```powershell
cd frontend/aijurisdictionfronend
.\node_modules\.bin\playwright.cmd test e2e/issue-617-admin-sidebar-retry.spec.ts
```

The scenario aborts the initial Admin dashboard request, verifies that the failure is not presented as a valid empty grid, clicks **Users**, and proves that a second authenticated backend request returns a confirmed empty result. It uses only the synthetic `issue-617-admin@example.test` identity and does not retain the synthetic device token in the screenshot or result manifest.

The committed PNG is retained as issue/PR acceptance evidence. Transient output under `runs/e2e/issue-617/` contains the final screenshot and machine-readable result manifest and follows the seven-day retention rule in `docs/E2E_TEST_EVIDENCE_RULE.md`.
