# Dashboard verification

Recorded 25 October 2026 on Windows with Chromium 156 and Lighthouse 13.5.0.
The six real-data routes were audited with default mobile simulation against the
gzip-enabled local production build. The measured scores are retained in
`lighthouse.json`; all meet the project's 95-point floor.

| Page           | Performance | Accessibility | Best practices |
| -------------- | ----------- | ------------- | -------------- |
| Market         | 96          | 100           | 100            |
| Price drops    | 95          | 100           | 100            |
| Seasons        | 98          | 100           | 100            |
| Drivers        | 99          | 100           | 100            |
| Fair price     | 99          | 100           | 100            |
| About the data | 99          | 100           | 100            |

The initial JS bundle is approximately 74KB gzip; the deferred chart bundle is
approximately 119KB, for a total below the 250KB budget. Charts below the viewport
defer their download and render until they enter view, with an explicit keyboard
load action. Their reserved height avoids moving later content while loading.

Verification includes ESLint, Prettier, strict TypeScript, unit/component tests,
100% coverage of the pure frontend helpers, twenty Python/TypeScript prediction
references, and sixteen production-browser scenarios. The visual/accessibility
matrix spans six pages, two themes, two viewport sizes and real/synthetic data:
48 saved views with no axe violations. Browser scenarios also exercise keyboard
navigation, blocked storage, malformed/mixed refreshes, retry, failed chart downloads,
focus preservation, dependent car inputs, price validation and filter resets.

The current production bundle contains 90 listings on one observation day. Sparse
analyses and Fair Price Check remain explicitly unavailable on that real sample;
populated-model behavior is checked with separate synthetic fixtures. Deployment
and the longer collection-volume goals remain separate from this local UI verification.
