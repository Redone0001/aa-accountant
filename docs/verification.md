# Verification — AA Accountant 0.1.0

Verified on November 1, 2026 with Python 3.12.14, Alliance Auth 5.6.0, Django 5.2.18, django-esi 10.1.0 and SQLite. ESI, SSO credentials, the Celery broker and Redis are test doubles; this does not claim a live corporation import or production deployment.

| Requirement | Implementation and evidence |
| --- | --- |
| AA module, menu, routes, permissions | `auth_hooks.py`; real AA URL loading, permission and template tests; rendered in AA's native frame |
| User-provided ESI authorization | AA `token_required`, token owner/scope checks, POST/CSRF handling; callback and token-selection tests |
| Corporation identity and wallet roles | `EsiClient.identity`; tested corporation, role and wallet-access checks, changed membership and missing tokens |
| Multiple corporations and divisions | Corporation/division models; repeat authorization, seven-division discovery, multi-source report and dispatch tests |
| Retained journal storage and deduplication | Database uniqueness and bulk upsert by division/entry ID; repeat pull, corrected entry, same ID across divisions and exact-value tests |
| All ESI journal pages | Explicit `X-Pages` pagination, tested with two pages; verified against CCP's current OpenAPI specification |
| Atomic imports and safe failures | Later-page failure rolls back a division; successful retry, source status and secret-redaction tests |
| Daily task / midnight example | `sync_all` task and README plain `crontab` local.py schedule, using the AA installation's Celery timezone; daily dispatch tests |
| Default six whole prior months | `retention_cutoff`, import floor, cleanup and export floor; July/January, August/February, year-boundary and configuration validation tests |
| Export page and CSV | Streaming corpus/division CSV with inclusive UTC range; permission isolation, full-history, transfer, exact-value, multiline text and formula safety tests |
| Named per-dashboard source selection | Dashboard model and admin; multi-corporation and multi-division report tests |
| Revenue/expense signs | Independent positive/negative sections, subtotal and net calculations; mixed-sign, zero and missing amount tests |
| Ref type human labels and row/Other/ignore | Dashboard rules, unknown-type policy, exclusion from totals and ordering tests |
| Exact reason matching and Other | Reason rules and fallback with corporation children; exact, case mismatch, trailing whitespace and missing reason tests; admin preserves whitespace |
| Internal transfer exclusion | Party-ID/ref-type classification; one-sided same-corporation transfer, cross-selected-corporation policy and external payment tests |
| Corporation drill-down | Recursive statement rows; merging several divisions of one corporation; browser checks expand category → reason → two corporations and collapse descendants |
| Full / million / billion ISK | Decimal formatter, space grouping, default billion unit; format and browser unit-switch tests; full precision remains in hover text and CSV |
| Full monthly statement | Twelve UTC calendar-month columns, totals, current MTD marker and unavailable-month distinction; month/cutoff/year tests |
| Access restrictions | Real AA main-character gate plus plugin permissions and per-dashboard groups; anonymous, unauthorized, hidden dashboard and forged export selection tests |
| Installation package | Wheel and sdist built; wheel assets compared byte-for-byte against all 32 plugin source/template/static files; installed wheel loaded outside the source checkout, migrated into a fresh database, and passed Django checks |

Final automated results: **35 pytest tests passed**; Ruff checks and formatting passed; Django system checks found no issues; migration drift check found no changes. Chromium checks passed for desktop nested rows, collapse/expand, unit switching and mobile statement scrolling. Screenshots are under `output/`.

The deployer must provide their existing AA installation, live EVE SSO credentials, an authorized corporation character, a running worker/beat/broker and production database. MySQL was not exercised in this macOS environment; the ORM import supports Django's MySQL upsert branch as well as SQLite. ESI can initially return only its 30-day journal window, so retained history grows after installation.

