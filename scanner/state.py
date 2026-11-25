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
        if path.exists():
            try:
                self.alerted = json.loads(path.read_text()).get("alerted", {})
            except (json.JSONDecodeError, OSError):
                self.alerted = {}

    def already_alerted(self, item_id: str) -> bool:
        return item_id in self.alerted

    def mark(self, item_id: str) -> None:
        self.alerted[item_id] = time.time()

    def save(self) -> None:
        cutoff = time.time() - KEEP_DAYS * 86400
        self.alerted = {k: v for k, v in self.alerted.items() if v >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"alerted": self.alerted}, indent=1))
