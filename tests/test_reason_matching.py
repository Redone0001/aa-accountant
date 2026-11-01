from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from accountant.admin import ReasonRuleForm
from accountant.models import Dashboard, JournalEntry, ReasonRule, RefTypeRule
from accountant.services.report import build_report
from tests.conftest import AT

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "mode,pattern,text,expected",
    [
        ("exact", "Moon rent", "Moon rent", True),
        ("exact", "Moon rent", "moon rent", False),
        ("exact", "Moon rent", "Moon rent October", False),
        ("exact", "Moon rent", "Moon rent ", False),
        ("iexact", "Moon rent", "MOON RENT", True),
        ("iexact", "Moon rent", "Moon Rent", True),
        ("iexact", "Straße", "STRASSE", True),
        ("iexact", "Moon rent", "Moon rent ", False),
        ("contains", "rent", "Moon rent October", True),
        ("contains", "rent", "Moon RENT October", False),
        ("contains", "rent", "Moon rental", True),
        ("icontains", "goo", "Alliance Goo October", True),
        ("icontains", "GOO", "alliance goo", True),
        ("icontains", "Straße", "Payment for STRASSE", True),
        ("icontains", "rent.*", "rent October", False),
        ("icontains", "rent.*", "payment RENT.*", True),
        ("icontains", "rent", "", False),
        ("icontains", "rent", None, False),
        ("icontains", "", "anything", False),
    ],
)
def test_reason_match_modes(mode, pattern, text, expected):
    assert ReasonRule(reason=pattern, match_type=mode).matches(text) is expected


def split_rule(board, **overrides):
    values = dict(
        dashboard=board,
        ref_type="player_donation",
        display_name="Contributions",
        split_reasons=True,
    )
    values.update(overrides)
    return RefTypeRule.objects.create(**values)


def test_exact_default_and_contains_overlap_count_each_entry_once(board, entry):
    ref = split_rule(board)
    exact = ReasonRule.objects.create(
        ref_rule=ref, reason="rent", display_name="Exact rent", order=10
    )
    general = ReasonRule.objects.create(
        ref_rule=ref, reason="rent", match_type="icontains", display_name="Rent keyword", order=20
    )
    assert exact.match_type == "exact"
    entry(reason="rent", amount="100.12")
    entry(reason="Rent October", amount="200.34")
    entry(reason="Other payment", amount="50.56")
    entry(reason="RENT refund", amount="-30.78")
    report = build_report(board, 2026, AT)
    children = report["revenue"].children[ref.ref_type].children
    assert children[str(exact.pk)].total == Decimal("100.12")
    assert children[str(general.pk)].total == Decimal("200.34")
    assert children["other"].total == Decimal("50.56")
    assert report["expenses"].children[ref.ref_type].children[str(general.pk)].total == Decimal(
        "-30.78"
    )
    assert report["revenue"].total == sum((r.total for r in children.values()), Decimal(0))
    assert report["profit"].total == Decimal("320.24")
    assert set(JournalEntry.objects.values_list("reason", flat=True)) == {
        "rent",
        "Rent October",
        "Other payment",
        "RENT refund",
    }


def test_first_match_uses_order_then_id_and_renaming_does_not_change_it(board, entry):
    ref = split_rule(board)
    older = ReasonRule.objects.create(
        ref_rule=ref, reason="moon", match_type="icontains", display_name="Z older"
    )
    newer = ReasonRule.objects.create(
        ref_rule=ref, reason="rent", match_type="icontains", display_name="A newer"
    )
    entry(reason="Moon rent")
    children = build_report(board, 2026, AT)["revenue"].children[ref.ref_type].children
    assert list(children) == [str(older.pk)]
    older.display_name = "Still older"
    older.save()
    assert str(older.pk) in build_report(board, 2026, AT)["revenue"].children[ref.ref_type].children
    older.order = 200
    older.save()
    children = build_report(board, 2026, AT)["revenue"].children[ref.ref_type].children
    assert list(children) == [str(newer.pk)]


def test_matching_is_scoped_and_preserves_monthly_corporation_totals(
    board, source, second_source, entry
):
    board.divisions.add(second_source)
    ref = split_rule(board)
    reason = ReasonRule.objects.create(
        ref_rule=ref, reason="moon", match_type="icontains", display_name="Moon rentals"
    )
    separate = split_rule(board, ref_type="corporation_account_withdrawal")
    entry(reason="MOON RENT", amount="100.12", date=datetime(2026, 6, 1, tzinfo=timezone.utc))
    entry(division=second_source, reason="Moon rent", amount="50.34")
    entry(ref_type=separate.ref_type, reason="Moon rent", amount="7.89")
    report = build_report(board, 2026, AT)
    child = report["revenue"].children[ref.ref_type].children[str(reason.pk)]
    assert child.amounts[5:7] == [Decimal("100.12"), Decimal("50.34")]
    assert child.children[str(source.corporation.corporation_id)].total == Decimal("100.12")
    assert child.children[str(second_source.corporation.corporation_id)].total == Decimal("50.34")
    assert list(report["revenue"].children[separate.ref_type].children) == ["other"]
    other = Dashboard.objects.create(name="Different reason rules")
    other.divisions.set(board.divisions.all())
    other_ref = split_rule(other)
    assert list(build_report(other, 2026, AT)["revenue"].children[other_ref.ref_type].children) == [
        "other"
    ]


