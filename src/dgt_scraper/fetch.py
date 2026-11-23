"""Polite async HTTP access to revista.dgt.es."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final, Self

import httpx

__all__ = ["BASE_URL", "Fetcher", "RateLimiter", "exam_url", "page_candidates"]

_log: Final = logging.getLogger(__name__)

BASE_URL: Final = "https://revista.dgt.es"
INDEX_PATH: Final = "/es/test/index.shtml"
USER_AGENT: Final = (
    "dgt-scraper/0.1 (+https://github.com/algarfer/dgt-exam-scraper) python-httpx"
)

_TIMEOUT: Final = httpx.Timeout(30.0)
_MAX_ATTEMPTS: Final = 3
_RETRY_STATUS: Final = frozenset({408, 429, 500, 502, 503, 504})


def exam_url(number: int, *, pad: int = 0) -> str:
    """URL of one exam page."""
    return f"{BASE_URL}/es/test/Test-num-{number:0{pad}d}.shtml"


def page_candidates(number: int) -> list[str]:
    """Candidate URLs for an exam, most likely first.

    Every exam observed so far uses the plain unpadded number; the padded forms are
    a cheap fallback in case low numbers are spelled differently.
    """
    seen: dict[str, None] = {}
    for pad in (0, 2, 3):
        seen.setdefault(exam_url(number, pad=pad), None)
    return list(seen)


class RateLimiter:
    """Allows at most ``rate`` acquisitions per second, process wide."""

    def __init__(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._interval = 1.0 / rate
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = self._next_at
            self._next_at = now + self._interval


@dataclass(frozen=True, slots=True)
class Fetcher:
    """Rate-limited, retrying HTTP client with an on-disk cache for exam pages."""

    client: httpx.AsyncClient
    limiter: RateLimiter
    semaphore: asyncio.Semaphore
    cache_dir: Path
    force: bool = False

    @classmethod
    def create(
        cls,
        *,
        cache_dir: Path,
        rate: float = 4.0,
        concurrency: int = 4,
        force: bool = False,
    ) -> Self:
        client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        return cls(
            client=client,
            limiter=RateLimiter(rate),
            semaphore=asyncio.Semaphore(concurrency),
            cache_dir=cache_dir,
            force=force,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.client.aclose()

    async def _get(self, url: str) -> httpx.Response | None:
        """GET ``url``, retrying transient failures. ``None`` means 404."""
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            async with self.semaphore:
                await self.limiter.acquire()
                try:
                    response = await self.client.get(url)
                except (httpx.TimeoutException, httpx.TransportError) as error:
                    last_error = error
                else:
                    if response.status_code == 404:
                        return None
                    if response.status_code not in _RETRY_STATUS:
                        response.raise_for_status()
                        return response
                    last_error = httpx.HTTPStatusError(
                        f"{response.status_code} for {url}",
                        request=response.request,
                        response=response,
                    )
            if attempt < _MAX_ATTEMPTS:
                backoff = 2.0 ** (attempt - 1)
                _log.warning("retrying %s in %.1fs (%s)", url, backoff, last_error)
                await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error

    def _cache_path(self, number: int) -> Path:
        return self.cache_dir / f"Test-num-{number}.shtml"

    async def exam_page(self, number: int) -> tuple[bytes, str] | None:
        """HTML and resolved URL of an exam, or ``None`` if it does not exist.

        Cached pages are reused unless the fetcher was built with ``force``.
        """
        cached = self._cache_path(number)
        if cached.is_file() and not self.force:
            _log.debug("exam %s from cache", number)
            return cached.read_bytes(), exam_url(number)

        for url in page_candidates(number):
            response = await self._get(url)
            if response is None:
                continue
            content = response.content
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(content)
            return content, url
        return None

    async def image(self, url: str, destination: Path) -> bool:
        """Make sure ``url`` is downloaded to ``destination``.

        Returns whether the file is on disk afterwards, so a already-present image and
        a freshly downloaded one are both reported as available.
        """
        if destination.is_file() and not self.force:
            return True
        response = await self._get(url)
        if response is None:
            _log.warning("image not found: %s", url)
            return destination.is_file()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return True

    async def index_numbers(self) -> list[int]:
        """Exam numbers advertised on the test index page."""
        response = await self._get(f"{BASE_URL}{INDEX_PATH}")
        if response is None:
            return []
        found = re.findall(r"Test-num-(\d+)\.shtml", response.text)
        return sorted({int(number) for number in found})
