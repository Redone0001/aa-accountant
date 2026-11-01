from datetime import datetime, timezone

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.timezone import now


def retention_months():
    value = getattr(settings, "ACCOUNTANT_RETENTION_MONTHS", 6)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImproperlyConfigured("ACCOUNTANT_RETENTION_MONTHS must be a positive integer.")
    return value


def retention_cutoff(at=None):
    """Current partial month plus N complete preceding UTC calendar months."""
    at = (at or now()).astimezone(timezone.utc)
    month_index = at.year * 12 + at.month - 1 - retention_months()
    year, month = divmod(month_index, 12)
    return datetime(year, month + 1, 1, tzinfo=timezone.utc)
