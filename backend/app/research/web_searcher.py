import asyncio
import logging
from typing import Any, Dict, List

from ddgs import DDGS

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT_S = 15


def _ddgs_search_sync(query: str, max_results: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    return results


async def search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search DuckDuckGo for a query string.

    Returns a list of {title, url, snippet} dicts. A 0.5s delay is applied
    before each call to stay below DuckDuckGo's informal rate limit. The
    blocking DDGS call is offloaded to a thread and bounded by SEARCH_TIMEOUT_S.
    """
    await asyncio.sleep(0.5)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_ddgs_search_sync, query, max_results),
            timeout=SEARCH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("DuckDuckGo search timed out after %ds for query '%s'", SEARCH_TIMEOUT_S, query)
        return []
    except Exception as e:
        logger.warning("DuckDuckGo search failed for query '%s': %s", query, e)
        return []


def deduplicate(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate results by URL."""
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)
    return unique
