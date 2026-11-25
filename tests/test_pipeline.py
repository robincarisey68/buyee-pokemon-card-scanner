from pathlib import Path

import yaml

from scanner.identify import Identifier
from scanner.main import Scanner
from scanner.models import Listing
from scanner.state import State
from tests.fake_dex import FakeDex

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())


class FakeBuyee:
    """M6-110 (revente ≈ 188 €) : une annonce abîmée très bon marché, une bonne à 15 000 ¥, une trop chère."""

    def __init__(self):
        self.items = {
            "m1": ("メガレックウザex SAR ストームエメラルダ 110/076", 12000, 5),   # état 5 : écartée
            "m2": ("メガレックウザex SAR ストームエメラルダ 110/076", 15000, 2),   # la bonne affaire
            "m3": ("メガレックウザex SAR ストームエメラルダ 110/076", 40000, 1),   # trop chère
            "m4": ("メガレックウザex SAR まとめ 3枚", 5000, 1),                   # lot : exclu
            "m5": ("リザードンex SAR 201/165", 50000, 1),                          # pas rentable
        }

    def search(self, keyword, pages, condition=None):
        return [Listing(item_id=k, url=f"https://buyee.jp/mercari/item/{k}", title=t, price_jpy=p,
                        eur_per_jpy=0.0061) for k, (t, p, _) in self.items.items()]

    def load_item(self, listing):
        listing.condition = self.items[listing.item_id][2]
        listing.seller_pays_shipping = True
        listing.photos = [f"https://static.mercdn.net/item/detail/hq/photos/{listing.item_id}_1.jpg"]
        return listing


def make_scanner(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Scanner(dict(CFG))
    s.buyee = FakeBuyee()
    s.dex = FakeDex()
    s.identifier = Identifier(s.dex)
    return s


def test_pipeline_finds_cheapest_good_listing(monkeypatch, tmp_path):
    s = make_scanner(monkeypatch)
    state = State(tmp_path / "state.json")
    deals = s.run(state, webhook=None, dry_run=True)
    assert len(deals) == 1
    d = deals[0]
    assert d.card.card_id == "M6-110"
    assert d.listing.item_id == "m2"
    assert d.profit.margin >= 0.35
    assert d.compared_listings == 3


def test_already_alerted_listing_is_skipped(monkeypatch, tmp_path):
    s = make_scanner(monkeypatch)
    state = State(tmp_path / "state.json")
    state.mark("m2")
    assert s.run(state, webhook=None, dry_run=True) == []


def test_discord_message_shape(monkeypatch, tmp_path):
    from scanner.discord import build_message

    s = make_scanner(monkeypatch)
    deal = s.run(State(tmp_path / "s.json"), webhook=None, dry_run=True)[0]
    msg = build_message(deal)
    embed = msg["embeds"][0]
    assert embed["url"] == "https://buyee.jp/mercari/item/m2"
    assert "Bénéfice net" in embed["description"]
    assert embed["image"]["url"].endswith("m2_1.jpg")
