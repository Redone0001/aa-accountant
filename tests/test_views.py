import csv
import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from esi.models import CallbackRedirect, Scope

from accountant.models import RefTypeRule
from accountant.services.esi import SCOPES
from tests.conftest import AT

pytestmark = pytest.mark.django_db


def test_views_reject_anonymous_and_unauthorized(client, user, board, source):
    paths = [
        reverse("accountant:index"),
        reverse("accountant:dashboard", args=[board.pk]),
        reverse("accountant:export"),
        reverse("accountant:sources"),
        reverse("accountant:connect"),
        reverse("accountant:sync", args=[source.corporation.pk]),
    ]
    for path in paths:
        assert client.get(path).status_code == 302
    client.force_login(user)
    for path in paths:
        assert client.get(path).status_code == 403


def test_real_aa_templates_report_and_configuration(client, user, grant, board, entry):
    grant(user, "view_dashboard", "manage_sources", "export_journal")
    client.force_login(user)
    RefTypeRule.objects.create(
        dashboard=board, ref_type="player_donation", display_name="Contributions"
    )
    entry(amount="100000000.12", description="<script>alert('unsafe')</script>")
    with (
        patch("accountant.views.now", return_value=AT),
        patch("accountant.conf.now", return_value=AT),
    ):
        for name in ("index", "export", "sources"):
            response = client.get(reverse(f"accountant:{name}"))
            assert response.status_code == 200
        response = client.get(reverse("accountant:dashboard", args=[board.pk]))
        assert response.status_code == 200
        html = response.content.decode()
        assert "Contributions" in html
        assert "0.1 B. isk" in html
        assert "100 000 000.12 ISK" in html
        assert 'data-parent="revenue-player_donation"' in html
        assert "Northstar Industries" in html
        assert "<script>alert('unsafe')</script>" not in html
        assert response.context["report"]["revenue"].total == Decimal("100000000.12")
        full = client.get(
            reverse("accountant:dashboard", args=[board.pk]), {"unit": "isk", "year": 2026}
        )
        assert "100 000 000.12" in full.content.decode()
        invalid = client.get(
            reverse("accountant:dashboard", args=[board.pk]), {"year": "not-a-year"}
        )
        assert invalid.status_code == 200
        assert invalid.context["report"] is None
        assert invalid.context["form"].errors


def test_hidden_dashboard_and_export_division_cannot_be_accessed(
    client, user, grant, board, source
):
    grant(user, "view_dashboard", "export_journal")
    board.allowed_groups.add(Group.objects.create(name="Private finance"))
    client.force_login(user)
    assert client.get(reverse("accountant:dashboard", args=[board.pk])).status_code == 404
    result = client.get(reverse("accountant:export"), {"division": source.pk})
    assert result.status_code == 200
    assert result.context["form"].errors
    assert not result.streaming


def test_csv_exact_values_inclusive_dates_and_raw_transfers(
    client, user, grant, board, source, entry
):
    grant(user, "view_dashboard", "export_journal")
    client.force_login(user)
    entry(amount="1234567890.12", reason='=HYPERLINK("bad")', description="line 1\nline 2")
    entry(
        ref_type="corporation_account_withdrawal",
        first_party_id=source.corporation.corporation_id,
        second_party_id=source.corporation.corporation_id,
        amount="-30000000000.01",
    )
    entry(date=AT - timedelta(days=3))
    entry(date=AT - timedelta(days=300))
    with patch("accountant.conf.now", return_value=AT):
        response = client.get(
            reverse("accountant:export"),
            {
                "division": source.pk,
                "start": "2026-07-14",
                "end": "2026-07-14",
            },
        )
        assert response.streaming
        records = list(csv.DictReader(io.StringIO(b"".join(response.streaming_content).decode())))
    assert len(records) == 2
    assert records[0]["amount"] == "1234567890.12"
    assert records[0]["reason"].startswith("'=")
    assert records[0]["description"] == "line 1\nline 2"
    assert records[1]["amount"] == "-30000000000.01"
    assert records[1]["same_corporation_transfer"] == "True"
    assert response["Cache-Control"] == "no-store"
    with patch("accountant.conf.now", return_value=AT):
        response = client.get(reverse("accountant:export"), {"division": source.pk})
        records = list(csv.DictReader(io.StringIO(b"".join(response.streaming_content).decode())))
    assert len(records) == 3
    response = client.get(
        reverse("accountant:export"),
        {
            "division": source.pk,
            "start": "2026-07-15",
            "end": "2026-07-14",
        },
    )
    assert response.context["form"].errors


def test_sync_requires_post_and_csrf(client, user, grant, source, offline):
    grant(user, "manage_sources")
    client.force_login(user)
    path = reverse("accountant:sync", args=[source.corporation.pk])
    assert client.get(path).status_code == 405
    assert client.post(path).status_code == 302
    offline.assert_called_once_with(source.corporation.pk)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)
    assert csrf_client.post(path).status_code == 403


def test_sso_callback_confirmation_and_token_selection(client, user, grant, token, source, offline):
    grant(user, "view_dashboard", "manage_sources")
    for name in SCOPES:
        token.scopes.add(Scope.objects.get_or_create(name=name)[0])
    client.force_login(user)
    CallbackRedirect.objects.create(session_key=client.session.session_key, token=token)
    path = reverse("accountant:connect")
    response = client.get(path)
    assert response.status_code == 200
    assert f'name="_token" value="{token.pk}"' in response.content.decode()
    assert not source.corporation.token_id
    with (
        patch(
            "esi.managers.TokenQueryset.require_valid", autospec=True, side_effect=lambda self: self
        ),
        patch(
            "accountant.views.authorize_corporation", return_value=source.corporation
        ) as authorize,
    ):
        response = client.post(path, {"_token": token.pk})
    assert response.status_code == 302
    authorize.assert_called_once()
    offline.assert_called_once_with(source.corporation.pk)
