# Task #243 Implementation Prep

## Task

- Issue: `#243`
- Title: `language switching`
- Frontend project board: `mmaideveloper/projects/6`
- Current board status at prep time: `Backlog`
- Prep branch: `feature/task-243-prepare-implementation`

Issue summary:

- Improve the language switching.
- When a language is chosen from the language menu, the currently opened page should translate into that language immediately.
- When routing to another page, the chosen language should stay active until the user selects a different language.

## Current State

What already works:

- Frontend language state is centralized in `frontend/aijurisdictionfronend/src/components/LanguageProvider.tsx`.
- The selected language is already persisted in `localStorage` under `aj_frontend_lang`.
- The language selection already survives route changes and browser refresh because the provider wraps the router in `frontend/aijurisdictionfronend/src/main.tsx`.
- Many public-page and profile strings already come from `frontend/aijurisdictionfronend/src/data/translations.ts`.

What is still blocking full-page translation:

- Several signed-in workspace surfaces still use hardcoded English strings instead of translation keys.
- Important untranslated files currently include:
  - `frontend/aijurisdictionfronend/src/pages/Home.tsx`
  - `frontend/aijurisdictionfronend/src/components/WorkspaceWelcome.tsx`
  - `frontend/aijurisdictionfronend/src/components/Sidebar.tsx`
  - `frontend/aijurisdictionfronend/src/components/PageLayout.tsx`
  - `frontend/aijurisdictionfronend/src/state/CaseProvider.tsx`
- Seeded mock case data and system-generated interaction text in `CaseProvider.tsx` are English-only, so switching languages does not fully translate the signed-in workspace today.
- The API request language in `frontend/aijurisdictionfronend/src/api/chatClient.ts` is currently driven by `VITE_API_LANGUAGE`, not by the selected UI language.

## Recommended Implementation Scope

1. Audit every visible app-owned string on the currently supported routes and move missing copy into `translations.ts`.
2. Replace hardcoded strings in the signed-in workspace with `useLanguage().t(...)`.
3. Localize app-owned seeded mock data and system-generated labels/messages used in the sidebar, workspace, and profile views.
4. Keep user-provided content unchanged.
   - Case titles entered by users should remain exactly as entered.
   - Uploaded filenames should remain exactly as uploaded.
5. Review whether the selected UI language should also be sent through the chat API client.
   - Recommended assumption for implementation: align API message language with the selected UI language unless that causes regressions with existing API expectations.
6. Add or update frontend tests to verify immediate on-page translation and persistence after route navigation.
7. Add a task-specific runnable example during implementation.

## Likely Files To Touch During Implementation

- `frontend/aijurisdictionfronend/src/data/translations.ts`
- `frontend/aijurisdictionfronend/src/components/LanguageProvider.tsx`
- `frontend/aijurisdictionfronend/src/components/LanguageSwitcher.tsx`
- `frontend/aijurisdictionfronend/src/components/Sidebar.tsx`
- `frontend/aijurisdictionfronend/src/components/WorkspaceWelcome.tsx`
- `frontend/aijurisdictionfronend/src/components/PageLayout.tsx`
- `frontend/aijurisdictionfronend/src/pages/Home.tsx`
- `frontend/aijurisdictionfronend/src/pages/Profile.tsx`
- `frontend/aijurisdictionfronend/src/state/CaseProvider.tsx`
- `frontend/aijurisdictionfronend/src/__tests__/...`
- `frontend/aijurisdictionfronend/README.md`
- `examples/frontend_language_switching_task_243_minimal_demo.py`

## Acceptance Checklist For Implementation

- Changing the language from the navbar switcher updates the currently open page immediately.
- Routing to a different page keeps the selected language active.
- Public pages and signed-in workspace pages do not show leftover app-owned English strings when `sk` or `de` is selected.
- Sidebar labels, workspace labels, CTA text, placeholders, and profile labels are translated.
- App-owned seeded mock text is translated consistently.
- Tests cover at least:
  - immediate language switch on the current route
  - language persistence after navigation
  - signed-in workspace translation for at least one authenticated route

## Validation Plan For Implementation

- `cd frontend/aijurisdictionfronend`
- `npm run lint`
- `npm run test`
- `python examples/minimal_demo.py`
- `python examples/frontend_language_switching_task_243_minimal_demo.py`

## Notes

- No conda activation was used for this prep because this is a frontend task.
- The worktree already contained an unrelated untracked file: `databases/api.sqlite3`. It was intentionally left untouched.
