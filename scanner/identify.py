"""Identification d'une carte à partir du titre japonais d'une annonce."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from .models import Card
from .tcgdex import TcgDex

# Abréviations de rareté utilisées sur Mercari -> libellés TCGdex.
RARITY_MAP: dict[str, set[str]] = {
    "SAR": {"special illustration rare"},
    "AR": {"illustration rare"},
    "SR": {"ultra rare", "secret rare"},
    "UR": {"hyper rare", "secret rare"},
    "HR": {"hyper rare"},
    "MUR": {"mega hyper rare"},
    "RRR": {"triple rare"},
    "RR": {"double rare"},
    "CHR": {"character rare"},
    "CSR": {"character super rare"},
    "SSR": {"shiny ultra rare"},
    "ACE": {"ace spec rare"},
    "BWR": {"black white rare"},
}

NUMBER_RE = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{2,3})(?!\d)")
SET_CODE_RE = re.compile(r"(?<![a-z0-9])((?:sv|sm|s|m)\d{1,2}[a-z]{0,2})(?![a-z0-9])", re.I)


def normalize(text: str) -> str:
    """Pleine chasse -> ASCII, minuscules, espaces simplifiés."""
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def find_rarities(title: str) -> list[str]:
    t = unicodedata.normalize("NFKC", title).upper()
    found = []
    # Les plus longues d'abord pour que "SAR" ne soit pas lu comme "AR".
    for code in sorted(RARITY_MAP, key=len, reverse=True):
        if re.search(rf"(?<![A-Z]){code}(?![A-Z])", t):
            found.append(code)
    return found


def find_number(title: str) -> Optional[tuple[int, int]]:
    m = NUMBER_RE.search(normalize(title))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


@dataclass
class Match:
    card: Card
    reason: str


class Identifier:
    def __init__(self, dex: TcgDex):
        self.dex = dex

    def _candidate_sets(self, title_n: str, number: Optional[tuple[int, int]]) -> list[dict]:
        sets = self.dex.sets()
        by_code = {s["id"].lower(): s for s in sets}
        found: list[dict] = []
        for code in SET_CODE_RE.findall(title_n):
            s = by_code.get(code.lower())
            if s and s not in found:
                found.append(s)
        named = [s for s in sets if len(normalize(s["name"])) >= 3 and normalize(s["name"]) in title_n]
        named.sort(key=lambda s: len(s["name"]), reverse=True)
        for s in named[:2]:
            if s not in found:
                found.append(s)
        if not found and number:
            found = [s for s in sets if (s.get("cardCount") or {}).get("official") == number[1]]
        return found

    def identify(self, title: str) -> Optional[Match]:
        title_n = normalize(title)
        number = find_number(title)
        rarities = find_rarities(title)
        matched: list[dict] = []

        for s in self._candidate_sets(title_n, number):
            detail = self.dex.set_detail(s["id"])
            official = (detail.get("cardCount") or {}).get("official")
            if number and official and number[1] != official:
                continue
            for c in detail.get("cards", []):
                name_n = normalize(c.get("name", ""))
                if not name_n or name_n not in title_n:
                    continue
                if number:
                    if not c.get("localId", "").isdigit() or int(c["localId"]) != number[0]:
                        continue
                matched.append(c)

        # "レックウザ" est contenu dans "メガレックウザex" : on garde le nom le plus précis.
        names = {normalize(c["name"]) for c in matched}
        matched = [c for c in matched
                   if not any(normalize(c["name"]) != n and normalize(c["name"]) in n for n in names)]
        candidates: list[Card] = [self.dex.card(c["id"]) for c in matched]

        if not candidates:
            return None
        if number:
            # Nom + numéro + set : identification sûre.
            if len(candidates) == 1:
                return Match(candidates[0], "nom + numéro + set")
            return None

        # Sans numéro : il faut la rareté pour départager.
        if rarities:
            wanted = set().union(*(RARITY_MAP[r] for r in rarities))
            candidates = [c for c in candidates if c.rarity.lower() in wanted]
        if len(candidates) == 1 and rarities:
            return Match(candidates[0], "nom + rareté + set")
        return None
