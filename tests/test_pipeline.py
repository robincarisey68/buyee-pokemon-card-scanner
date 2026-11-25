from pathlib import Path
from types import SimpleNamespace

import yaml

from scanner.identify import Identifier
from scanner.main import Scanner
from scanner.mercari import listing_from_search_item
from scanner.models import Listing
from scanner.state import State
from tests.fake_dex import FakeDex

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())


class FakeMercari:
    """M6-110 (revente ≈ 188 €) : une annonce abîmée très bon marché, une bonne à 15 000 ¥, une trop chère."""

    def __init__(self):
        self.items = {
            "m1": ("メガレックウザex SAR ストームエメラルダ 110/076", 12000, 5, ""),        # état 5 : écartée
            "m0": ("メガレックウザex SAR ストームエメラルダ 110/076", 13000, 2, "角に白欠けあり"),  # description : écartée
            "m2": ("メガレックウザex SAR ストームエメラルダ 110/076", 15000, 2, "美品です"),   # la bonne affaire
            "m3": ("メガレックウザex SAR ストームエメラルダ 110/076", 40000, 1, ""),        # trop chère
            "m4": ("メガレックウザex SAR まとめ 3枚", 5000, 1, ""),                         # lot : exclu
            "m5": ("リザードンex SAR 201/165", 50000, 1, ""),                               # pas rentable
        }
        self.calls = []

    def search(self, keyword, pages, conditions=None, price_max=None, cheapest_first=False):
        self.calls.append((keyword, conditions, price_max, cheapest_first))
        out = []
        for k, (t, p, cond, _) in self.items.items():
            if conditions and cond not in conditions:
                continue
            if price_max and p > price_max:
                continue
            out.append(Listing(item_id=k, url=f"https://buyee.jp/mercari/item/{k}", title=t, price_jpy=p,
                               condition=cond, seller_pays_shipping=True))
        return out

    def load_item(self, listing):
        _, _, cond, desc = self.items[listing.item_id]
        listing.condition = cond
        listing.description = desc
        listing.photos = [f"https://static.mercdn.net/item/detail/orig/photos/{listing.item_id}_1.jpg"]
        return listing


def make_scanner(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Scanner(dict(CFG))
    s.mercari = FakeMercari()
    s.dex = FakeDex()
    s.identifier = Identifier(s.dex)
    s.update_fx = lambda: setattr(s, "eur_per_jpy", 0.0061)
    return s


def test_pipeline_finds_cheapest_good_listing(monkeypatch, tmp_path):
    s = make_scanner(monkeypatch)
    deals = s.run(State(tmp_path / "state.json"), webhook=None, dry_run=True)
    assert len(deals) == 1
    d = deals[0]
    assert d.card.card_id == "M6-110"
    assert d.listing.item_id == "m2"
    assert d.listing.url == "https://buyee.jp/mercari/item/m2"
    assert d.profit.margin >= 0.35
    # La recherche détaillée filtre l'état et le prix maximum côté Mercari.
    keyword, conditions, price_max, cheapest = s.mercari.calls[-1]
    assert keyword == "メガレックウザex 110/076"
    assert conditions == [1, 2, 3] and cheapest and price_max > 15000


def test_already_alerted_listing_is_skipped(monkeypatch, tmp_path):
    s = make_scanner(monkeypatch)
    state = State(tmp_path / "state.json")
    state.mark("m2")
    assert s.run(state, webhook=None, dry_run=True) == []


def test_discord_message_shape(monkeypatch, tmp_path):
    from scanner.discord import build_message

    s = make_scanner(monkeypatch)
    deal = s.run(State(tmp_path / "s.json"), webhook=None, dry_run=True)[0]
    embed = build_message(deal)["embeds"][0]
    assert embed["url"] == "https://buyee.jp/mercari/item/m2"
    assert "Bénéfice net" in embed["description"]
    assert embed["image"]["url"].endswith("m2_1.jpg")


def test_listing_from_search_item():
    it = SimpleNamespace(id_="m123", name="ピカチュウ AR", price=3000, is_no_price=False, auction=None,
                         thumbnails=["https://t/1.jpg"], item_condition_id=2, shipping_payer_id=2)
    l = listing_from_search_item(it)
    assert l.url == "https://buyee.jp/mercari/item/m123"
    assert l.condition == 2 and l.seller_pays_shipping is True
    # Boutiques Mercari (id sans "m") et enchères ignorées.
    assert listing_from_search_item(SimpleNamespace(**{**it.__dict__, "id_": "abc"})) is None
    assert listing_from_search_item(SimpleNamespace(**{**it.__dict__, "auction": SimpleNamespace(id_="a1")})) is None
    # Un objet enchère vide (annonce à prix fixe) est accepté.
    assert listing_from_search_item(SimpleNamespace(**{**it.__dict__, "auction": SimpleNamespace(id_=None)})) is not None
