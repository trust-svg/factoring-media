from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
import httpx
import logging
import config

logger = logging.getLogger(__name__)


@dataclass
class Item:
    platform: str
    external_id: str
    title: str
    price: int | None
    url: str
    image_url: str | None = None


@dataclass
class DetailedItem:
    """Extended item data from individual listing page."""
    platform: str
    url: str
    title: str
    price: int
    description: str
    condition: str
    image_urls: List[str]
    external_id: str = ""


class BaseScraper:
    platform: str = ""

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
        )

    async def search(self, keyword: str) -> List[Item]:
        raise NotImplementedError
