"""Filtres sur les annonces : lots, cartes gradées, état."""
from __future__ import annotations

import re
import unicodedata

from .models import Listing

CONDITION_LABELS = {
    1: "Neuf / non utilisé",
    2: "Quasi neuf",
    3: "Pas de rayures ni taches visibles",
    4: "Quelques rayures",
    5: "Rayures et taches",
    6: "Mauvais état",
}


def title_excluded(title: str, exclude_keywords: list[str]) -> bool:
    t = unicodedata.normalize("NFKC", title).upper()
    for kw in exclude_keywords:
        k = unicodedata.normalize("NFKC", kw).upper()
        if k.isascii():
            # Mot latin entier seulement : "ARS" ne doit pas exclure "STARS".
            if re.search(rf"(?<![A-Z]){re.escape(k)}(?![A-Z])", t):
                return True
        elif k in t:
            return True
    return False


def good_condition(listing: Listing, accepted: list[int]) -> bool:
    return listing.condition in accepted
