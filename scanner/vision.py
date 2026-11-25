"""Vérification des photos par Claude Haiku : bonne carte ? défauts visibles ?"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from .models import Card, Listing

MODEL = "claude-haiku-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "same_card": {"type": "boolean"},
        "number_seen": {"type": "string"},
        "single_card": {"type": "boolean"},
        "defects": {"type": "array", "items": {"type": "string"}},
        "condition_ok": {"type": "boolean"},
        "note_fr": {"type": "string"},
    },
    "required": ["same_card", "number_seen", "single_card", "defects", "condition_ok", "note_fr"],
    "additionalProperties": False,
}

PROMPT = """Tu vérifies une annonce Mercari d'une carte Pokémon japonaise avant un achat pour revente.
Carte attendue : {name} — set « {set_name} » ({set_id}), numéro {number}, rareté {rarity}.
La première image est la carte de référence. Les suivantes sont les photos de l'annonce.

Réponds en JSON :
- same_card : les photos montrent bien cette carte exacte (même illustration, même numéro, version japonaise) ?
- number_seen : le numéro lisible sur la photo (ex. "201/165"), ou "" s'il est illisible.
- single_card : l'annonce vend une seule carte (pas un lot) ?
- defects : défauts visibles (coins blanchis, rayures, pli, bords abîmés, centrage très décalé). Liste vide si aucun.
- condition_ok : la carte paraît en bon état, revendable comme « Near Mint » ou « Excellent » ?
- note_fr : une phrase courte en français pour l'acheteur."""


@dataclass
class VisionResult:
    same_card: bool
    condition_ok: bool
    single_card: bool
    note: str


class VisionChecker:
    def __init__(self, enabled: bool, max_checks: int):
        self.enabled = enabled and bool(os.environ.get("ANTHROPIC_API_KEY"))
        self.remaining = max_checks
        self._client = None
        if self.enabled:
            import anthropic

            self._client = anthropic.Anthropic()

    def check(self, card: Card, listing: Listing) -> Optional[VisionResult]:
        """Renvoie None si la vérification est désactivée ou impossible."""
        if not self.enabled or self.remaining <= 0 or not listing.photos:
            return None
        self.remaining -= 1
        content: list[dict] = []
        if card.image:
            content.append({"type": "image", "source": {"type": "url", "url": card.image}})
        for url in listing.photos[:3]:
            content.append({"type": "image", "source": {"type": "url", "url": url}})
        content.append({"type": "text", "text": PROMPT.format(
            name=card.name, set_name=card.set_name, set_id=card.set_id,
            number=card.number_label, rarity=card.rarity or "inconnue")})
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=2000,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": content}],
            )
        except Exception as exc:  # une erreur d'IA ne doit pas bloquer le scan
            print(f"  [vision] erreur : {exc}")
            return None
        if response.stop_reason != "end_turn":
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        note = data.get("note_fr", "")
        if data.get("defects"):
            note = f"{note} Défauts vus : {', '.join(data['defects'])}."
        return VisionResult(
            same_card=bool(data.get("same_card")),
            condition_ok=bool(data.get("condition_ok")),
            single_card=bool(data.get("single_card")),
            note=note.strip(),
        )
