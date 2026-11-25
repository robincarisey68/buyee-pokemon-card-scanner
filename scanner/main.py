"""Pipeline complet, en deux modes :
- « demande » : cartes JP qui se vendent sur Cardmarket -> recherche de chacune sur Mercari ;
- « offres » : recherches larges sur Mercari -> identification -> prix Cardmarket.
Puis bénéfice net, seuil de marge et alerte Discord avec le lien Buyee."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from . import discord
from .filters import good_condition, title_excluded
from .http import Http
from .mercari import Mercari
from .demand import DemandList
from .identify import Identifier
from .models import Card, Deal
from .profit import compute_profit, max_price_jpy_for_margin
from .state import State
from .tcgdex import TcgDex
from .vision import VisionChecker

DEFAULT_EUR_PER_JPY = 0.0059
FX_URL = "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=EUR"


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Scanner:
    def __init__(self, cfg: dict, http: Http | None = None):
        self.cfg = cfg
        self.http = http or Http()
        self.mercari = Mercari(tuple(cfg.get("request_delay_seconds", [2, 4])))
        self.dex = TcgDex(self.http)
        self.identifier = Identifier(self.dex)
        v = cfg.get("vision", {})
        self.vision = VisionChecker(v.get("enabled", True), v.get("max_checks_per_run", 10))
        self.eur_per_jpy = DEFAULT_EUR_PER_JPY
        self._id_cache: dict[str, Card | None] = {}
        self.listings_seen = 0

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

    def update_fx(self) -> None:
        """Taux du jour (BCE via frankfurter.dev), majoré de la marge de change de Buyee."""
        markup = 1 + self.cfg.get("fx_markup", 0.03)
        try:
            data = self.http.get_json(FX_URL)
            self.eur_per_jpy = float(data["rates"]["EUR"]) * markup
        except Exception as exc:
            print(f"Taux de change indisponible ({exc}), valeur par défaut utilisée.")
            self.eur_per_jpy = DEFAULT_EUR_PER_JPY * markup
        print(f"Taux utilisé : 1000 ¥ = {self.eur_per_jpy * 1000:.2f} €")

    def discover(self) -> list[tuple[Card, float, int]]:
        """Recherches larges : repère les cartes dont au moins une annonce semble rentable."""
        best: dict[str, tuple[Card, float, int]] = {}
        for query in self.cfg["search_queries"]:
            listings = self.mercari.search(query, self.cfg["pages_per_query"])
            self.listings_seen += len(listings)
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

    def best_offer(self, card: Card, resale: float, extra_keywords: list[str] | None = None) -> Deal | None:
        """Compare toutes les annonces de la carte (jusqu'à 10 pages) et garde la meilleure en bon état."""
        limit = self.max_price(resale)
        same: dict[str, object] = {}
        for keyword in [card.search_keyword, *(extra_keywords or [])]:
            listings = self.mercari.search(
                keyword, self.cfg["pages_per_card"],
                conditions=self.cfg["accepted_conditions"], price_max=limit, cheapest_first=True,
            )
            self.listings_seen += len(listings)
            for l in listings:
                if l.item_id in same or title_excluded(l.title, self.cfg["exclude_keywords"]):
                    continue
                c = self.identify(l.title)
                if c is not None and c.card_id == card.card_id:
                    same[l.item_id] = l
            if same:
                break  # le premier mot-clé a suffi
        same = list(same.values())
        same.sort(key=lambda l: l.price_jpy)
        print(f"  {card.card_id} {card.name} : {len(same)} annonces identiques en bon état, revente {resale:.2f} €, prix max {limit} ¥")
        for l in same:
            if l.price_jpy > limit:
                break
            self.mercari.load_item(l)
            if not l.available or not good_condition(l, self.cfg["accepted_conditions"]):
                continue
            if title_excluded(l.description, self.cfg.get("exclude_description_keywords", [])):
                print(f"    écartée (description) : {l.url}")
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

    def demand_candidates(self, state: State) -> list[tuple[Card, float, list[str]]]:
        """Mode demande : les cartes les plus demandées, parcourues par tranches au fil des passages."""
        d = self.cfg["demand"]
        cache = Path(self.cfg.get("_state_dir", "state")) / "catalogue_prix.json"
        top = DemandList(self.dex, cache, d.get("cache_hours", 20)).top(
            d["rarities"], self.cfg["min_resale_eur"], d.get("require_sold_yesterday", False),
            d.get("min_trend_ratio", 0.8), d["list_size"], d.get("max_resale_eur", 0),
        )
        if not top:
            return []
        start = state.demand_cursor % len(top)
        n = min(d["cards_per_run"], len(top))
        batch = [top[(start + i) % len(top)] for i in range(n)]
        state.demand_cursor = (start + n) % len(top)
        print(f"Mode demande : {len(top)} cartes demandées, cartes {start + 1} à {start + n} ce passage")
        out = []
        for dc in batch:
            extra = [f"{dc.card.name} {dc.rarity_code} {dc.card.set_name}".strip()] if dc.rarity_code else []
            out.append((dc.card, dc.resale, extra))
        return out

    def run(self, state: State, webhook: str | None, dry_run: bool) -> list[Deal]:
        deals: list[Deal] = []
        self.update_fx()
        modes = self.cfg.get("modes", ["offres"])
        candidates: list[tuple[Card, float, list[str]]] = []
        if "demande" in modes:
            candidates += self.demand_candidates(state)
        if "offres" in modes:
            candidates += [(card, resale, []) for card, resale, _ in self.discover()]
        done: set[str] = set()
        for card, resale, extra in candidates:
            if not card.price or card.card_id in done:
                continue
            done.add(card.card_id)
            deal = self.best_offer(card, resale, extra)
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
        cfg.setdefault("demand", {})["cards_per_run"] = 3

    if not webhook and not args.dry_run:
        print("DISCORD_WEBHOOK_URL absent : passage en mode test (rien n'est envoyé).")
        args.dry_run = True

    cfg["_state_dir"] = str(Path(args.state).parent)
    state = State(Path(args.state))
    scanner = Scanner(cfg)
    deals = scanner.run(state, webhook, args.dry_run)
    state.save()
    print(f"Terminé : {len(deals)} bonne(s) affaire(s), {scanner.listings_seen} annonces lues.")
    if scanner.listings_seen == 0:
        print("ERREUR : aucune annonce lue sur Mercari.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
