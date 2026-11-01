from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from accountant.models import Corporation, JournalEntry
from accountant.services.esi import EsiClient, EsiError, RetryableEsiError
from accountant.services.importer import (
    authorize_corporation,
    prune_history,
    save_page,
    sync_corporation,
)

pytestmark = pytest.mark.django_db


def payload(**overrides):
    item = {
        "id": 123456789012345,
        "date": "2026-07-14T23:59:00Z",
        "amount": Decimal("123456789012.34"),
        "ref_type": "player_donation",
        "reason": "moon_rent",
    }
    item.update(overrides)
    return item


def test_import_idempotency_exact_amounts_and_division_identity(source, second_source):
    item = payload()
    save_page(source, [item, item], retention_cutoff_at())
    save_page(source, [item], retention_cutoff_at())
    assert JournalEntry.objects.count() == 1
    assert JournalEntry.objects.get().amount == Decimal("123456789012.34")
    save_page(second_source, [item], retention_cutoff_at())
    assert JournalEntry.objects.count() == 2
    save_page(source, [payload(reason="corrected", amount=Decimal("0.01"))], retention_cutoff_at())
    assert JournalEntry.objects.get(division=source).reason == "corrected"
    assert JournalEntry.objects.get(division=source).amount == Decimal("0.01")


def retention_cutoff_at():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_import_cutoff_and_retention_cleanup(source, entry):
    save_page(source, [payload(date="2025-12-31T23:59:59Z")], retention_cutoff_at())
    assert not JournalEntry.objects.exists()
    entry(date=datetime(2025, 12, 31, tzinfo=timezone.utc))
    entry(date=retention_cutoff_at())
    with patch("accountant.services.importer.retention_cutoff", return_value=retention_cutoff_at()):
        assert prune_history() == 1
    assert JournalEntry.objects.get().date == retention_cutoff_at()


def test_decimal_decoding_pagination_and_token_refresh(token):
    first = MagicMock(
        status_code=200, text='[{"amount": 123456789012345.67, "id": 1}]', headers={"X-Pages": "2"}
    )
    second = MagicMock(
        status_code=200, text='[{"amount": -0.01, "id": 2}]', headers={"X-Pages": "2"}
    )
    with (
        EsiClient(token) as esi,
        patch.object(esi.session, "get", side_effect=[first, second]) as get,
        patch.object(token, "valid_access_token", return_value="test-access") as refresh,
    ):
        pages = list(esi.journal_pages(98000001, 1))
        assert pages[0][0]["amount"] == Decimal("123456789012345.67")
        assert pages[1][0]["amount"] == Decimal("-0.01")
        assert get.call_args_list[1].kwargs["params"] == {"page": 2}
        assert refresh.call_count == 2
        assert get.call_args.kwargs["timeout"] == 30


@pytest.mark.parametrize(
    "status,error",
    [(403, EsiError), (420, RetryableEsiError), (429, RetryableEsiError), (503, RetryableEsiError)],
)
def test_esi_errors_are_safe(token, status, error):
    response = MagicMock(status_code=status, text="SECRET-RESPONSE", headers={})
    with EsiClient(token) as esi, patch.object(esi.session, "get", return_value=response):
        with pytest.raises(error) as raised:
            esi.get("/test")
        assert "SECRET" not in str(raised.value)


def test_network_and_json_errors_retry(token):
    with (
        EsiClient(token) as esi,
        patch.object(esi.session, "get", side_effect=requests.Timeout("secret")),
    ):
        with pytest.raises(RetryableEsiError, match="connection failed"):
            esi.get("/test")
    with (
        EsiClient(token) as esi,
        patch.object(esi.session, "get", return_value=MagicMock(status_code=200, text="invalid")),
    ):
        with pytest.raises(RetryableEsiError, match="invalid response"):
            esi.get("/test")


def test_identity_checks_corp_role_and_wallet_access(token):
    with (
        EsiClient(token) as esi,
        patch.object(
            esi,
            "get",
            side_effect=[
                ({"corporation_id": 98}, {}),
                ({"roles": ["Accountant"]}, {}),
                ({"name": "Our corporation"}, {}),
                ([{"division": 1}], {}),
            ],
        ) as get,
    ):
        assert esi.identity() == (98, "Our corporation", [{"division": 1}])
        assert get.call_args.args[0] == "/corporations/98/wallets"
    with (
        EsiClient(token) as esi,
        patch.object(
            esi,
            "get",
            side_effect=[
                ({"corporation_id": 98}, {}),
                ({"roles": []}, {}),
            ],
        ),
    ):
        with pytest.raises(EsiError, match="needs Accountant"):
            esi.identity()


def test_authorize_repeat_and_sync_failure_rollback(source, token):
    with patch("accountant.services.importer.EsiClient") as factory:
        esi = factory.return_value.__enter__.return_value
        esi.identity.return_value = (
            source.corporation.corporation_id,
            "Updated corporation",
            [{"division": i} for i in range(1, 8)],
        )
        corporation = authorize_corporation(token)
        authorize_corporation(token)
        assert Corporation.objects.count() == 1
        assert corporation.divisions.count() == 7
        corporation.divisions.exclude(pk=source.pk).update(enabled=False)

        def partial_failure(*args):
            yield [payload()]
            raise RetryableEsiError("ESI temporarily unavailable.")

        esi.journal_pages.side_effect = partial_failure
        with pytest.raises(RetryableEsiError):
            sync_corporation(corporation.pk)
        assert not JournalEntry.objects.exists()
        source.refresh_from_db()
        assert source.last_success is None
        assert "temporarily" in source.last_error
        assert source.last_attempt is not None
        esi.journal_pages.side_effect = None
        esi.journal_pages.return_value = [[payload()]]
        with patch(
            "accountant.services.importer.retention_cutoff", return_value=retention_cutoff_at()
        ):
            sync_corporation(corporation.pk)
            sync_corporation(corporation.pk)
        assert JournalEntry.objects.count() == 1
        source.refresh_from_db()
        assert source.last_success is not None
        assert not source.last_error


def test_changed_membership_missing_token_and_disabled_sources(source, token):
    corporation = source.corporation
    with pytest.raises(EsiError, match="No token"):
        sync_corporation(corporation.pk)
    corporation.token = token
    corporation.save()
    with patch("accountant.services.importer.EsiClient") as factory:
        factory.return_value.__enter__.return_value.identity.return_value = (
            99,
            "Different corporation",
            [],
        )
        with pytest.raises(EsiError, match="has left"):
            sync_corporation(corporation.pk)
    corporation.enabled = False
    corporation.save()
    assert sync_corporation(corporation.pk) == 0


def test_raw_exception_not_persisted(source, token):
    source.corporation.token = token
    source.corporation.save()
    with patch("accountant.services.importer.EsiClient", side_effect=RuntimeError("SECRET-TOKEN")):
        with pytest.raises(RuntimeError):
            sync_corporation(source.corporation.pk)
    source.refresh_from_db()
    assert "SECRET" not in source.last_error
