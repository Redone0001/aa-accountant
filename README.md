# AA Accountant

An installable Alliance Auth plugin for retained corporation wallet journals and named monthly profit-and-loss dashboards. It follows AA's menu, URL, permission, SSO, Django admin, migration, and Celery conventions. The implementation is original; the [AA example plugin](https://apps.allianceauth.org/apps/detail/aa-example-plugin) is the structural reference.

## Requirements

- Alliance Auth 5.x, Python 3.10+, Django 5.2, django-esi 10.x.
- A working AA EVE SSO setup, Celery worker, beat scheduler, and database.
- An authorized character in each corporation with Accountant, Junior Accountant, Director or CEO access. ESI remains the authority for wallet access.

## Install

In your existing AA virtual environment, install from the public [GitHub repository](https://github.com/Redone0001/aa-accountant):

```sh
pip install git+https://github.com/Redone0001/aa-accountant.git
```

Add to your AA `settings/local.py`:

```python
from celery.schedules import crontab

INSTALLED_APPS += ["accountant"]

# Current partial month + six complete preceding UTC calendar months.
ACCOUNTANT_RETENTION_MONTHS = 6

# Daily at midnight, using your AA installation's Celery timezone.
CELERYBEAT_SCHEDULE["accountant_daily_sync"] = {
    "task": "accountant.tasks.sync_all",
    "schedule": crontab(minute=0, hour="0"),
}
```

Add these scopes to the allowed scopes of your existing EVE developer application:

```text
esi-wallet.read_corporation_wallets.v1
esi-characters.read_corporation_roles.v1
```

Then run:

```sh
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
```

Restart your AA web services, Celery workers, and Celery beat using your deployment's service manager. Only run one beat scheduler. The menu entry and `/accountant/` routes are registered by AA hooks; no project URL changes are needed.

### Permissions and initial configuration

1. Grant readers `accountant.view_dashboard` through AA groups/states.
2. Grant trusted source administrators `accountant.manage_sources`. They can connect/replace tokens and queue imports for all connected corporations. They need `view_dashboard` too to see the menu.
3. Grant `accountant.export_journal` to users who may download history. Readers can export divisions used by their visible dashboards. Source administrators with this permission can export every division.
4. Open **Accountant → Wallet sources → Connect / reauthorize corporation** and choose an AA token or complete EVE SSO. A character is checked against its current corporation and roles. Repeat for every corporation. Tokens and refresh secrets stay in django-esi's token store.
5. In Django admin → **AA Accountant → Corporations**, rename divisions as desired or disable imports for unused divisions. All seven returned wallet divisions are enabled initially. Disabling import preserves already stored history until retention prunes it.
6. In **Dashboards**, create a named dashboard, choose the wallet divisions across any corporations, and select its default ISK unit. If allowed groups is empty, all users with `view_dashboard` may view it. Otherwise only those groups (and superusers) may view it. Staff status alone does not bypass this restriction.
7. Add reference type rules inline. Use their change link, or **Ref type rules**, to add reason rules. Staff configuration access uses Django's ordinary per-model admin permissions. Configuration administrators are trusted to choose the data and groups a dashboard exposes.

## Category rules

Rules are per dashboard, so the same journal can produce different reports without rewriting stored history.

| Backend value | Display name | Mode | Split reasons |
| --- | --- | --- | --- |
| `bounty_prizes` | Bounty prizes | Separate row | No |
| `player_donation` | Contributions | Separate row | Yes |
| `corporation_account_withdrawal` | Payments | Separate row | Yes |
| `brokers_fee` | Market fees | Bundle into Other | No |
| `market_escrow` | Market escrow | Ignore | No |

For Contributions, add exact reason values such as `moon_rent` → **Moon rentals** and `corp_dues` → **Corporation dues**. Matching is case-sensitive and includes whitespace; inspect the raw CSV to find the ESI reason value. An unmatched or empty reason is grouped into **Other reasons**. Human names never participate in matching.

**Separate row** creates its own category; **Bundle into Other** merges into the section's Other row; **Ignore** excludes entries from both rows and totals. Unknown ref types follow the dashboard's unconfigured mode, initially Other. Reasons are subdivided only for separate rows.

Positive entries appear under revenue and negative entries under expenses. A category containing both signs appears in both sections, with separate totals. Zero or missing amounts do not contribute. Expand categories, then reason rows, to see each corporation's contribution across its selected divisions. Several divisions of one corporation merge into one corporation row. Expand all / Collapse all are keyboard accessible.

### Internal transfers

`corporation_account_withdrawal` entries whose first and second parties both equal the journal's corporation ID are always excluded. This covers the −30 B / +30 B division transfer in the supplied example, even when only one side's division is selected.

By default, that ref type is also excluded when both parties are corporations selected by the dashboard. Turn off **Exclude between selected corporations** to count those cross-corporation payments. External withdrawals and payments to characters still count. Transfers are classified by ref type and party IDs, never by coincidentally equal amounts. All raw entries remain available in CSV exports, including ignored categories and transfers. The export marks same-corporation transfers; cross-corporation exclusion depends on the dashboard configuration.

## Time, precision, and retention

- Reports show January–December for a selected year, monthly totals, annual totals, and net profit/loss. Months outside retention or in the future show `—`. The current month is marked MTD. Totals reflect only retained, imported entries; an uninitialized or failed source is shown below the statement.
- UTC defines journal months and inclusive export dates. The daily schedule uses your AA installation's Celery timezone.
- Six months retention means **current partial month plus six whole preceding calendar months**. On July 15, January 1 remains and the preceding December is removed. On August 1, January is removed. Retention applies globally to stored journals, including disabled sources; raw exports also honor the cutoff before the next cleanup runs.
- Imports request all journal pages every time, then upsert by `(wallet division, ESI journal ID)`. The same ID in different divisions must be retained to preserve both sides of transfers. Retried/overlapping pulls do not duplicate transactions. A failed later page rolls back that division's import; already stored data is not lost. Sources show attempt time, successful sync time and a safe error message.
- The first pull can recover only ESI's roughly **30-day journal window**. Retention cannot backfill older months. Daily imports build the longer local history; extended outages can cause unrecoverable gaps. No fabricated historical data is inserted.
- Money is decoded as Decimal before JSON can turn it into a float and stored with two decimal places. Reports aggregate Decimal values, and CSV exports retain full two-decimal ISK values. Display units affect presentation only. Full ISK uses spaces (`10 000`), millions use `100 M. isk`, and billions use `0.1 B. isk` (default). Hover any amount for full ISK. Very small nonzero values show `<0.01` at the selected scale.
- ESI requests use a fixed compatibility date, contact user agent, 30-second timeout, and explicit pagination. Temporary connection, rate-limit and server failures retry through Celery with exponential backoff. Other corporations are dispatched independently. Revoked tokens, changed membership, or lost roles require reauthorization and do not erase history.

## Export and operations

**Export history** selects a corporation/division and optional inclusive UTC date range. Empty dates export all retained history. CSV includes transaction IDs, parties, reason, description, amount, balance, tax and context. It streams rows instead of holding the full export in memory. Untrusted formula-like text gets an apostrophe prefix for spreadsheet safety; monetary numbers are unaffected.

For an immediate synchronous import or retention cleanup in an AA shell:

```sh
python manage.py accountant_sync
python manage.py accountant_sync --corporation-id 123456789
python manage.py accountant_sync --prune-only
```

The daily `sync_all` task prunes history before dispatching corporation imports. Monitor Celery failures and Wallet sources. Back up the AA database as usual; deleting a source or division cascades its journal history. Reducing retention permanently removes older journal rows on the next cleanup.

## Development and verification

```sh
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/python -m build --no-isolation
```

`manage.py` uses the included development settings and real AA apps with SQLite. Production uses your existing AA project's `manage.py`. On macOS, AA's MySQL driver may require MySQL client development libraries to install, even though local tests use SQLite. Tests mock ESI and the broker and never require real tokens. A live deployment still needs its own EVE SSO credentials and a role-bearing character for an end-to-end import.

For a fictional local preview, run `.venv/bin/python -m tests.preview`, then `.venv/bin/python manage.py runserver 127.0.0.1:8000`. The preview has no password or ESI credentials. Its local development session is saved to `output/preview-session.txt`; the optional Playwright check `node tests/browser-smoke.cjs` uses that session to exercise nested expansion, unit changes, and desktop/mobile layouts, and saves screenshots under `output/`. Install Playwright/Chromium in your Node environment to run that check. The preview script refuses to run with production settings.

Primary references: [AA URL hooks](https://allianceauth.readthedocs.io/en/latest/development/custom/url-hooks.html), [AA menu hooks](https://allianceauth.readthedocs.io/en/latest/development/custom/menu-hooks.html), [django-esi token flow](https://django-esi.readthedocs.io/en/latest/developer.html), [CCP ESI specification](https://esi.evetech.net/meta/openapi.json).
