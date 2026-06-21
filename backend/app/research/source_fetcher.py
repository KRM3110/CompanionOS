"""
Source fetcher — pulls main article text from search-result URLs.

Web-search APIs return short snippets (typically 100–250 characters). That
isn't enough context for the report builder to write grounded, specific
prose. This module concurrently fetches each top-ranked result URL, strips
boilerplate with trafilatura, and attaches the cleaned main text to the
result dict as a new `body` field.

The original `snippet` is left in place as a fallback: if a page fails to
fetch, returns non-HTML content, or trafilatura can't isolate the main
text, the report builder falls back to the snippet for that source.

Per-source text is truncated to `MAX_BODY_CHARS` so a single long page
can't dominate the model's context window and crowd out other sources.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 8.0
MAX_BODY_CHARS = 3500
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 CompanionOS-Research/1"
)

# Domains whose pages don't yield extractable article text — fetching them
# wastes the request budget. Video pages and social posts go here.
_SKIP_DOMAINS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "twitter.com", "x.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
}


def _skip(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return True
    return host.lower() in _SKIP_DOMAINS


def _extract_main_text(html: str, url: str) -> str:
    """
    Pull the article body out of a raw HTML page.

    Uses trafilatura when installed (the quality fallback). When trafilatura
    is unavailable or fails on a particular page, falls back to a regex tag
    strip — lossier but always returns something.
    """
    if _HAS_TRAFILATURA:
        try:
            text = trafilatura.extract(
                html,
                url=url,
                favor_recall=False,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            if text:
                return text.strip()
        except Exception as e:
            logger.debug("trafilatura failed on %s: %s", url, e)
    # Fallback when trafilatura is missing or returned nothing: strip script
    # and style blocks then drop remaining tags.
    import re
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _fetch_one(client: httpx.AsyncClient, result: Dict[str, Any]) -> Dict[str, Any]:
    url = result.get("url", "")
    enriched = dict(result)
    enriched["body"] = ""
    enriched["fetched"] = False
    if not url or _skip(url):
        return enriched
    try:
        r = await client.get(url, timeout=FETCH_TIMEOUT_S)
    except httpx.RequestError as e:
        logger.debug("fetch failed %s: %s", url, e)
        return enriched
    if r.status_code != 200 or "text/html" not in r.headers.get("content-type", "").lower():
        return enriched
    text = _extract_main_text(r.text, url)
    if not text:
        return enriched
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + " …[truncated]"
    enriched["body"] = text
    enriched["fetched"] = True
    return enriched


async def enrich_sources(
    results: List[Dict[str, Any]],
    max_concurrent: int = 6,
    max_to_fetch: int = 10,
) -> List[Dict[str, Any]]:
    """
    Fetch main text for the first `max_to_fetch` results and attach it as
    a new `body` field on each.

    Concurrency is bounded by `max_concurrent` to be polite to origin
    servers. Results beyond `max_to_fetch` are returned unmodified so they
    still appear in the source list, but without a fetched body. Per-page
    failures (timeouts, non-200, non-HTML, extraction misses) are silent;
    the caller can detect them via the `fetched` boolean on each item.
    """
    if not results:
        return results
    to_fetch = results[:max_to_fetch]
    rest = results[max_to_fetch:]

    sem = asyncio.Semaphore(max_concurrent)

    async def _bounded(client, r):
        async with sem:
            return await _fetch_one(client, r)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=FETCH_TIMEOUT_S,
    ) as client:
        enriched = await asyncio.gather(*(_bounded(client, r) for r in to_fetch))
    return list(enriched) + rest
