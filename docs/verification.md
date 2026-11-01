# Verification — AA Accountant 0.1.5

Verified on November 1, 2026 with Python 3.12.14, Alliance Auth 5.6.0, Django 5.2.18, django-esi 10.1.0 and SQLite. ESI, SSO credentials, the Celery broker and Redis are test doubles; this does not claim a live corporation import or production deployment.

| Requirement | Implementation and evidence |
| --- | --- |
| AA module, menu, routes, permissions | `auth_hooks.py`; real AA URL loading, permission and template tests; rendered in AA's native frame |
| User-provided ESI authorization | AA `token_required`, token owner/scope checks, POST/CSRF handling; callback and token-selection tests |
| Corporation identity and wallet roles | `EsiClient.identity`; tested corporation, role and wallet-access checks, changed membership and missing tokens |
| Multiple corporations and divisions | Corporation/division models; repeat authorization, seven-division discovery, multi-source report and dispatch tests |
| Retained journal storage and deduplication | Database uniqueness and bulk upsert by division/entry ID; repeat pull, corrected entry, same ID across divisions and exact-value tests |
| All ESI journal pages | Explicit `X-Pages` pagination, tested with two pages and ten pages of 1,000 distinct entries; repeat-sync test confirms retained entries survive after leaving ESI's response window |
| Atomic imports and safe failures | Later-page failure rolls back a division; successful retry, source status and secret-redaction tests |
| Daily task / midnight example | `sync_all` task and README plain `crontab` local.py schedule, using the AA installation's Celery timezone; daily dispatch tests |
| Default six whole prior months | `retention_cutoff`, import floor, cleanup and export floor; July/January, August/February, year-boundary and configuration validation tests |
| Export page and CSV | Streaming corpus/division CSV with inclusive UTC range; permission isolation, full-history, transfer, exact-value, multiline text and formula safety tests |
| Named per-dashboard source selection | Dashboard model and admin; multi-corporation and multi-division report tests |
| Revenue/expense signs | Independent positive/negative sections, subtotal and net calculations; mixed-sign, zero and missing amount tests |
| Ref type human labels and row/Other/ignore | Dashboard rules, unknown-type policy, exclusion from totals and ordering tests |
| Predefined reference type selector | Exact comparison against the 162-value user-supplied list; names for every type; both real admin editors render dropdowns; blank-name defaults, custom names, legacy identifiers and duplicate-rule validation tested |
| Automatic display names | Chromium checks select types and fill the corresponding name in the standalone form and dynamically added dashboard inline rows, while preserving customized names and other rows |
| Reason match types and Other | Exact/contains with sensitive/insensitive case modes; Unicode case folding, literal keywords, blank/missing reasons, whitespace preservation and default exact behavior tested; first match by order/ID prevents overlap from double-counting, with dashboard/ref-type scoping and unchanged monthly/corporation totals |
| Shared reason display names | Identical names merge within each ref type; tests cover multiple keywords, overlapping matches counted once, monthly/corporation totals, separate revenue/expenses, mixed match modes, ordering without matches for the first rule, distinct capitalization, renaming and separation from the automatic Other reasons bucket |
| Internal transfer exclusion | Party-ID/ref-type classification; one-sided same-corporation transfer, cross-selected-corporation policy and external payment tests |
| Storage character/corporation exclusion | Per-dashboard admin rules match either party ID for every ref type, sign, selected source and month; tests verify disjoint exclusion counts, preserved raw entries/CSV exports, independent dashboards, reversible exclusion and positive/unique IDs |
| Corporation drill-down | Recursive statement rows; merging several divisions of one corporation; browser checks expand category → reason → two corporations and collapse descendants |
| Full / million / billion ISK | Decimal formatter with exactly two decimal places and trailing zeros, space grouping, default billion unit; whole, fractional, negative and zero display values tested; full precision remains in hover text and CSV |
| Full monthly statement | Twelve UTC calendar-month columns, totals, current MTD marker and unavailable-month distinction; month/cutoff/year tests |
| Access restrictions | Real AA main-character gate plus plugin permissions and per-dashboard groups; anonymous, unauthorized, hidden dashboard and forged export selection tests |
| Installation package | Wheel and sdist built; 0.1.0 installed-wheel app loading, fresh migrations and system checks verified outside the source checkout; 0.1.1 adds the catalog and admin JavaScript without schema changes |

Final automated results: **81 pytest tests passed**; Ruff checks and formatting passed; Django system checks found no issues; migration drift check found no changes. Three new report tests verify merging shared reason display names, and the real admin form test checks the grouping help text. Version 0.1.5 requires no new migration. The 0.1.5 wheel matches source and includes the existing migrations.

Earlier 0.1.4 verification: real admin form tests saved a case-insensitive contains rule and verified its effect on reporting. Chromium checked all four options, saved an uppercase keyword that matches the lowercase demo reason as a substring, verified unchanged category/net totals, and restored the original rule. The upgrade migration preserved existing reason text, names, order and journal entries, with all existing rules defaulting to exact matching. Earlier storage exclusion, reference type selector and desktop/mobile statement checks also passed. Screenshots are under `output/`.

The deployer must provide their existing AA installation, live EVE SSO credentials, an authorized corporation character, a running worker/beat/broker and production database. MySQL was not exercised in this macOS environment; the ORM import supports Django's MySQL upsert branch as well as SQLite. ESI's initial history is capped by both age and entry count, so retained history grows after installation.

