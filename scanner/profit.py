"""Calcul du bénéfice net : achat Buyee + import en France, puis revente."""
from __future__ import annotations

from .models import Listing, ProfitBreakdown


def compute_profit(listing: Listing, resale_eur: float, costs: dict, resale: dict,
                   eur_per_jpy: float) -> ProfitBreakdown:
    purchase = listing.price_jpy * eur_per_jpy
    buyee_fee = costs["buyee_service_fee_jpy"] * eur_per_jpy
    domestic = 0.0 if listing.seller_pays_shipping is not False else costs["domestic_shipping_jpy"] * eur_per_jpy
    international = costs["international_shipping_per_card_jpy"] * eur_per_jpy
    duty = costs["eu_flat_duty_eur"]
    # TVA à l'import : sur la valeur de la carte + le transport + les droits.
    vat = (purchase + domestic + international + duty) * costs["import_vat_rate"]
    handling = costs.get("import_handling_eur", 0.0)
    total_cost = purchase + buyee_fee + domestic + international + duty + vat + handling

    marketplace_fee = resale_eur * resale["marketplace_fee_rate"]
    shipping_out = resale["shipping_to_buyer_eur"]
    net_revenue = resale_eur - marketplace_fee - shipping_out
    profit = net_revenue - total_cost
    margin = profit / total_cost if total_cost else 0.0
    return ProfitBreakdown(
        purchase_eur=round(purchase, 2),
        buyee_fee_eur=round(buyee_fee, 2),
        domestic_shipping_eur=round(domestic, 2),
        international_shipping_eur=round(international, 2),
        eu_duty_eur=round(duty, 2),
        vat_eur=round(vat, 2),
        handling_eur=round(handling, 2),
        total_cost_eur=round(total_cost, 2),
        resale_eur=round(resale_eur, 2),
        marketplace_fee_eur=round(marketplace_fee, 2),
        shipping_to_buyer_eur=round(shipping_out, 2),
        net_revenue_eur=round(net_revenue, 2),
        profit_eur=round(profit, 2),
        margin=round(margin, 4),
    )


def max_price_jpy_for_margin(resale_eur: float, min_margin: float, costs: dict, resale: dict,
                              eur_per_jpy: float, seller_pays_shipping: bool = True) -> int:
    """Prix d'annonce maximum (yens) qui donne encore la marge voulue. Sert de pré-filtre."""
    net_revenue = resale_eur * (1 - resale["marketplace_fee_rate"]) - resale["shipping_to_buyer_eur"]
    max_cost = net_revenue / (1 + min_margin)
    vat = costs["import_vat_rate"]
    fixed_jpy = costs["international_shipping_per_card_jpy"] + (0 if seller_pays_shipping else costs["domestic_shipping_jpy"])
    # total = (p + fixed)*r*(1+vat) + fee*r + duty*(1+vat) + handling
    rest = max_cost - costs["buyee_service_fee_jpy"] * eur_per_jpy - costs["eu_flat_duty_eur"] * (1 + vat) - costs.get("import_handling_eur", 0.0)
    p = rest / (eur_per_jpy * (1 + vat)) - fixed_jpy
    return max(0, int(p))
