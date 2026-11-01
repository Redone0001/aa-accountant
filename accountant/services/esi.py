"""Small ESI transport; AA/django-esi owns SSO tokens and refreshes them.

Decode money as Decimal directly from JSON, before any float conversion.
"""

import json
from decimal import Decimal

import requests
from django.conf import settings

from accountant import __version__

SCOPES = ["esi-wallet.read_corporation_wallets.v1", "esi-characters.read_corporation_roles.v1"]
WALLET_ROLES = {"CEO", "Director", "Accountant", "Junior_Accountant"}


class EsiError(Exception):
    """Safe message: never includes response bodies, URLs or credentials."""


class RetryableEsiError(EsiError):
    pass


class EsiClient:
    base_url = "https://esi.evetech.net"

    def __init__(self, token):
        self.token = token
        self.session = requests.Session()
        contact = getattr(settings, "ESI_USER_CONTACT_EMAIL", "")
        self.session.headers.update(
            {
                "User-Agent": f"AAAccountant/{__version__} ({contact})",
                "X-Compatibility-Date": "2025-07-23",
                "Accept": "application/json",
            }
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def get(self, path, *, authenticated=False, params=None):
        headers = {}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token.valid_access_token()}"
        try:
            response = self.session.get(
                self.base_url + path, params=params, headers=headers, timeout=30
            )
        except requests.RequestException:
            raise RetryableEsiError("ESI connection failed; synchronization will retry.") from None
        if response.status_code in (420, 429) or response.status_code >= 500:
            raise RetryableEsiError(f"ESI temporarily unavailable (HTTP {response.status_code}).")
        if response.status_code != 200:
            raise EsiError(
                f"ESI request refused (HTTP {response.status_code}); check token and roles."
            )
        try:
            return json.loads(response.text, parse_float=Decimal), response.headers
        except (ValueError, TypeError):
            raise RetryableEsiError("ESI returned an invalid response.") from None

    def identity(self):
        character, _ = self.get(f"/characters/{self.token.character_id}")
        roles, _ = self.get(f"/characters/{self.token.character_id}/roles", authenticated=True)
        if not WALLET_ROLES.intersection(roles.get("roles", [])):
            raise EsiError("Character needs Accountant, Junior Accountant, Director or CEO role.")
        corp_id = character["corporation_id"]
        corp, _ = self.get(f"/corporations/{corp_id}")
        # This request also verifies ESI actually permits corporation wallet access.
        wallets, _ = self.get(f"/corporations/{corp_id}/wallets", authenticated=True)
        return corp_id, corp["name"], wallets

    def journal_pages(self, corporation_id, division):
        page, pages = 1, 1
        while page <= pages:
            items, headers = self.get(
                f"/corporations/{corporation_id}/wallets/{division}/journal",
                authenticated=True,
                params={"page": page},
            )
            if not isinstance(items, list):
                raise RetryableEsiError("ESI returned an invalid journal page.")
            try:
                reported_pages = int(headers.get("X-Pages", "1"))
                if reported_pages < 1:
                    raise ValueError
            except (ValueError, TypeError):
                raise RetryableEsiError("ESI returned invalid pagination headers.") from None
            pages = max(pages, reported_pages)
            yield items
            page += 1
