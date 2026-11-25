"""Mode « demande d'abord » : part des cartes japonaises qui se vendent en Europe (Cardmarket),
puis va chercher chacune d'elles au meilleur prix sur Mercari.

Source : TCGdex, qui recopie chaque jour les prix Cardmarket des cartes japonaises
(tendance, moyennes 1 / 7 / 30 jours). Cardmarket ne publie pas le nombre de ventes :
la « demande » est donc estimée par la régularité des ventes (une moyenne 1 jour existe =
la carte s'est vendue hier) et par la stabilité du prix.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from .models import Card
from .tcgdex import API, TcgDex, card_from_raw

# Raretés recherchées (libellés TCGdex) et abréviation utilisée sur Mercari.
RARITY_CODES = {
    "Special illustration rare": "SAR",
    "Illustration rare": "AR",
    "Ultra Rare": "SR",
    "Hyper rare": "UR",
    "Mega Hyper Rare": "MUR",
    "Character Rare": "CHR",
    "Character Super Rare": "CSR",
    "Secret Rare": "UR",
    "Shiny Ultra Rare": "SSR",
}


@dataclass
class DemandCard:
    card: Card
    resale: float
    score: float
    sold_yesterday: bool
    trend_ratio: float  # tendance / moyenne 30 jours (> 1 = prix en hausse)

    @property
    def rarity_code(self) -> str:
        return RARITY_CODES.get(self.card.rarity, "")


def demand_score(card: Card, resale: float) -> tuple[float, bool, float]:
    """Score = racine du prix de revente × régularité des ventes × tendance.

    La racine évite que quelques cartes anciennes très chères (et peu vendues) écrasent le classement."""
    p = card.price
    sold_yesterday = bool(p.avg1)
    regularity = 1.0 + (0.5 if sold_yesterday else 0.0)
    trend_ratio = (p.trend / p.avg30) if (p.trend and p.avg30) else 1.0
    momentum = min(max(trend_ratio, 0.7), 1.3)
    return (resale ** 0.5) * regularity * momentum, sold_yesterday, round(trend_ratio, 2)


class DemandList:
    def __init__(self, dex: TcgDex, cache_path: Path, cache_hours: float = 20, workers: int = 8):
        self.dex = dex
        self.cache_path = cache_path
        self.cache_hours = cache_hours
        self.workers = workers

    def _load_cache(self) -> Optional[list[dict]]:
        try:
            data = json.loads(self.cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - data.get("saved", 0) > self.cache_hours * 3600:
            return None
        return data.get("cards")

    def _save_cache(self, cards: list[dict]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps({"saved": time.time(), "cards": cards}, ensure_ascii=False))

    def fetch_catalog(self, rarities: list[str]) -> list[dict]:
        """Toutes les cartes japonaises des raretés voulues, avec leurs prix Cardmarket (1 fois par jour)."""
        cached = self._load_cache()
        if cached is not None:
            print(f"Catalogue des prix : {len(cached)} cartes (cache du jour)")
            return cached
        ids: list[str] = []
        for rarity in rarities:
            try:
                ids += [c["id"] for c in self.dex.http.get_json(f"{API}/cards?rarity={quote(rarity)}")]
            except Exception as exc:
                print(f"  [demande] rareté « {rarity} » indisponible : {exc}")
        ids = list(dict.fromkeys(ids))

        def fetch(card_id: str) -> Optional[dict]:
            try:
                return self.dex.card_raw(card_id)
            except Exception:
                return None

        with ThreadPoolExecutor(self.workers) as pool:
            raws = [r for r in pool.map(fetch, ids) if r]
        slim = [
            {k: r.get(k) for k in ("id", "localId", "name", "rarity", "image", "set", "pricing")}
            for r in raws
            # Le filtre de TCGdex est large : on ne garde que les raretés demandées exactement.
            if (r.get("pricing") or {}).get("cardmarket") and r.get("rarity") in rarities
        ]
        print(f"Catalogue des prix : {len(ids)} cartes lues, {len(slim)} avec un prix Cardmarket")
        if slim:
            self._save_cache(slim)
        return slim

    def top(self, rarities: list[str], min_resale: float, require_sold_yesterday: bool,
            min_trend_ratio: float, limit: int, max_resale: float = 0) -> list[DemandCard]:
        result: list[DemandCard] = []
        for raw in self.fetch_catalog(rarities):
            card = card_from_raw(raw)
            p = card.price
            if not p or not p.has_recent_sales():
                continue
            resale = p.resale_estimate()
            if not resale or resale < min_resale or (max_resale and resale > max_resale):
                continue
            score, sold_yesterday, ratio = demand_score(card, resale)
            if require_sold_yesterday and not sold_yesterday:
                continue
            if ratio < min_trend_ratio:
                continue  # prix en chute : revente risquée
            result.append(DemandCard(card, resale, score, sold_yesterday, ratio))
        result.sort(key=lambda d: d.score, reverse=True)
        return result[:limit]
