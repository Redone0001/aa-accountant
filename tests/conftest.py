from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from unittest.mock import patch

import pytest
from allianceauth.authentication.models import UserProfile
from allianceauth.eveonline.models import EveCharacter
from django.contrib.auth.models import Permission, User
from esi.models import Token

from accountant.models import Corporation, Dashboard, JournalEntry, WalletDivision

AT = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline():
    """Tests must never make live ESI requests or dispatch jobs to an external broker."""
    with (
        patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected HTTP")),
        patch("httpx2.Client.send", side_effect=AssertionError("Unexpected HTTPX")),
        patch("accountant.tasks.sync_wallets.delay") as delay,
    ):
        yield delay


@pytest.fixture
def source(db):
    corporation = Corporation.objects.create(corporation_id=98000001, name="Northstar Industries")
    return WalletDivision.objects.create(corporation=corporation, division=1, name="Operations")


@pytest.fixture
def second_source(db):
    corporation = Corporation.objects.create(corporation_id=98000002, name="Orbital Logistics")
    return WalletDivision.objects.create(corporation=corporation, division=4, name="SRP")


@pytest.fixture
def board(source):
    dashboard = Dashboard.objects.create(name="Alliance profit & loss")
    dashboard.divisions.add(source)
    return dashboard


@pytest.fixture
def entry(source):
    ids = count(10000000000)

    def create(**kwargs):
        data = dict(
            division=source,
            entry_id=next(ids),
            date=AT - timedelta(days=1),
            amount=Decimal("100"),
            ref_type="player_donation",
        )
        data.update(kwargs)
        return JournalEntry.objects.create(**data)

    return create


@pytest.fixture
def user(db):
    result = User.objects.create_user(username="reader", password="test-password")
    character = EveCharacter.objects.create(character_id=90000001, character_name="Test Accountant")
    UserProfile.objects.filter(user=result).update(main_character=character)
    return result


@pytest.fixture
def grant():
    def give(user, *codenames):
        user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="accountant", codename__in=codenames)
        )
        if hasattr(user, "_perm_cache"):
            del user._perm_cache
        if hasattr(user, "_user_perm_cache"):
            del user._user_perm_cache
        return user

    return give


@pytest.fixture
def token(user):
    result = Token(
        user=user,
        character_id=90000001,
        character_name="Test Accountant",
        access_token="not-a-real-access-token",
        refresh_token="not-a-real-refresh-token",
        character_owner_hash="test-owner",
        created=AT,
    )
    # A synthetic token has no EVE identity; bypass AA's live ownership lookup signal.
    Token.objects.bulk_create([result])
    return result
