from pathlib import Path

from scanner.buyee import parse_item, parse_search

FIX = Path(__file__).parent / "fixtures"


def test_parse_search():
    items = parse_search((FIX / "mercari_search.html").read_text())
    assert len(items) == 2
    first = items[0]
    assert first.item_id == "m70648894482"
    assert first.url == "https://buyee.jp/mercari/item/m70648894482"
    assert first.price_jpy == 50000
    assert first.title == "リザードンex SAR SV2a ポケモンカード151 201/165"
    assert abs(first.eur_per_jpy - 305 / 50000) < 1e-9
    assert first.thumbnail.startswith("https://static.mercdn.net/")


def test_parse_item():
    listing = parse_search((FIX / "mercari_search.html").read_text())[1]
    listing = parse_item((FIX / "mercari_item.html").read_text(), listing)
    assert listing.condition == 1
    assert listing.seller_pays_shipping is True
    assert listing.available is True
    assert listing.price_jpy == 25000
    assert len(listing.photos) == 3
    assert all("/item/detail/hq/photos/" in p for p in listing.photos)


def test_parse_item_sold_out():
    html = (FIX / "mercari_item.html").read_text().replace("g-button--mercari enable", "g-button--mercari disable")
    listing = parse_search((FIX / "mercari_search.html").read_text())[1]
    assert parse_item(html, listing).available is False
