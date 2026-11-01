from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured

from accountant.admin import ReasonRuleForm
from accountant.checks import check_retention
from accountant.conf import retention_cutoff
from accountant.models import Dashboard, ReasonRule, RefTypeRule, WalletDivision
from accountant.services.report import build_report
from accountant.templatetags.accountant import isk
from tests.conftest import AT

pytestmark = pytest.mark.django_db


def test_retention_calendar_boundaries(settings):
    assert retention_cutoff(AT) == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retention_cutoff(datetime(2026, 8, 1, tzinfo=timezone.utc)).month == 2
    assert retention_cutoff(datetime(2026, 1, 15, tzinfo=timezone.utc)) == datetime(
        2025, 7, 1, tzinfo=timezone.utc
    )
    settings.ACCOUNTANT_RETENTION_MONTHS = 12
    assert retention_cutoff(AT) == datetime(2025, 7, 1, tzinfo=timezone.utc)
    for invalid in (0, -1, "six", True):
        settings.ACCOUNTANT_RETENTION_MONTHS = invalid
        with pytest.raises(ImproperlyConfigured):
            retention_cutoff(AT)
        assert check_retention(None)[0].id == "accountant.E001"


def test_reason_admin_preserves_significant_spaces(board):
    rule = RefTypeRule.objects.create(
        dashboard=board, ref_type="player_donation", display_name="Donations"
    )
    form = ReasonRuleForm(
        data={
            "ref_rule": rule.pk,
            "reason": " moon_rent ",
            "display_name": "Moon rental",
            "order": 1,
        }
    )
    assert form.is_valid(), form.errors
    assert form.save().reason == " moon_rent "


def test_merge_signs_reasons_and_corporation_details(board, source, second_source, entry):
    third = WalletDivision.objects.create(corporation=source.corporation, division=2)
    board.divisions.add(second_source, third)
    rule = RefTypeRule.objects.create(
        dashboard=board,
        ref_type="player_donation",
        display_name="Contributions",
        split_reasons=True,
    )
    reason = ReasonRule.objects.create(
        ref_rule=rule, reason="moon_rent", display_name="Moon rentals"
    )
    entry(reason="moon_rent", amount="1234567890.12")
    entry(division=third, reason="moon_rent", amount="0.01")
    entry(division=second_source, reason="moon_rent", amount="1000000000.25")
    entry(reason="moon_rent", amount="-15.01")
    entry(reason="MOON_RENT", amount="2.10")
    entry(reason="", amount="3.20")
    entry(reason="moon_rent ", amount="4.30")
    entry(amount=0)
    entry(amount=None)
    report = build_report(board, 2026, AT)
    assert report["revenue"].total == Decimal("2234567899.98")
    assert report["expenses"].total == Decimal("-15.01")
    assert report["profit"].total == Decimal("2234567884.97")
    category = report["revenue"].children["player_donation"]
    moon = category.children[str(reason.pk)]
    assert moon.label == "Moon rentals"
    assert moon.children[str(source.corporation.corporation_id)].total == Decimal("1234567890.13")
    assert moon.children[str(second_source.corporation.corporation_id)].total == Decimal(
        "1000000000.25"
    )
    assert category.children["other"].total == Decimal("9.60")


def test_ref_type_modes_unknowns_and_sorting(board, entry):
    RefTypeRule.objects.create(
        dashboard=board, ref_type="bounty_prizes", display_name="Bounties", order=1
    )
    RefTypeRule.objects.create(
        dashboard=board, ref_type="market_escrow", display_name="Escrow", mode="ignore"
    )
    RefTypeRule.objects.create(
        dashboard=board, ref_type="player_donation", display_name="Donations", mode="other"
    )
    entry(ref_type="bounty_prizes", amount=10)
    entry(ref_type="market_escrow", amount=1000)
    entry(ref_type="market_escrow", amount=-1000)
    entry(amount=20)
    entry(ref_type="new_esi_type", amount=30)
    entry(ref_type="new_esi_type", amount=-5)
    report = build_report(board, 2026, AT)
    assert report["ignored"] == 2
    assert report["revenue"].total == 60
    assert report["expenses"].total == -5
    assert list(report["revenue"].children) == ["bounty_prizes", "other"]
    assert report["revenue"].children["other"].total == 50
    board.unconfigured_mode = "row"
    assert "new_esi_type" in build_report(board, 2026, AT)["revenue"].children
    board.unconfigured_mode = "ignore"
    assert build_report(board, 2026, AT)["revenue"].total == 30


