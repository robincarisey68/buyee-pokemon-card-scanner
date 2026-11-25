"""Catalogue TCGdex réduit, reproduit à partir de vraies réponses de l'API (25/11/2026)."""
from scanner.tcgdex import card_from_raw

SETS = [
    {"id": "SV2a", "name": "ポケモンカード151", "cardCount": {"official": 165, "total": 210}},
    {"id": "M6", "name": "ストームエメラルダ", "cardCount": {"official": 76, "total": 113}},
    {"id": "SV10", "name": "ロケット団の栄光", "cardCount": {"official": 98, "total": 132}},
]

def _cm(trend, avg7, avg30, pid):
    return {"pricing": {"cardmarket": {"trend": trend, "avg7": avg7, "avg30": avg30, "avg1": trend,
                                         "low": trend * 0.7, "idProduct": pid, "updated": "2026-11-25"}}}

CARDS = {
    "SV2a-201": {"id": "SV2a-201", "localId": "201", "name": "リザードンex", "rarity": "Special illustration rare",
                 "image": "https://assets.tcgdex.net/ja/SV/SV2a/201",
                 "set": {"id": "SV2a", "name": "ポケモンカード151", "cardCount": {"official": 165}},
                 **_cm(297.54, 300.0, 353.78, 719654)},
    "SV2a-185": {"id": "SV2a-185", "localId": "185", "name": "リザードンex", "rarity": "Ultra Rare",
                 "set": {"id": "SV2a", "name": "ポケモンカード151", "cardCount": {"official": 165}},
                 **_cm(20.13, 21.0, 20.01, 1)},
    "M6-058": {"id": "M6-058", "localId": "058", "name": "メガレックウザex", "rarity": "Double rare",
               "set": {"id": "M6", "name": "ストームエメラルダ", "cardCount": {"official": 76}}, **_cm(1.06, 1.1, 1.33, 2)},
    "M6-095": {"id": "M6-095", "localId": "095", "name": "メガレックウザex", "rarity": "Ultra Rare",
               "set": {"id": "M6", "name": "ストームエメラルダ", "cardCount": {"official": 76}}, **_cm(21.44, 22.0, 24.43, 3)},
    "M6-110": {"id": "M6-110", "localId": "110", "name": "メガレックウザex", "rarity": "Special illustration rare",
               "set": {"id": "M6", "name": "ストームエメラルダ", "cardCount": {"official": 76}}, **_cm(221.06, 210.0, 188.38, 4)},
    "M6-113": {"id": "M6-113", "localId": "113", "name": "メガレックウザex", "rarity": "Mega Hyper Rare",
               "set": {"id": "M6", "name": "ストームエメラルダ", "cardCount": {"official": 76}}, **_cm(350.04, 381.16, 419.83, 900146)},
}

SET_CARDS = {
    "SV2a": {"id": "SV2a", "cardCount": {"official": 165},
             "cards": [{"id": k, "localId": v["localId"], "name": v["name"]} for k, v in CARDS.items() if k.startswith("SV2a")]
             + [{"id": "SV2a-025", "localId": "025", "name": "ピカチュウ"}]},
    "M6": {"id": "M6", "cardCount": {"official": 76},
           "cards": [{"id": k, "localId": v["localId"], "name": v["name"]} for k, v in CARDS.items() if k.startswith("M6")]
           + [{"id": "M6-050", "localId": "050", "name": "レックウザ"}]},
    "SV10": {"id": "SV10", "cardCount": {"official": 98}, "cards": []},
}


class FakeDex:
    def sets(self):
        return SETS

    def set_detail(self, set_id):
        return SET_CARDS[set_id]

    def card(self, card_id):
        return card_from_raw(CARDS[card_id])