def test_reason_form_rejects_empty_keywords_and_invalid_match_modes(board):
    ref = split_rule(board)
    data = {
        "ref_rule": ref.pk,
        "reason": "",
        "match_type": "icontains",
        "display_name": "Blank keyword",
        "order": 1,
    }
    form = ReasonRuleForm(data=data)
    assert not form.is_valid()
    assert "reason" in form.errors
    form = ReasonRuleForm(data={**data, "reason": "moon", "match_type": "regex"})
    assert not form.is_valid()
    assert "match_type" in form.errors


def test_shared_display_name_merges_keywords_months_corporations_and_overlap(
    board, source, second_source, entry
):
    board.divisions.add(second_source)
    ref = split_rule(board)
    first = ReasonRule.objects.create(
        ref_rule=ref, reason="ABC", match_type="icontains", display_name="abc, ABC, ZXY"
    )
    ReasonRule.objects.create(
        ref_rule=ref, reason="ZXY", match_type="icontains", display_name=first.display_name
    )
    entry(reason="abc payment", amount="100.12", date=datetime(2026, 6, 1, tzinfo=timezone.utc))
    entry(reason="ABC and ZXY", amount="20.34")
    entry(division=second_source, reason="ZXY payment", amount="50.56")
    entry(reason="abc refund", amount="-10.78")
    entry(division=second_source, reason="ZXY refund", amount="-30.90")
    entry(reason="Unmatched", amount="7.89")
    report = build_report(board, 2026, AT)
    children = report["revenue"].children[ref.ref_type].children
    assert list(children) == [str(first.pk), "other"]
    merged = children[str(first.pk)]
    assert merged.label == "abc, ABC, ZXY"
    assert merged.amounts[5:7] == [Decimal("100.12"), Decimal("70.90")]
    assert merged.total == Decimal("171.02")
    assert merged.children[str(source.corporation.corporation_id)].total == Decimal("120.46")
    assert merged.children[str(second_source.corporation.corporation_id)].total == Decimal("50.56")
    expenses = report["expenses"].children[ref.ref_type].children
    assert list(expenses) == [str(first.pk)]
    assert expenses[str(first.pk)].total == Decimal("-41.68")
    assert report["revenue"].total == Decimal("178.91")
    assert report["profit"].total == Decimal("137.23")
    assert JournalEntry.objects.count() == 6


def test_group_order_uses_first_configured_rule_even_without_matches(board, entry):
    ref = split_rule(board)
    first = ReasonRule.objects.create(ref_rule=ref, reason="ABC", display_name="Shared", order=5)
    middle = ReasonRule.objects.create(
        ref_rule=ref, reason="Other", display_name="Middle", order=10
    )
    ReasonRule.objects.create(
        ref_rule=ref, reason="ZXY", match_type="contains", display_name="Shared", order=20
    )
    entry(reason="Other")
    entry(reason="ZXY payment")
    children = build_report(board, 2026, AT)["revenue"].children[ref.ref_type].children
    assert list(children) == [str(first.pk), str(middle.pk)]
    assert len({row.key for row in children.values()}) == 2


def test_group_names_are_exact_scoped_and_distinct_from_automatic_other(board, entry):
    ref = split_rule(board)
    rules = [
        ReasonRule.objects.create(ref_rule=ref, reason=text, display_name=name)
        for text, name in [("ABC", "Shared"), ("ZXY", "shared"), ("DEF", "Other reasons")]
    ]
    separate = split_rule(board, ref_type="corporation_account_withdrawal")
    separate_reason = ReasonRule.objects.create(
        ref_rule=separate, reason="ABC", display_name="Shared"
    )
    for text in ("ABC", "ZXY", "DEF", "Unmatched"):
        entry(reason=text)
    entry(ref_type=separate.ref_type, reason="ABC", amount="50")
    report = build_report(board, 2026, AT)
    children = report["revenue"].children[ref.ref_type].children
    assert list(children) == [*(str(rule.pk) for rule in rules), "other"]
    assert all(row.total == 100 for row in children.values())
    assert len({row.key for row in children.values()}) == 4
    assert (
        report["revenue"].children[separate.ref_type].children[str(separate_reason.pk)].total == 50
    )
    rules[1].display_name = "Shared"
    rules[1].save()
    merged = build_report(board, 2026, AT)["revenue"].children[ref.ref_type].children
    assert list(merged) == [str(rules[0].pk), str(rules[2].pk), "other"]
    assert merged[str(rules[0].pk)].total == 200


def test_admin_can_save_contains_case_insensitive_rule(client, user, board, entry):
    user.is_staff = user.is_superuser = True
    user.save()
    client.force_login(user)
    ref = split_rule(board)
    entry(reason="Alliance Goo October")
    url = reverse("admin:accountant_reftyperule_change", args=[ref.pk])
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'name="reason_rules-__prefix__-match_type"' in html
    assert "Contains (case-insensitive)" in html
    assert "Rules with the same display name merge into one row" in html
    response = client.post(
        url,
        {
            "dashboard": board.pk,
            "ref_type": ref.ref_type,
            "display_name": ref.display_name,
            "mode": "row",
            "split_reasons": "on",
            "order": 100,
            "reason_rules-TOTAL_FORMS": 1,
            "reason_rules-INITIAL_FORMS": 0,
            "reason_rules-0-ref_rule": ref.pk,
            "reason_rules-0-reason": "goo",
            "reason_rules-0-match_type": "icontains",
            "reason_rules-0-display_name": "Goo income",
            "reason_rules-0-order": 5,
        },
    )
    assert response.status_code == 302
    reason = ref.reason_rules.get()
    assert reason.match_type == "icontains"
    assert (
        build_report(board, 2026, AT)["revenue"]
        .children[ref.ref_type]
        .children[str(reason.pk)]
        .total
        == 100
    )
