"""Mémoire entre deux passages : annonces déjà envoyées, pour ne pas répéter les alertes."""
from __future__ import annotations

import json
import time
from pathlib import Path

KEEP_DAYS = 30


class State:
    def __init__(self, path: Path):
        self.path = path
        self.alerted: dict[str, float] = {}
        # Position dans la liste des cartes demandées (pour les parcourir toutes au fil des passages).
        self.demand_cursor: int = 0
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self.alerted = data.get("alerted", {})
                self.demand_cursor = int(data.get("demand_cursor", 0))
            except (json.JSONDecodeError, OSError, ValueError):
                self.alerted = {}

    def already_alerted(self, item_id: str) -> bool:
        return item_id in self.alerted

    def mark(self, item_id: str) -> None:
        self.alerted[item_id] = time.time()

    def save(self) -> None:
        cutoff = time.time() - KEEP_DAYS * 86400
        self.alerted = {k: v for k, v in self.alerted.items() if v >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"alerted": self.alerted, "demand_cursor": self.demand_cursor}, indent=1))
