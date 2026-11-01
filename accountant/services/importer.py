from datetime import timezone
from decimal import Decimal

from django.db import connection, transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now

from accountant.conf import retention_cutoff
from accountant.models import Corporation, JournalEntry, WalletDivision
from accountant.services.esi import EsiClient, EsiError

MONEY_FIELDS = ("amount", "balance", "tax")
OPTIONAL_FIELDS = ("first_party_id", "second_party_id", "context_id", "tax_receiver_id")
TEXT_FIELDS = ("reason", "description", "context_id_type")
UPDATE_FIELDS = ["date", "ref_type", *MONEY_FIELDS, *OPTIONAL_FIELDS, *TEXT_FIELDS]


def save_page(division, items, cutoff=None):
    cutoff = cutoff or retention_cutoff()
    rows = {}
    for item in items:
        date = item["date"]
        if isinstance(date, str):
            date = parse_datetime(date)
        if date is None or date.tzinfo is None:
            raise ValueError("Journal dates must include a timezone.")
        if date < cutoff:
            continue
        data = {name: item.get(name) for name in OPTIONAL_FIELDS}
        data.update({name: item.get(name) or "" for name in TEXT_FIELDS})
        data.update(
            {
                name: Decimal(str(item[name])) if item.get(name) is not None else None
                for name in MONEY_FIELDS
            }
        )
        # Duplicate IDs in the same ESI page must not cause a conflict within a bulk upsert.
        rows[item["id"]] = JournalEntry(
            division=division,
            entry_id=item["id"],
            date=date.astimezone(timezone.utc),
            ref_type=item["ref_type"],
            **data,
        )
    kwargs = {}
    if connection.features.supports_update_conflicts_with_target:
        kwargs["unique_fields"] = ["division", "entry_id"]
    JournalEntry.objects.bulk_create(
        rows.values(), update_conflicts=True, update_fields=UPDATE_FIELDS, batch_size=500, **kwargs
    )
    return len(rows)


@transaction.atomic
def authorize_corporation(token):
    with EsiClient(token) as esi:
        corporation_id, name, wallets = esi.identity()
    corporation, _ = Corporation.objects.update_or_create(
        corporation_id=corporation_id, defaults={"name": name, "token": token, "enabled": True}
    )
    for wallet in wallets:
        number = wallet["division"]
        if number not in range(1, 8):
            raise ValueError("ESI returned an invalid division.")
        WalletDivision.objects.get_or_create(
            corporation=corporation,
            division=number,
            defaults={"name": "Master wallet" if number == 1 else f"Wallet {number}"},
        )
    return corporation


def sync_corporation(corporation_id):
    corporation = Corporation.objects.get(pk=corporation_id)
    if not corporation.enabled:
        return 0
    divisions = corporation.divisions.filter(enabled=True)
    divisions.update(last_attempt=now())
    if corporation.token is None:
        divisions.update(last_error="No token. Reauthorize this corporation.")
        raise EsiError("No token. Reauthorize this corporation.")
    try:
        with EsiClient(corporation.token) as esi:
            current_corp, name, _ = esi.identity()
            if current_corp != corporation.corporation_id:
                raise EsiError("Token character has left this corporation. Reauthorize it.")
            Corporation.objects.filter(pk=corporation.pk).update(name=name)
            touched = 0
            for division in divisions:
                # A failed later page rolls back the entire division, preserving its last success.
                with transaction.atomic():
                    cutoff = retention_cutoff()
                    for page in esi.journal_pages(corporation.corporation_id, division.division):
                        touched += save_page(division, page, cutoff)
                    WalletDivision.objects.filter(pk=division.pk).update(
                        last_success=now(), last_error=""
                    )
            return touched
    except Exception as error:
        # Do not store exception strings from HTTP/SSO libraries: they can contain credentials.
        message = (
            str(error)
            if isinstance(error, EsiError)
            else ("Synchronization failed. Check worker logs and reauthorize the token if needed.")
        )
        divisions.update(last_error=message[:255])
        raise


def prune_history():
    return JournalEntry.objects.filter(date__lt=retention_cutoff()).delete()[0]
