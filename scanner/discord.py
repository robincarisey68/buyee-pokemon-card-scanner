"""Envoi des alertes dans un salon Discord (webhook)."""
from __future__ import annotations

import requests

from .filters import CONDITION_LABELS
from .models import Deal


def build_message(deal: Deal) -> dict:
    p = deal.profit
    card = deal.card
    l = deal.listing
    lines = [
        f"**Bénéfice net : {p.profit_eur:.2f} € (+{p.margin * 100:.0f} %)**",
        f"Prix Buyee : {l.price_jpy:,} ¥ (≈ {p.purchase_eur:.2f} €)".replace(",", " "),
        f"Coût total rendu en France : {p.total_cost_eur:.2f} €",
        f"Revente estimée Cardmarket : {p.resale_eur:.2f} € → net {p.net_revenue_eur:.2f} €",
        f"État : {CONDITION_LABELS.get(l.condition or 0, 'inconnu')}",
        f"Annonce la moins chère parmi {deal.compared_listings} en bon état",
    ]
    if deal.vision_note:
        lines.append(f"Photos (IA) : {deal.vision_note}")
    detail = (
        f"Achat {p.purchase_eur:.2f} + Buyee {p.buyee_fee_eur:.2f} + port JP {p.domestic_shipping_eur:.2f} "
        f"+ port intl {p.international_shipping_eur:.2f} + taxe UE {p.eu_duty_eur:.2f} + TVA {p.vat_eur:.2f}"
        f" | Revente : commission {p.marketplace_fee_eur:.2f} + envoi {p.shipping_to_buyer_eur:.2f}"
    )
    fields = [{"name": "Détail des frais (€)", "value": detail[:1024]}]
    if card.cardmarket_url:
        fields.append({"name": "Cardmarket", "value": card.cardmarket_url})
    embed = {
        "title": f"{card.name} {card.number_label} — {card.set_name}"[:256],
        "url": l.url,
        "description": "\n".join(lines)[:4000],
        "color": 0x2ECC71,
        "fields": fields,
        "footer": {"text": f"{card.rarity} · {card.card_id} · annonce {l.item_id}"},
    }
    image = l.photos[0] if l.photos else l.thumbnail
    if image:
        embed["image"] = {"url": image}
    if card.image:
        embed["thumbnail"] = {"url": card.image}
    return {"username": "Scanner Buyee", "embeds": [embed]}


def send(webhook_url: str, deal: Deal) -> bool:
    resp = requests.post(webhook_url, json=build_message(deal), timeout=20)
    return resp.status_code in (200, 204)


def send_text(webhook_url: str, text: str) -> None:
    requests.post(webhook_url, json={"username": "Scanner Buyee", "content": text[:1900]}, timeout=20)
