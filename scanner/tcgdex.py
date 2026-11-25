"""Catalogue des cartes japonaises et prix Cardmarket, via l'API gratuite TCGdex."""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from .http import Http
from .models import Card, CardPrice

API = "https://api.tcgdex.net/v2/ja"


class TcgDex:
    def __init__(self, http: Http):
        self.http = http
        self._sets: Optional[list[dict]] = None
        self._set_cards: dict[str, dict] = {}
        self._cards: dict[str, dict] = {}

    def sets(self) -> list[dict]:
        if self._sets is None:
            self._sets = self.http.get_json(f"{API}/sets")
        return self._sets

    def set_detail(self, set_id: str) -> dict:
        if set_id not in self._set_cards:
            self._set_cards[set_id] = self.http.get_json(f"{API}/sets/{quote(set_id, safe='')}")
        return self._set_cards[set_id]

    def card_raw(self, card_id: str) -> dict:
        raw = self._cards.get(card_id)
        if raw is None:
            raw = self.http.get_json(f"{API}/cards/{quote(card_id, safe='')}")
            self._cards[card_id] = raw
        return raw

    def card(self, card_id: str) -> Card:
        raw = self.card_raw(card_id)
        return card_from_raw(raw)


def price_from_raw(raw: dict) -> Optional[CardPrice]:
    cm = (raw.get("pricing") or {}).get("cardmarket")
    if not cm:
        return None
    return CardPrice(
        trend=cm.get("trend") or None,
        avg1=cm.get("avg1") or None,
        avg7=cm.get("avg7") or None,
        avg30=cm.get("avg30") or None,
        low=cm.get("low") or None,
        product_id=cm.get("idProduct"),
        updated=cm.get("updated") or "",
    )


def card_from_raw(raw: dict) -> Card:
    s = raw.get("set") or {}
    count = (s.get("cardCount") or {}).get("official")
    image = raw.get("image") or ""
    return Card(
        card_id=raw["id"],
        name=raw.get("name", ""),
        local_id=raw.get("localId", ""),
        set_id=s.get("id", ""),
        set_name=s.get("name", ""),
        set_official_count=count or None,
        rarity=raw.get("rarity") or "",
        image=f"{image}/high.png" if image else "",
        price=price_from_raw(raw),
    )
