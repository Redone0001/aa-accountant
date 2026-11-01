from decimal import Decimal, localcontext

from django import template

register = template.Library()


@register.filter
def isk(value, unit="isk"):
    if value is None:
        return "—"
    scale, suffix = {
        "million": (Decimal(10**6), " M. isk"),
        "billion": (Decimal(10**9), " B. isk"),
    }.get(unit, (Decimal(1), ""))
    with localcontext() as ctx:
        ctx.prec = 50
        amount = Decimal(value) / scale
        number = f"{amount:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
        # Keep a visible sign for small nonzero amounts when the chosen unit rounds to zero.
        if amount and abs(amount) < Decimal("0.005"):
            return ("−" if amount < 0 else "") + "<0.01" + suffix
        return number + suffix


@register.filter
def report_cells(row, months):
    return [(amount if month["available"] else None) for amount, month in zip(row.amounts, months)]
