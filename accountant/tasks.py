from celery import shared_task

from accountant.models import Corporation
from accountant.services.esi import EsiError, RetryableEsiError
from accountant.services.importer import prune_history, sync_corporation


@shared_task
def sync_all():
    """Dispatch separate jobs so an unavailable corporation cannot block the others."""
    prune_history()
    for pk in Corporation.objects.filter(enabled=True).values_list("pk", flat=True):
        sync_wallets.delay(pk)


@shared_task(bind=True, max_retries=5)
def sync_wallets(self, corporation_id):
    try:
        return sync_corporation(corporation_id)
    except RetryableEsiError:
        raise self.retry(
            exc=RetryableEsiError("Temporary ESI failure."),
            countdown=min(3600, 120 * (2**self.request.retries)),
        ) from None
    except EsiError:
        # Detailed safe error is visible on the source page. Reauthorization may be needed.
        raise
    except Exception:
        # Ensure Celery never serializes a token-bearing exception into the result backend.
        raise EsiError(
            "Synchronization failed; check source status and token authorization."
        ) from None
