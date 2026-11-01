from unittest.mock import patch

import pytest
from celery.exceptions import Retry

from accountant.services.esi import EsiError, RetryableEsiError
from accountant.tasks import sync_all, sync_wallets

pytestmark = pytest.mark.django_db


def test_daily_dispatch_and_retention(source, second_source, offline):
    with patch("accountant.tasks.prune_history") as prune:
        sync_all()
    prune.assert_called_once()
    assert {call.args[0] for call in offline.call_args_list} == {
        source.corporation.pk,
        second_source.corporation.pk,
    }
    source.corporation.enabled = False
    source.corporation.save()
    offline.reset_mock()
    with patch("accountant.tasks.prune_history"):
        sync_all()
    offline.assert_called_once_with(second_source.corporation.pk)


def test_retry_and_exception_redaction():
    with (
        patch("accountant.tasks.sync_corporation", side_effect=RetryableEsiError("retry")),
        patch.object(sync_wallets, "retry", side_effect=Retry()) as retry,
    ):
        with pytest.raises(Retry):
            sync_wallets(1)
    assert retry.call_args.kwargs["countdown"] == 120
    with patch("accountant.tasks.sync_corporation", side_effect=RuntimeError("SECRET")):
        with pytest.raises(EsiError) as error:
            sync_wallets(1)
    assert "SECRET" not in str(error.value)
