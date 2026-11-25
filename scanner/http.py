from __future__ import annotations

import random
import time
from typing import Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class Http:
    """Session HTTP partagée, avec une pause aléatoire entre deux pages Buyee."""

    def __init__(self, delay_range: tuple[float, float] = (3, 6), timeout: float = 30):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}
        )
        self.delay_range = delay_range
        self.timeout = timeout
        self._last_polite: float = 0.0

    def get_polite(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """GET vers Buyee, en respectant une pause entre deux requêtes."""
        wait = random.uniform(*self.delay_range) - (time.monotonic() - self._last_polite)
        if wait > 0 and self._last_polite:
            time.sleep(wait)
        try:
            return self._get(url, params)
        finally:
            self._last_polite = time.monotonic()

    def get_json(self, url: str, params: Optional[dict] = None):
        resp = self._get(url, params)
        resp.raise_for_status()
        return resp.json()

    def _get(self, url: str, params: Optional[dict]) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(5 * (attempt + 1))
                    continue
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(5 * (attempt + 1))
        if last_exc:
            raise last_exc
        return resp  # type: ignore[possibly-undefined]
