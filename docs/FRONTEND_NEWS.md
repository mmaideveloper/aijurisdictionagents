# Frontend News Page

The React frontend exposes public product updates at `/aktuality` through `frontend/aijurisdictionfronend/src/pages/News.tsx`.

News copy is translation-driven in `frontend/aijurisdictionfronend/src/data/translations.ts`. Each new item should include Slovak, English, and German text so the language switcher never renders a raw translation key.

Compliance-oriented updates must stay informational: do not expose user identifiers, provider credentials, prompts, or model secrets in news copy. For AI model and routing announcements, mention governance, data minimization, auditability, and human oversight when the feature can affect legal-risk outputs.

Run the focused news-page regression after changes:

```powershell
cd frontend\aijurisdictionfronend
npm test -- --run src/__tests__/newsPage.test.tsx
```
