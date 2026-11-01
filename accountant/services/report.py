import calendar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from django.utils.timezone import now

from accountant.conf import retention_cutoff
from accountant.models import DisplayMode, JournalEntry
from accountant.ref_types import ref_type_display_name

ZERO = Decimal("0")


def is_internal_transfer(entry, corporation_id, selected_corps=(), exclude_between=True):
    if entry["ref_type"] != "corporation_account_withdrawal":
        return False
    first, second = entry["first_party_id"], entry["second_party_id"]
    return (first == second == corporation_id) or (
        exclude_between and first in selected_corps and second in selected_corps
    )


@dataclass
class Row:
    key: str
    label: str
    amounts: list = field(default_factory=lambda: [ZERO] * 12)
    children: dict = field(default_factory=dict)

    @property
    def total(self):
        with localcontext() as ctx:
            ctx.prec = 50
            return sum(self.amounts, ZERO)

    def add(self, month, amount):
        self.amounts[month - 1] += amount


def build_report(dashboard, year, at=None):
    at = at or now()
    cutoff = retention_cutoff(at)
    divisions = list(dashboard.divisions.select_related("corporation").all())
    corps = {d.corporation.corporation_id: d.corporation.name for d in divisions}
    division_corps = {d.pk: d.corporation.corporation_id for d in divisions}
    rules = {r.ref_type: r for r in dashboard.ref_rules.prefetch_related("reason_rules")}
    reasons = {key: {r.reason: r for r in rule.reason_rules.all()} for key, rule in rules.items()}
    excluded_entity_rules = list(dashboard.excluded_entities.all())
    excluded_entity_ids = {rule.entity_id for rule in excluded_entity_rules}
    revenue, expenses = Row("revenue", "Revenue total"), Row("expenses", "Expenses total")
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    entries = JournalEntry.objects.filter(
        division_id__in=division_corps,
        date__gte=max(start, cutoff),
        date__lt=min(end, at),
    ).values(
        "division_id", "date", "ref_type", "reason", "amount", "first_party_id", "second_party_id"
    )
    excluded_transfers = excluded_entity_entries = ignored = 0
    with localcontext() as ctx:
        ctx.prec = 50
        for entry in entries.iterator(chunk_size=2000):
            if (
                entry["first_party_id"] in excluded_entity_ids
                or entry["second_party_id"] in excluded_entity_ids
            ):
                excluded_entity_entries += 1
                continue
            corp_id = division_corps[entry["division_id"]]
            if is_internal_transfer(
                entry, corp_id, corps, dashboard.exclude_between_selected_corporations
            ):
                excluded_transfers += 1
                continue
            rule = rules.get(entry["ref_type"])
            mode = rule.mode if rule else dashboard.unconfigured_mode
            if mode == DisplayMode.IGNORE:
                ignored += 1
                continue
            amount = entry["amount"]
            if amount is None or amount == ZERO:
                continue
            section = revenue if amount > ZERO else expenses
            month = entry["date"].astimezone(timezone.utc).month
            section.add(month, amount)
            other = mode == DisplayMode.OTHER
            ref_key = "other" if other else entry["ref_type"]
            label = (
                "Other"
                if other
                else (rule.display_name if rule else ref_type_display_name(entry["ref_type"]))
            )
            key = f"{section.key}-{ref_key}"
            parent = section.children.setdefault(ref_key, Row(key, label))
            parent.add(month, amount)
            if rule and rule.split_reasons and not other:
                reason_rule = reasons[rule.ref_type].get(entry["reason"])
                reason_key = str(reason_rule.pk) if reason_rule else "other"
                label = reason_rule.display_name if reason_rule else "Other reasons"
                child_key = f"{key}-reason-{reason_key}"
                parent = parent.children.setdefault(reason_key, Row(child_key, label))
                parent.add(month, amount)
            corp_key = str(corp_id)
            corp_row = parent.children.setdefault(
                corp_key, Row(f"{parent.key}-corp-{corp_id}", corps[corp_id])
            )
            corp_row.add(month, amount)

        profit = Row("profit", "Net profit / loss")
        profit.amounts = [a + b for a, b in zip(revenue.amounts, expenses.amounts)]

    def rule_order(item):
        key, row = item
        rule = rules.get(key)
        return (99999 if key == "other" else rule.order if rule else 100, row.label)

    for section in (revenue, expenses):
        section.children = dict(sorted(section.children.items(), key=rule_order))
        for ref_key, row in section.children.items():
            rule = rules.get(ref_key)
            if rule and rule.split_reasons:
                reason_order = {str(r.pk): r.order for r in rule.reason_rules.all()}
                row.children = dict(
                    sorted(
                        row.children.items(),
                        key=lambda item: (reason_order.get(item[0], 99999), item[1].label),
                    )
                )
            for child in row.children.values():
                child.children = dict(
                    sorted(child.children.items(), key=lambda item: item[1].label)
                )

    months = [
        {
            "label": calendar.month_abbr[month],
            "available": datetime(year, month, 1, tzinfo=timezone.utc) >= cutoff
            and datetime(year, month, 1, tzinfo=timezone.utc) <= at,
            "current": (year, month) == (at.year, at.month),
        }
        for month in range(1, 13)
    ]
    return {
        "revenue": revenue,
        "expenses": expenses,
        "profit": profit,
        "months": months,
        "divisions": divisions,
        "cutoff": cutoff,
        "excluded_transfers": excluded_transfers,
        "excluded_entity_entries": excluded_entity_entries,
        "excluded_entity_rules": excluded_entity_rules,
        "ignored": ignored,
    }
