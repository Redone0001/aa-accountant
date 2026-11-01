from pathlib import Path

import pytest
from django import forms
from django.urls import reverse

from accountant.forms import RefTypeRuleForm
from accountant.models import RefTypeRule
from accountant.ref_types import REF_TYPE_NAMES
from accountant.services.report import build_report
from tests.conftest import AT

pytestmark = pytest.mark.django_db


def test_catalog_matches_the_user_supplied_allowlist():
    supplied = (Path(__file__).parent / "fixtures" / "ref_types.txt").read_text().splitlines()
    assert len(supplied) == len(set(supplied))
    assert set(REF_TYPE_NAMES) == set(supplied)
    for value, display_name in REF_TYPE_NAMES.items():
        assert display_name.strip() == display_name
        assert display_name and "_" not in display_name
        assert len(display_name) <= RefTypeRule._meta.get_field("display_name").max_length
    assert REF_TYPE_NAMES["ess_escrow_transfer"] == "ESS escrow transfer"
    assert REF_TYPE_NAMES["cspaofflinerefund"] == "CSPA offline refund"
    assert REF_TYPE_NAMES["sovereignity_bill"] == "Sovereignty bill"


def rule_data(board, **overrides):
    data = {
        "dashboard": board.pk,
        "ref_type": "player_donation",
        "display_name": "",
        "mode": "row",
        "order": 100,
    }
    data.update(overrides)
    return data


def test_selection_defaults_name_without_javascript_and_allows_custom_labels(board):
    form = RefTypeRuleForm(data=rule_data(board))
    assert isinstance(form.fields["ref_type"].widget, forms.Select)
    assert form.is_valid(), form.errors
    rule = form.save()
    assert rule.ref_type == "player_donation"
    assert rule.display_name == "Player donation"
    form = RefTypeRuleForm(instance=rule, data=rule_data(board, display_name="Moon income"))
    assert form.is_valid(), form.errors
    assert form.save().display_name == "Moon income"
    form = RefTypeRuleForm(instance=rule, data=rule_data(board, ref_type="ess_escrow_transfer"))
    assert form.is_valid(), form.errors
    assert form.save().display_name == "ESS escrow transfer"


def test_unknown_new_rules_rejected_but_legacy_rule_can_be_edited(board):
    unknown = "custom_preexisting_type"
    form = RefTypeRuleForm(data=rule_data(board, ref_type=unknown))
    assert not form.is_valid()
    assert "ref_type" in form.errors
    rule = RefTypeRule.objects.create(
        dashboard=board, ref_type=unknown, display_name="My existing category"
    )
    form = RefTypeRuleForm(
        instance=rule, data=rule_data(board, ref_type=unknown, display_name=rule.display_name)
    )
    assert form.is_valid(), form.errors
    assert form.save().display_name == "My existing category"
    changed = RefTypeRuleForm(instance=rule, data=rule_data(board, ref_type="another_custom_type"))
    assert not changed.is_valid()


def test_duplicate_rule_still_rejected(board):
    RefTypeRule.objects.create(
        dashboard=board, ref_type="player_donation", display_name="Existing donations"
    )
    form = RefTypeRuleForm(data=rule_data(board))
    assert not form.is_valid()
    assert "already exists" in str(form.errors)


def test_catalog_labels_used_for_unconfigured_separate_rows(board, entry):
    board.unconfigured_mode = "row"
    entry(ref_type="cspaofflinerefund")
    entry(ref_type="future_esi_type")
    report = build_report(board, 2026, AT)
    assert report["revenue"].children["cspaofflinerefund"].label == "CSPA offline refund"
    assert report["revenue"].children["future_esi_type"].total == 100


def test_real_admin_editors_render_dropdown_and_can_save_default_name(client, user, board):
    user.is_staff = user.is_superuser = True
    user.save()
    client.force_login(user)
    response = client.get(reverse("admin:accountant_reftyperule_add"))
    assert response.status_code == 200
    html = response.content.decode()
    assert '<select name="ref_type"' in html
    assert 'data-display-name="ESS escrow transfer"' in html
    assert "ESS escrow transfer (ess_escrow_transfer)" in html
    assert "accountant/admin-ref-types.js" in html
    response = client.post(
        reverse("admin:accountant_reftyperule_add"),
        {
            **rule_data(board),
            "reason_rules-TOTAL_FORMS": 0,
            "reason_rules-INITIAL_FORMS": 0,
        },
    )
    assert response.status_code == 302, response.context["adminform"].errors
    assert board.ref_rules.get().display_name == "Player donation"
    response = client.get(reverse("admin:accountant_dashboard_change", args=[board.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert '<select name="ref_rules-0-ref_type"' in html
    assert 'name="ref_rules-__prefix__-ref_type"' in html
    assert "accountant/admin-ref-types.js" in html
