import json
import time
from pathlib import Path

import yaml

from scanner.demand import DemandList, demand_score
from scanner.identify import Identifier
from scanner.main import Scanner
from scanner.state import State
from scanner.tcgdex import card_from_raw
from tests.fake_dex import CARDS, FakeDex
from tests.test_pipeline import FakeMercari

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())


def write_cache(path: Path, cards: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"saved": time.time(), "cards": cards}))


def test_score_prefers_liquid_rising_cards():
    a = card_from_raw(CARDS["M6-110"])   # tendance 221 > moyenne 30 j 188 : en hausse
    b = card_from_raw(CARDS["SV2a-185"])
    sa, sold, ratio = demand_score(a, 188.38)
    sb, _, _ = demand_score(b, 20.01)
    assert sold and ratio > 1 and sa > sb


def test_top_filters_and_ranks(tmp_path):
    cache = tmp_path / "catalogue_prix.json"
    falling = dict(CARDS["M6-113"])
    falling["pricing"] = {"cardmarket": {"trend": 200, "avg7": 300, "avg30": 419, "avg1": 210, "idProduct": 9}}
    write_cache(cache, [CARDS["SV2a-201"], CARDS["M6-110"], CARDS["SV2a-185"], CARDS["M6-058"], falling])
    rarities = ["Special illustration rare", "Ultra Rare", "Double rare", "Mega Hyper Rare"]
    top = DemandList(FakeDex(), cache).top(rarities, min_resale=25, require_sold_yesterday=False,
                                           min_trend_ratio=0.8, limit=10, max_resale=1000)
    ids = [d.card.card_id for d in top]
    # Cartes sous 25 € et prix qui s'effondre écartés ; M6-110 (en hausse) passe devant SV2a-201 (en baisse).
    assert ids == ["M6-110", "SV2a-201"]
    assert top[0].rarity_code == "SAR"


def test_demand_mode_end_to_end(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = dict(CFG)
    cfg["modes"] = ["demande"]
    cfg["_state_dir"] = str(tmp_path)
    cfg["demand"] = {**CFG["demand"], "cards_per_run": 1}
    write_cache(tmp_path / "catalogue_prix.json", [CARDS["M6-110"], CARDS["SV2a-201"]])
    s = Scanner(cfg)
    s.mercari = FakeMercari()
    s.dex = FakeDex()
    s.identifier = Identifier(s.dex)
    s.update_fx = lambda: setattr(s, "eur_per_jpy", 0.0061)
    state = State(tmp_path / "state.json")

    # 1er passage : la carte n°1 du classement (M6-110) -> l'annonce m2 à 15 000 ¥.
    deals = s.run(state, webhook=None, dry_run=True)
    assert [d.listing.item_id for d in deals] == ["m2"]
    assert state.demand_cursor == 1
    # 2e passage : la carte suivante (SV2a-201, trop chère sur Mercari) -> rien, et retour au début.
    assert s.run(state, webhook=None, dry_run=True) == []
    assert state.demand_cursor == 0


def test_catalog_keeps_only_requested_rarities(tmp_path):
    class Http:
        def get_json(self, url):
            return [{"id": "SV2a-201"}, {"id": "MC-764"}]

    class Dex:
        http = Http()

        def card_raw(self, card_id):
            if card_id == "MC-764":
                return {"id": "MC-764", "name": "ピカチュウex", "rarity": "None",
                        "set": {"id": "MC"}, "pricing": {"cardmarket": {"trend": 900}}}
            return CARDS[card_id]

    cards = DemandList(Dex(), tmp_path / "c.json").fetch_catalog(["Special illustration rare"])
    assert [c["id"] for c in cards] == ["SV2a-201"]
