"""Create a local, fictional preview using development settings only.

Run: .venv/bin/python -m tests.preview
Then: .venv/bin/python manage.py runserver 127.0.0.1:8000
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
if os.environ["DJANGO_SETTINGS_MODULE"] != "tests.settings":
    raise RuntimeError("The preview is restricted to the bundled local development settings.")

import django  # noqa: E402

django.setup()

from allianceauth.authentication.models import UserProfile  # noqa: E402
from allianceauth.eveonline.models import EveCharacter  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils.timezone import now  # noqa: E402

from accountant.models import (  # noqa: E402
    Corporation,
    Dashboard,
    JournalEntry,
    ReasonRule,
    RefTypeRule,
    WalletDivision,
)

call_command("migrate", verbosity=0)
at = now()
user, _ = User.objects.get_or_create(username="accountant-preview")
user.is_superuser = user.is_staff = True
user.set_unusable_password()
user.save()
character, _ = EveCharacter.objects.get_or_create(
    character_id=90000099, defaults={"character_name": "Preview Accountant"}
)
UserProfile.objects.filter(user=user).update(main_character=character)
board, _ = Dashboard.objects.get_or_create(
    name="Alliance treasury · Demo",
    defaults={"description": "Fictional sample data · Two corporations, one financial picture."},
)
divisions = []
for index, name in enumerate(["Northstar Industries", "Orbital Logistics"]):
    corp, _ = Corporation.objects.get_or_create(
        corporation_id=98000001 + index, defaults={"name": name, "enabled": False}
    )
    division, _ = WalletDivision.objects.get_or_create(
        corporation=corp, division=1, defaults={"name": "Operations", "last_success": at}
    )
    divisions.append(division)
board.divisions.set(divisions)
rules = [
    ("bounty_prizes", "Bounty prizes", "", Decimal("42.81")),
    ("industry_job_tax", "Industry job tax", "", Decimal("28.46")),
    ("player_donation", "Contributions", "moon_rent", Decimal("35.20")),
    ("brokers_fee", "Market fees", "", Decimal("8.17")),
    ("corporation_account_withdrawal", "Payments", "srp", Decimal("-48.31")),
    ("market_transaction", "Fuel and supplies", "", Decimal("-12.90")),
]
for order, (ref_type, label, reason, amount) in enumerate(rules):
    rule, _ = RefTypeRule.objects.get_or_create(
        dashboard=board,
        ref_type=ref_type,
        defaults={"display_name": label, "split_reasons": bool(reason), "order": order},
    )
    if reason:
        ReasonRule.objects.get_or_create(
            ref_rule=rule,
            reason=reason,
            defaults={
                "display_name": "Moon rentals" if reason == "moon_rent" else "Ship replacement"
            },
        )
    for month in range(1, at.month + 1):
        date = min(datetime(at.year, month, 12, 14, tzinfo=timezone.utc), at - timedelta(minutes=1))
        for index, division in enumerate(divisions):
            JournalEntry.objects.update_or_create(
                division=division,
                entry_id=100000 + month * 100 + order * 10 + index,
                defaults={
                    "date": date,
                    "ref_type": ref_type,
                    "reason": reason,
                    "amount": amount * Decimal(10**9) * Decimal(100 + month * 2 + index * 5) / 100,
                    "first_party_id": division.corporation.corporation_id,
                    "second_party_id": 90000020,
                },
            )
client = Client()
client.force_login(user)
session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
output = Path(settings.BASE_DIR) / "output"
output.mkdir(exist_ok=True)
(output / "preview-session.txt").write_text(session_cookie)
print(f"Preview: http://127.0.0.1:8000/accountant/dashboard/{board.pk}/")
print("Local preview session saved in output/preview-session.txt (no password or ESI token).")
