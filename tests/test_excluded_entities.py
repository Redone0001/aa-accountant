import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from accountant.models import Dashboard, ExcludedEntity, JournalEntry, ReasonRule, RefTypeRule
from accountant.services.report import build_report
from tests.conftest import AT

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "entity_type,storage_id", [("character", 90000123), ("corporation", 98000123)]
)
def test_storage_entities_exclude_both_parties_all_types_and_months(
    board, source, entry, entity_type, storage_id
):
    ExcludedEntity.objects.create(
        dashboard=board, entity_id=storage_id, entity_type=entity_type, display_name="Storage"
    )
    rule = RefTypeRule.objects.create(
        dashboard=board, ref_type="player_donation", display_name="Donations", split_reasons=True
    )
    reason = ReasonRule.objects.create(
        ref_rule=rule, reason="storage", display_name="Storage funds"
    )
    entry(
        date=datetime(2026, 6, 15, tzinfo=timezone.utc),
        amount="-30000000000",
        ref_type="corporation_account_withdrawal",
        first_party_id=source.corporation.corporation_id,
        second_party_id=storage_id,
    )
    entry(amount="20000000000", first_party_id=storage_id, reason="storage")
    entry(amount="2.50", first_party_id=storage_id, second_party_id=storage_id)
    entry(amount="-19.99", ref_type="future_esi_type", second_party_id=storage_id)
    entry(amount="125.25", first_party_id=90000999)
    entry(amount="-5.25", second_party_id=90000999)
    report = build_report(board, 2026, AT)
    assert report["revenue"].total == Decimal("125.25")
    assert report["expenses"].total == Decimal("-5.25")
    assert report["profit"].total == Decimal("120.00")
    assert report["revenue"].amounts[5] == report["expenses"].amounts[5] == 0
    assert report["excluded_entity_entries"] == 4
    assert JournalEntry.objects.count() == 6
    for section in (report["revenue"], report["expenses"]):
        assert str(reason.pk) not in section.children["player_donation"].children
        assert sum((row.total for row in section.children.values()), Decimal(0)) == section.total


def test_exclusions_apply_across_selected_corporations_but_are_scoped_and_reversible(
    board, second_source, entry
):
    board.divisions.add(second_source)
    entry(amount=100, first_party_id=90000123)
    entry(division=second_source, amount=-40, second_party_id=90000123)
    other = Dashboard.objects.create(name="Include storage")
    other.divisions.set(board.divisions.all())
    exclusion = ExcludedEntity.objects.create(dashboard=board, entity_id=90000123)
    assert build_report(board, 2026, AT)["profit"].total == 0
    assert build_report(board, 2026, AT)["excluded_entity_entries"] == 2
    assert build_report(other, 2026, AT)["profit"].total == 60
    exclusion.delete()
    assert build_report(board, 2026, AT)["profit"].total == 60
    assert JournalEntry.objects.count() == 2


def test_entity_exclusions_count_once_before_internal_and_ignored_rules(board, source, entry):
    corp_id = source.corporation.corporation_id
    ExcludedEntity.objects.create(dashboard=board, entity_id=corp_id, entity_type="corporation")
    RefTypeRule.objects.create(
        dashboard=board, ref_type="player_donation", display_name="Ignored", mode="ignore"
    )
    entry(
        ref_type="corporation_account_withdrawal", first_party_id=corp_id, second_party_id=corp_id
    )
    entry(first_party_id=corp_id)
    entry(amount=9, first_party_id=None, second_party_id=None, ref_type="market_transaction")
    report = build_report(board, 2026, AT)
    assert report["excluded_entity_entries"] == 2
    assert report["excluded_transfers"] == 0
    assert report["ignored"] == 0
    assert report["revenue"].total == 9


def test_excluded_ids_must_be_positive_and_unique_within_dashboard(board):
    for invalid in (0, -1):
        with pytest.raises(ValidationError):
            ExcludedEntity(dashboard=board, entity_id=invalid).full_clean()
    ExcludedEntity.objects.create(dashboard=board, entity_id=90000123)
    with transaction.atomic(), pytest.raises(IntegrityError):
        ExcludedEntity.objects.create(
            dashboard=board, entity_id=90000123, entity_type="corporation"
        )
    other = Dashboard.objects.create(name="Another board")
    ExcludedEntity.objects.create(dashboard=other, entity_id=90000123)


def test_admin_can_configure_exclusions_and_dashboard_shows_inline(client, user, board):
    user.is_staff = user.is_superuser = True
    user.save()
    client.force_login(user)
    response = client.post(
        reverse("admin:accountant_excludedentity_add"),
        {
            "dashboard": board.pk,
            "entity_id": "90000123",
            "entity_type": "character",
            "display_name": "Treasury storage",
        },
    )
    assert response.status_code == 302
    exclusion = board.excluded_entities.get()
    assert exclusion.entity_id == 90000123
    assert str(exclusion) == "Treasury storage (Character #90000123)"
    response = client.get(reverse("admin:accountant_dashboard_change", args=[board.pk]))
    assert response.status_code == 200
    assert 'name="excluded_entities-0-entity_id"' in response.content.decode()
    assert 'name="excluded_entities-__prefix__-entity_id"' in response.content.decode()


def test_excluded_entries_are_visible_in_raw_csv_but_not_dashboard(
    client, user, grant, board, source, entry
):
    ExcludedEntity.objects.create(
        dashboard=board, entity_id=90000123, display_name="Treasury storage"
    )
    entry(amount="123.45", first_party_id=90000123)
    grant(user, "view_dashboard", "export_journal")
    client.force_login(user)
    with (
        patch("accountant.views.now", return_value=AT),
        patch("accountant.services.report.now", return_value=AT),
        patch("accountant.conf.now", return_value=AT),
    ):
        response = client.get(reverse("accountant:dashboard", args=[board.pk]))
        assert response.status_code == 200
        assert response.context["report"]["profit"].total == 0
        assert "1 entries involving excluded entities" in response.content.decode()
        assert "Treasury storage" in response.content.decode()
        response = client.get(reverse("accountant:export"), {"division": source.pk})
        rows = list(csv.DictReader(io.StringIO(b"".join(response.streaming_content).decode())))
    assert len(rows) == 1
    assert rows[0]["first_party_id"] == "90000123"
    assert rows[0]["amount"] == "123.45"
