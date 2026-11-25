from scanner.identify import Identifier, find_number, find_rarities
from tests.fake_dex import FakeDex


def ident(title):
    m = Identifier(FakeDex()).identify(title)
    return m.card.card_id if m else None


def test_number_and_rarity_parsing():
    assert find_number("リザードンex SAR ２０１／１６５") == (201, 165)
    assert find_rarities("メガレックウザex SAR MEGA") == ["SAR"]
    assert "AR" not in find_rarities("ゲンガーex SAR")
    assert find_rarities("ピカチュウ AR 151") == ["AR"]


def test_identify_with_number():
    assert ident("リザードンex SAR SV2a ポケモンカード151 201/165") == "SV2a-201"
    assert ident("リザードンex 185/165 ポケカ151 sv2a") == "SV2a-185"


def test_identify_with_number_only_total():
    # Pas de nom de set, mais le total 165 et le nom suffisent.
    assert ident("ポケカ リザードンex 201/165 美品") == "SV2a-201"


def test_identify_with_rarity_and_set_name():
    assert ident("メガレックウザex SAR MEGA 拡張パック ストームエメラルダ") == "M6-110"
    assert ident("メガレックウザex MUR ストームエメラルダ") == "M6-113"


def test_identify_refuses_when_ambiguous():
    # Pas de numéro ni de rareté : plusieurs versions possibles, on ne devine pas.
    assert ident("メガレックウザex ストームエメラルダ") is None
    # Numéro incohérent avec le set.
    assert ident("リザードンex 201/999") is None
    # Carte inconnue.
    assert ident("ミュウツー SAR") is None
