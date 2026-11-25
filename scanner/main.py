"""Pipeline complet : recherche Buyee -> identification -> prix -> bénéfice -> alerte Discord."""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from pathlib import Path

import yaml

from . import discord
from .buyee import Buyee
from .filters import good_condition, title_excluded
from .http import Http
from .identify import Identifier
from .models import Card, Deal, Listing
from .profit import compute_profit, max_price_jpy_for_margin
from .state import State
from .tcgdex import TcgDex
from .vision import VisionChecker

DEFAULT_EUR_PER_JPY = 0.0061


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Scanner:
    def __init__(self, cfg: dict, http: Http | None = None):
        self.cfg = cfg
        self.http = http or Http(tuple(cfg.get("request_delay_seconds", [3, 6])))
        self.buyee = Buyee(self.http)
        self.dex = TcgDex(self.http)
        self.identifier = Identifier(self.dex)
        v = cfg.get("vision", {})
        self.vision = VisionChecker(v.get("enabled", True), v.get("max_checks_per_run", 10))
        self.eur_per_jpy = DEFAULT_EUR_PER_JPY
        self._id_cache: dict[str, Card | None] = {}

    # --- étapes ---------------------------------------------------------
    def identify(self, title: str) -> Card | None:
        if title not in self._id_cache:
            try:
                match = self.identifier.identify(title)
            except Exception as exc:
                print(f"  [identification] erreur sur « {title} » : {exc}")
                match = None
            self._id_cache[title] = match.card if match else None
        return self._id_cache[title]

    def resale_ok(self, card: Card) -> float | None:
        if not card.price:
            return None
        resale = card.price.resale_estimate()
        if not resale or resale < self.cfg["min_resale_eur"]:
            return None
        if self.cfg["resale"].get("require_recent_sales", True) and not card.price.has_recent_sales():
            return None
        return resale

    def max_price(self, resale: float) -> int:
        return max_price_jpy_for_margin(
            resale, self.cfg["min_margin"], self.cfg["costs"], self.cfg["resale"], self.eur_per_jpy
        )

    def update_fx(self, listings: list[Listing]) -> None:
        rates = [l.eur_per_jpy for l in listings if l.eur_per_jpy]
        if rates:
            self.eur_per_jpy = statistics.median(rates)

    def discover(self) -> list[tuple[Card, float, int]]:
        """Recherches larges : repère les cartes dont au moins une annonce semble rentable."""
        best: dict[str, tuple[Card, float, int]] = {}
        for query in self.cfg["search_queries"]:
            listings = self.buyee.search(query, self.cfg["pages_per_query"])
            self.update_fx(listings)
            stats = {"exclues": 0, "identifiées": 0, "avec prix FR": 0, "sous le prix max": 0}
            for l in listings:
                if title_excluded(l.title, self.cfg["exclude_keywords"]):
                    stats["exclues"] += 1
                    continue
                card = self.identify(l.title)
                if not card:
                    continue
                stats["identifiées"] += 1
                resale = self.resale_ok(card)
                if not resale:
                    continue
                stats["avec prix FR"] += 1
                limit = self.max_price(resale)
                if l.price_jpy > limit:
                    continue
                stats["sous le prix max"] += 1
                score = limit / l.price_jpy
                if card.card_id not in best or score > best[card.card_id][2]:
                    best[card.card_id] = (card, resale, score)
            detail = ", ".join(f"{k} {v}" for k, v in stats.items())
            print(f"Recherche « {query} » : {len(listings)} annonces ({detail})")
        ranked = sorted(best.values(), key=lambda t: t[2], reverse=True)
        return ranked[: self.cfg["max_cards_per_run"]]

    def best_offer(self, card: Card, resale: float) -> Deal | None:
        """Compare toutes les annonces de la carte (jusqu'à 10 pages) et garde la meilleure en bon état."""
        listings = self.buyee.search(card.search_keyword, self.cfg["pages_per_card"])
        same = [
            l for l in listings
            if not title_excluded(l.title, self.cfg["exclude_keywords"])
            and (c := self.identify(l.title)) is not None and c.card_id == card.card_id
        ]
        same.sort(key=lambda l: l.price_jpy)
        limit = self.max_price(resale)
        print(f"  {card.card_id} {card.name} : {len(same)} annonces identiques, revente {resale:.2f} €, prix max {limit} ¥")
        for l in same:
            if l.price_jpy > limit:
                break
            self.buyee.load_item(l)
            if not l.available or not good_condition(l, self.cfg["accepted_conditions"]):
                continue
            profit = compute_profit(l, resale, self.cfg["costs"], self.cfg["resale"], self.eur_per_jpy)
            if profit.margin < self.cfg["min_margin"]:
                continue
            note = ""
            result = self.vision.check(card, l)
            if result is not None:
                if not (result.same_card and result.single_card and result.condition_ok):
                    print(f"    écartée par la vérification photo : {result.note}")
                    continue
                note = result.note
            return Deal(card=card, listing=l, profit=profit, compared_listings=len(same), vision_note=note)
        return None

    def run(self, state: State, webhook: str | None, dry_run: bool) -> list[Deal]:
        deals: list[Deal] = []
        for card, resale, _ in self.discover():
            if not card.price:
                continue
            deal = self.best_offer(card, resale)
            if not deal:
                continue
            if state.already_alerted(deal.listing.item_id):
                print(f"    déjà envoyée : {deal.listing.url}")
                continue
            deals.append(deal)
            print(f"    AFFAIRE : {deal.listing.url} bénéfice {deal.profit.profit_eur} € (+{deal.profit.margin:.0%})")
            if not dry_run and webhook:
                if discord.send(webhook, deal):
                    state.mark(deal.listing.item_id)
        return deals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scanner de bonnes affaires Pokémon sur Buyee")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--state", default="state/state.json")
    parser.add_argument("--dry-run", action="store_true", help="n'envoie rien sur Discord")
    parser.add_argument("--test-discord", action="store_true", help="envoie un message de test et s'arrête")
    parser.add_argument("--quick", action="store_true", help="test rapide : 1 recherche, 1 page")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config))
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip() or None

    if args.test_discord:
        if not webhook:
            print("DISCORD_WEBHOOK_URL manquant")
            return 1
        discord.send_text(webhook, "✅ Scanner Buyee connecté. Les bonnes affaires arriveront ici.")
        return 0

    if args.quick:
        cfg["search_queries"] = cfg["search_queries"][:1]
        cfg["pages_per_query"] = 1
        cfg["pages_per_card"] = 2
        cfg["max_cards_per_run"] = 2

    if not webhook and not args.dry_run:
        print("DISCORD_WEBHOOK_URL absent : passage en mode test (rien n'est envoyé).")
        args.dry_run = True

    state = State(Path(args.state))
    deals = Scanner(cfg).run(state, webhook, args.dry_run)
    state.save()
    print(f"Terminé : {len(deals)} bonne(s) affaire(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
