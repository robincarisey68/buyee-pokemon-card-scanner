from scanner.filters import title_excluded
from scanner.models import Listing
from scanner.profit import compute_profit, max_price_jpy_for_margin

COSTS = {"buyee_service_fee_jpy": 300, "domestic_shipping_jpy": 750,
         "international_shipping_per_card_jpy": 1500, "eu_flat_duty_eur": 3.0,
         "import_vat_rate": 0.20, "import_handling_eur": 0.0}
RESALE = {"marketplace_fee_rate": 0.05, "shipping_to_buyer_eur": 2.0}
RATE = 0.0061


def listing(price, seller_pays=True):
    return Listing(item_id="m1", url="u", title="t", price_jpy=price, seller_pays_shipping=seller_pays)


def test_profit_breakdown():
    p = compute_profit(listing(10000), 150.0, COSTS, RESALE, RATE)
    # 10 000 ¥ = 61 € ; Buyee 1,83 ; port intl 9,15 ; taxe 3 ; TVA 20 % de (61 + 9,15 + 3)
    assert p.purchase_eur == 61.0
    assert p.domestic_shipping_eur == 0.0
    assert p.vat_eur == round((61 + 9.15 + 3) * 0.2, 2)
    assert p.net_revenue_eur == round(150 * 0.95 - 2, 2)
    assert abs(p.total_cost_eur - (61 + 1.83 + 9.15 + 3 + p.vat_eur)) < 0.02
    assert p.profit_eur == round(p.net_revenue_eur - p.total_cost_eur, 2)


def test_buyer_pays_domestic_shipping():
    p = compute_profit(listing(10000, seller_pays=False), 150.0, COSTS, RESALE, RATE)
    assert p.domestic_shipping_eur == round(750 * RATE, 2)


def test_max_price_matches_margin():
    limit = max_price_jpy_for_margin(150.0, 0.35, COSTS, RESALE, RATE)
    at_limit = compute_profit(listing(limit), 150.0, COSTS, RESALE, RATE)
    above = compute_profit(listing(limit + 200), 150.0, COSTS, RESALE, RATE)
    assert at_limit.margin >= 0.35 - 0.001
    assert above.margin < 0.35


def test_title_exclusions():
    kws = ["まとめ", "PSA", "ARS", "BOX"]
    assert title_excluded("リザードンex PSA10", kws)
    assert title_excluded("ポケカ まとめ売り", kws)
    assert not title_excluded("STARS ピカチュウ", kws)
    assert not title_excluded("リザードンex SAR 201/165", kws)
