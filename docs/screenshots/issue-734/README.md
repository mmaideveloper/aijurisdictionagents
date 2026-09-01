# Issue 734 review evidence

- Scenario: Slovak consumer-advertising video rendered only inside `#article-pravna-pomoc-pre-kazdeho`.
- Final asset: `corporate-web/assets/jurisdigta-pravna-pomoc-sk.mp4`.
- CapCut project: existing project `CE63752E-C3A0-4322-A46F-62407C113E03`.
- Export: MP4, 720 × 1276, 30 fps, approximately 13.08 seconds.
- Final card: approximately 2.5 seconds; approved JurisDigta shield and `www.jurisdigta.eu` remain visible through the last frame.
- Source content: synthetic people and documents only.
- Privacy review: passed; screenshot contains no names, accounts, credentials, customer documents, case facts, or other personal data.
- Homepage impact: none; `corporate-web/assets/jurisdigta-sk.mp4` remains unchanged.
- Test command: `npm run test:e2e` from `corporate-web`.
- Result: 18 passed across desktop Chromium and mobile Chromium.

![Slovak video blog end-card](slovak-video-blog-end-card.png)

Publishing remains subject to human review of the free-start claim, legal disclaimer, brand fidelity, spelling, and music licensing.
