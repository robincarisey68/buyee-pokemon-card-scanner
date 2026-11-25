"""Annonces Mercari Japon (le site que Buyee revend), lues via la bibliothèque mercapi.

Buyee bloque les robots, mais chaque annonce Mercari a la même référence sur Buyee :
https://buyee.jp/mercari/item/<id>. On lit donc Mercari et on envoie le lien Buyee.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Optional

from .models import Listing

# Mercari : 1 = port payé par l'acheteur (着払い), 2 = port inclus, payé par le vendeur (送料込み).
SELLER_PAYS_ID = 2


def buyee_url(item_id: str) -> str:
    return f"https://buyee.jp/mercari/item/{item_id}"


def listing_from_search_item(it) -> Optional[Listing]:
    """Convertit un résultat de recherche mercapi en annonce. Ignore les boutiques et les prix absents."""
    item_id = getattr(it, "id_", "") or ""
    if not item_id.startswith("m") or getattr(it, "is_no_price", False) or not it.price:
        return None
    auction = getattr(it, "auction", None)
    if auction is not None and getattr(auction, "id_", None):
        return None  # enchère Mercari : le prix final n'est pas connu
    thumbs = getattr(it, "thumbnails", None) or []
    return Listing(
        item_id=item_id,
        url=buyee_url(item_id),
        title=it.name,
        price_jpy=int(it.price),
        thumbnail=thumbs[0] if thumbs else "",
        condition=getattr(it, "item_condition_id", None),
        seller_pays_shipping=(getattr(it, "shipping_payer_id", None) == SELLER_PAYS_ID),
    )


class Mercari:
    def __init__(self, delay_range: tuple[float, float] = (2, 4)):
        self.delay_range = delay_range
        self.failures = 0
        self._last = 0.0

    def _pause(self) -> None:
        if self._last:
            wait = random.uniform(*self.delay_range) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
        self._last = time.monotonic()

    @staticmethod
    def _client():
        # Un client neuf par appel : chaque asyncio.run() a sa propre boucle d'événements.
        from mercapi import Mercapi

        return Mercapi()

    def search(self, keyword: str, pages: int, conditions: Optional[list[int]] = None,
               price_max: Optional[int] = None, cheapest_first: bool = False) -> list[Listing]:
        """Annonces en vente. Par défaut les plus récentes d'abord ; sinon les moins chères d'abord."""
        return asyncio.run(self._search(keyword, pages, conditions or [], price_max, cheapest_first))

    async def _search(self, keyword: str, pages: int, conditions: list[int],
                      price_max: Optional[int], cheapest_first: bool) -> list[Listing]:
        from mercapi.requests import SearchRequestData

        sort = (
            (SearchRequestData.SortBy.SORT_PRICE, SearchRequestData.SortOrder.ORDER_ASC)
            if cheapest_first
            else (SearchRequestData.SortBy.SORT_CREATED_TIME, SearchRequestData.SortOrder.ORDER_DESC)
        )

        listings: list[Listing] = []
        seen: set[str] = set()
        try:
            self._pause()
            res = await self._client().search(
                keyword,
                sort_by=sort[0],
                sort_order=sort[1],
                status=[SearchRequestData.Status.STATUS_ON_SALE],
                item_conditions=conditions,
                price_max=price_max,
            )
            for page in range(pages):
                for it in res.items:
                    l = listing_from_search_item(it)
                    if l and l.item_id not in seen:
                        seen.add(l.item_id)
                        listings.append(l)
                if page + 1 >= pages or not res.meta.next_page_token:
                    break
                self._pause()
                res = await res.next_page()
        except Exception as exc:
            self.failures += 1
            print(f"  [mercari] « {keyword} » : erreur {type(exc).__name__} : {exc}")
        return listings

    def load_item(self, listing: Listing) -> Listing:
        return asyncio.run(self._load_item(listing))

    async def _load_item(self, listing: Listing) -> Listing:
        try:
            self._pause()
            item = await self._client().item(listing.item_id)
        except Exception as exc:
            print(f"  [mercari] annonce {listing.item_id} : erreur {exc}")
            listing.available = False
            return listing
        if item is None:
            listing.available = False
            return listing
        listing.available = "on_sale" in (item.status or "").lower()
        listing.title = item.name or listing.title
        listing.price_jpy = int(item.price or listing.price_jpy)
        if item.item_condition:
            listing.condition = item.item_condition.id_
        if item.shipping_payer:
            listing.seller_pays_shipping = item.shipping_payer.id_ == SELLER_PAYS_ID
        listing.photos = list(item.photos or [])
        listing.description = item.description or ""
        return listing
