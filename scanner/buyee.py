"""Lecture des pages Buyee (Mercari) : recherche et page d'annonce."""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .http import Http
from .models import Listing

BASE = "https://buyee.jp"
SEARCH_URL = BASE + "/mercari/search"
ITEM_ID_RE = re.compile(r"/mercari/item/(m?\d+)")
EUR_RE = re.compile(r"€\s*([\d,]+(?:\.\d+)?)")
SELLER_WORDS = {"vendeur", "seller", "出品者", "送料込み"}


def _to_int(text: str) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _abs(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urljoin(BASE, url)


def parse_search(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    seen: set[str] = set()
    for li in soup.select("li.list"):
        a = li.find("a", href=ITEM_ID_RE)
        if not a:
            continue
        m = ITEM_ID_RE.search(a["href"])
        item_id = m.group(1)
        if item_id in seen:
            continue
        seen.add(item_id)
        name_el = li.select_one(".name")
        price_el = li.select_one(".price")
        price = _to_int(price_el.get_text()) if price_el else None
        if not name_el or not price:
            continue
        eur_per_jpy = None
        fx_el = li.select_one(".price-fx")
        if fx_el:
            fm = EUR_RE.search(fx_el.get_text())
            if fm:
                eur = float(fm.group(1).replace(",", ""))
                eur_per_jpy = eur / price if price else None
        img = li.select_one("img.thumbnail")
        listings.append(
            Listing(
                item_id=item_id,
                url=f"{BASE}/mercari/item/{item_id}",
                title=name_el.get_text(" ", strip=True),
                price_jpy=price,
                thumbnail=_abs(img.get("src", "")) if img else "",
                eur_per_jpy=eur_per_jpy,
            )
        )
    return listings


def parse_item(html: str, listing: Listing) -> Listing:
    """Complète une annonce avec l'état, le port Japon, les photos et la disponibilité."""
    soup = BeautifulSoup(html, "html.parser")

    # Titre complet et prix à jour (JSON-LD, indépendant de la langue).
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            listing.title = data.get("name") or listing.title
            offer = data.get("offers") or {}
            if isinstance(offer, dict) and offer.get("price"):
                listing.price_jpy = int(float(offer["price"]))

    table = soup.select_one("dl.m-goodsTable")
    if table:
        cond_link = table.find("a", href=re.compile(r"condition=\d"))
        if cond_link:
            qs = parse_qs(urlparse(cond_link["href"]).query)
            listing.condition = int(qs["condition"][0])
        for dt in table.find_all("dt"):
            label = dt.get_text(" ", strip=True).lower()
            if "port" in label or "shipping" in label or "送料" in label:
                dd = dt.find_next_sibling("dd")
                if dd:
                    value = dd.get_text(" ", strip=True).lower()
                    listing.seller_pays_shipping = any(w in value for w in SELLER_WORDS)
                break

    photos: list[str] = []
    for img in soup.find_all("img"):
        for attr in ("data-src", "src"):
            src = img.get(attr) or ""
            if "/item/detail/" in src and src not in photos:
                photos.append(_abs(src))
    listing.photos = photos

    button = soup.select_one(".m-goodsButton button, button.g-button--mercari")
    if button is not None:
        listing.available = "enable" in (button.get("class") or [])
    return listing


class Buyee:
    def __init__(self, http: Http):
        self.http = http
        self.failures = 0

    def search(self, keyword: str, pages: int, condition: Optional[int] = None) -> list[Listing]:
        results: list[Listing] = []
        seen: set[str] = set()
        for page in range(1, pages + 1):
            params = {"keyword": keyword, "page": page}
            if condition:
                params["condition"] = condition
            resp = self.http.get_polite(SEARCH_URL, params=params)
            if resp.status_code != 200:
                print(f"  [buyee] « {keyword} » page {page} : HTTP {resp.status_code} ({len(resp.text)} octets)")
                self.failures += 1
                break
            parsed = parse_search(resp.text)
            page_items = [l for l in parsed if l.item_id not in seen]
            if not page_items:
                if page == 1 and not parsed:
                    title = re.search(r"<title>(.*?)</title>", resp.text, re.S)
                    print(f"  [buyee] « {keyword} » : aucune annonce lue (page « {title.group(1).strip()[:80] if title else '?'} », "
                          f"{len(resp.text)} octets, url {resp.url})")
                    body = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
                    print(f"  [buyee] début de la page : {body[:300]}")
                break
            for item in page_items:
                seen.add(item.item_id)
            results.extend(page_items)
        return results

    def load_item(self, listing: Listing) -> Listing:
        resp = self.http.get_polite(listing.url)
        if resp.status_code != 200:
            listing.available = False
            return listing
        return parse_item(resp.text, listing)
