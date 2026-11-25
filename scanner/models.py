from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    """Une annonce Mercari, achetable via Buyee."""

    item_id: str
    url: str
    title: str
    price_jpy: int
    thumbnail: str = ""
    eur_per_jpy: Optional[float] = None
    condition: Optional[int] = None
    seller_pays_shipping: Optional[bool] = None
    photos: list[str] = field(default_factory=list)
    description: str = ""
    available: bool = True


@dataclass
class CardPrice:
    """Prix Cardmarket (EUR) d'une carte japonaise, via TCGdex."""

    trend: Optional[float] = None
    avg1: Optional[float] = None
    avg7: Optional[float] = None
    avg30: Optional[float] = None
    low: Optional[float] = None
    product_id: Optional[int] = None
    updated: str = ""

    def resale_estimate(self) -> Optional[float]:
        """Prix de revente prudent : le plus bas entre tendance, moyenne 7 j et moyenne 30 j."""
        values = [v for v in (self.trend, self.avg7, self.avg30) if v]
        return min(values) if values else None

    def has_recent_sales(self) -> bool:
        return bool(self.avg7) and bool(self.avg30)


@dataclass
class Card:
    """Une carte identifiée dans le catalogue japonais TCGdex."""

    card_id: str  # ex. "SV2a-201"
    name: str
    local_id: str
    set_id: str
    set_name: str
    set_official_count: Optional[int] = None
    rarity: str = ""
    image: str = ""
    price: Optional[CardPrice] = None

    @property
    def number_label(self) -> str:
        if self.set_official_count:
            return f"{self.local_id}/{self.set_official_count:03d}"
        return self.local_id

    @property
    def search_keyword(self) -> str:
        """Mots-clés pour retrouver toutes les annonces de cette carte sur Mercari."""
        return f"{self.name} {self.number_label}"

    @property
    def cardmarket_url(self) -> str:
        if self.price and self.price.product_id:
            return f"https://www.cardmarket.com/fr/Pokemon/Products?idProduct={self.price.product_id}"
        return ""


@dataclass
class ProfitBreakdown:
    purchase_eur: float
    buyee_fee_eur: float
    domestic_shipping_eur: float
    international_shipping_eur: float
    eu_duty_eur: float
    vat_eur: float
    handling_eur: float
    total_cost_eur: float
    resale_eur: float
    marketplace_fee_eur: float
    shipping_to_buyer_eur: float
    net_revenue_eur: float
    profit_eur: float
    margin: float


@dataclass
class Deal:
    card: Card
    listing: Listing
    profit: ProfitBreakdown
    compared_listings: int
    vision_note: str = ""