def test_transfers_excluded_even_one_side_selected(board, source, second_source, entry):
    corp_id = source.corporation.corporation_id
    second_id = second_source.corporation.corporation_id
    entry(
        ref_type="corporation_account_withdrawal",
        first_party_id=corp_id,
        second_party_id=corp_id,
        amount="-30000000000",
    )
    report = build_report(board, 2026, AT)
    assert report["expenses"].total == 0
    assert report["excluded_transfers"] == 1
    board.divisions.add(second_source)
    entry(
        ref_type="corporation_account_withdrawal",
        first_party_id=corp_id,
        second_party_id=second_id,
        amount="-700",
    )
    entry(
        division=second_source,
        ref_type="corporation_account_withdrawal",
        first_party_id=corp_id,
        second_party_id=second_id,
        amount="700",
    )
    entry(
        ref_type="corporation_account_withdrawal",
        first_party_id=corp_id,
        second_party_id=90000001,
        amount="-20",
    )
    report = build_report(board, 2026, AT)
    assert report["excluded_transfers"] == 3
    assert report["revenue"].total == 0
    assert report["expenses"].total == -20
    board.exclude_between_selected_corporations = False
    report = build_report(board, 2026, AT)
    assert report["revenue"].total == 700
    assert report["expenses"].total == -720
    assert report["profit"].total == -20


def test_report_months_cutoff_utc_and_year_filter(board, entry):
    entry(date=datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc), amount=9000)
    entry(date=datetime(2026, 1, 1, tzinfo=timezone.utc), amount="1.11")
    entry(date=datetime(2026, 2, 1, tzinfo=timezone.utc), amount="2.22")
    entry(date=datetime(2026, 12, 1, tzinfo=timezone.utc), amount="9999")
    report = build_report(board, 2026, AT)
    assert report["revenue"].amounts[:2] == [Decimal("1.11"), Decimal("2.22")]
    assert report["revenue"].total == Decimal("3.33")
    assert [m["available"] for m in report["months"]] == [True] * 7 + [False] * 5
    assert report["months"][6]["current"]
    assert build_report(board, 2025, AT)["revenue"].total == 0


def test_dashboard_group_access(board, user, grant):
    assert not Dashboard.visible_to(user).exists()
    grant(user, "view_dashboard")
    assert Dashboard.visible_to(user).filter(pk=board.pk).exists()
    group = Group.objects.create(name="Finance")
    board.allowed_groups.add(group)
    assert not Dashboard.visible_to(user).exists()
    user.is_staff = True
    user.save()
    assert not Dashboard.visible_to(user).exists()
    user.groups.add(group)
    assert Dashboard.visible_to(user).filter(pk=board.pk).exists()


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("10000", "isk", "10 000.00"),
        ("10000.12", "isk", "10 000.12"),
        ("100000000", "million", "100.00 M. isk"),
        ("100000000", "billion", "0.10 B. isk"),
        ("8000000000", "billion", "8.00 B. isk"),
        ("8100000000", "billion", "8.10 B. isk"),
        ("-8000000000", "billion", "-8.00 B. isk"),
        ("0", "billion", "0.00 B. isk"),
        ("-1234567890.12", "billion", "-1.23 B. isk"),
        ("0", "isk", "0.00"),
        ("1", "billion", "<0.01 B. isk"),
        ("-1", "billion", "−<0.01 B. isk"),
    ],
)
def test_isk_display(value, unit, expected):
    assert isk(Decimal(value), unit) == expected
    assert isk(None) == "—"
