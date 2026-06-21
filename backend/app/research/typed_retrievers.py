"""
Typed retrievers — authoritative version / release data for chat responses.

When the user asks about a software package's versions, releases, patches, or
changelog, the precise answer lives in a typed API (npm registry, PyPI, the
GitHub Releases API) rather than in any prose page. This module:

  1. Asks a small classifier LLM to read the user's question and decide
     which sources (if any) should be queried, with what package or repo
     name, and what version filter.
  2. Dispatches the chosen API calls in parallel.
  3. Returns the results as a single FACTS string the chat / research
     pipeline can hand to the response-generation LLM.

There is no curated list of package names or aliases here. The classifier
is responsible for understanding what the user is asking about — including
the mapping from how a human writes a name ("Next.js", "PyTorch") to the
registry id it lives under ("next", "torch").

Public surface:
    gather_facts(question)  → FactsResult(text, sources, reasoning)
    extract_version_date_map(facts_text) → {version: canonical_date}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import httpx

from ..llm_client import llm_chat

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 8.0
_MAX_VERSIONS = 25
_CLASSIFIER_TIMEOUT_S = 12
_CLASSIFIER_MAX_TOKENS = 400


# ─── Classifier ────────────────────────────────────────────────────────────


_CLASSIFIER_SYSTEM = """Decide whether the user's question needs authoritative version/release
data from a software registry. Output JSON only:

{
  "needs_facts": bool,
  "queries": [
    {
      "source": "npm" | "pypi" | "github_releases",
      "name": "<exact registry id, e.g. 'next', 'torch', 'vercel/next.js'>",
      "version_constraint": "<version prefix the user mentioned>" | null
    }
  ],
  "reasoning": "<one sentence>"
}

needs_facts is true only when the answer turns on specific versions,
release dates, patches, or changelog data. Multiple queries are allowed
(e.g. for comparisons).
"""


@dataclass
class _Query:
    source: str
    name: str
    version_constraint: Optional[str] = None


@dataclass
class FactsResult:
    """Outcome of running the typed-retriever layer."""
    text: str = ""
    sources: List[str] = field(default_factory=list)
    reasoning: str = ""

    @property
    def has_facts(self) -> bool:
        return bool(self.text)


def _extract_json_object(raw: str) -> Optional[dict]:
    """
    Best-effort JSON extraction from an LLM response.

    Strips markdown code fences, then grabs the substring from the first
    `{` to the last `}` and parses it. Returns None when no valid object
    can be recovered.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        logger.warning("Classifier returned malformed JSON: %s", e)
        return None


async def _classify(question: str) -> Tuple[List[_Query], str]:
    """
    Run the classifier LLM. Returns (queries, reasoning).

    On any failure (timeout, malformed output, unexpected schema) returns
    ([], "") so the caller degrades gracefully to no FACTS.
    """
    try:
        raw = await llm_chat(
            [
                {"role": "system", "content": _CLASSIFIER_SYSTEM},
                {"role": "user", "content": question},
            ],
            timeout_s=_CLASSIFIER_TIMEOUT_S,
            max_tokens=_CLASSIFIER_MAX_TOKENS,
        )
    except Exception as e:
        logger.warning("Classifier LLM call failed: %s", e)
        return [], ""

    parsed = _extract_json_object(raw)
    if not parsed:
        return [], ""

    reasoning = (parsed.get("reasoning") or "").strip()
    if not parsed.get("needs_facts"):
        return [], reasoning

    queries: List[_Query] = []
    for q in parsed.get("queries", []) or []:
        source = (q.get("source") or "").strip().lower()
        name = (q.get("name") or "").strip()
        constraint = q.get("version_constraint")
        if isinstance(constraint, str):
            constraint = constraint.strip() or None
        else:
            constraint = None
        if source not in {"npm", "pypi", "github_releases"} or not name:
            continue
        queries.append(
            _Query(source=source, name=name, version_constraint=constraint)
        )
    return queries, reasoning


# ─── Source dispatch ───────────────────────────────────────────────────────


def _filter_by_version(
    rows: List[Tuple[str, str]],
    version_prefix: Optional[str],
) -> List[Tuple[str, str]]:
    if not version_prefix:
        return rows
    pfx_dot = version_prefix + "."
    return [r for r in rows if r[0] == version_prefix or r[0].startswith(pfx_dot)]


def _format_table_block(
    *,
    source_label: str,
    source_url: str,
    name: str,
    rows: List[Tuple[str, str]],
    latest_global: str,
    version_constraint: Optional[str],
    header_left: str = "Version",
    header_right: str = "Release Date",
) -> str:
    table_rows = "\n".join(f"| {v} | {d} |" for v, d in rows)
    header = (
        f'[Authoritative version data — {source_label} "{name}"]\n'
        f"Source: {source_url}\n"
    )
    if version_constraint:
        header += (
            f"FILTERED to the {version_constraint}.x release series.\n"
            f"latest stable in this series: {rows[0][0]}\n"
            f"latest stable overall: {latest_global}\n"
            f"showing {len(rows)} most-recent releases in the "
            f"{version_constraint}.x series (newest first):\n\n"
        )
    else:
        header += (
            f"latest stable: {latest_global}\n"
            f"showing {len(rows)} most-recent stable releases "
            f"(newest first):\n\n"
        )
    return (
        header
        + f"| {header_left} | {header_right} |\n"
        + f"| :--- | :--- |\n"
        + table_rows
    )


async def _npm_fetch(client: httpx.AsyncClient, q: _Query) -> Optional[str]:
    try:
        r = await client.get(
            f"https://registry.npmjs.org/{q.name}", timeout=_HTTP_TIMEOUT
        )
    except httpx.RequestError as e:
        logger.warning("npm fetch failed for %s: %s", q.name, e)
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    times = data.get("time", {}) or {}
    stable: List[Tuple[str, str]] = []
    version_re = re.compile(r"^\d+\.\d+\.\d+$")
    for v, t in times.items():
        if version_re.match(v):
            stable.append((v, (t or "")[:10]))
    if not stable:
        return None
    stable.sort(key=lambda x: [int(p) for p in x[0].split(".")], reverse=True)
    filtered = _filter_by_version(stable, q.version_constraint)
    if q.version_constraint and not filtered:
        return None
    rows_to_show = filtered[:_MAX_VERSIONS]
    dist_tags = data.get("dist-tags", {}) or {}
    latest_global = dist_tags.get("latest", stable[0][0])
    return _format_table_block(
        source_label="npm package",
        source_url=f"https://registry.npmjs.org/{q.name}",
        name=q.name,
        rows=rows_to_show,
        latest_global=latest_global,
        version_constraint=q.version_constraint,
    )


async def _pypi_fetch(client: httpx.AsyncClient, q: _Query) -> Optional[str]:
    try:
        r = await client.get(
            f"https://pypi.org/pypi/{q.name}/json", timeout=_HTTP_TIMEOUT
        )
    except httpx.RequestError as e:
        logger.warning("pypi fetch failed for %s: %s", q.name, e)
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    releases = data.get("releases", {}) or {}
    version_re = re.compile(r"^\d+\.\d+(\.\d+)?$")
    raw: List[Tuple[str, str]] = []
    for v, files in releases.items():
        if not version_re.match(v) or not files:
            continue
        upload = files[0].get("upload_time", "")[:10]
        raw.append((v, upload))
    if not raw:
        return None

    def _key(item: Tuple[str, str]) -> List[int]:
        return [int(p) if p.isdigit() else 0 for p in item[0].split(".")]

    raw.sort(key=_key, reverse=True)
    filtered = _filter_by_version(raw, q.version_constraint)
    if q.version_constraint and not filtered:
        return None
    rows_to_show = filtered[:_MAX_VERSIONS]
    latest_global = data.get("info", {}).get("version", raw[0][0])
    return _format_table_block(
        source_label="PyPI package",
        source_url=f"https://pypi.org/pypi/{q.name}/json",
        name=q.name,
        rows=rows_to_show,
        latest_global=latest_global,
        version_constraint=q.version_constraint,
    )


async def _github_releases_fetch(
    client: httpx.AsyncClient, q: _Query
) -> Optional[str]:
    if "/" not in q.name:
        return None
    owner, _, repo = q.name.partition("/")
    if not owner or not repo:
        return None
    try:
        r = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases",
            params={"per_page": _MAX_VERSIONS},
            timeout=_HTTP_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except httpx.RequestError as e:
        logger.warning("github fetch failed for %s: %s", q.name, e)
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, list) or not data:
        return None
    rows = []
    for rel in data[:_MAX_VERSIONS]:
        tag = rel.get("tag_name", "")
        published = (rel.get("published_at", "") or "")[:10]
        rows.append(f"| {tag} | {published} |")
    return (
        f'[Authoritative release data — GitHub repository "{owner}/{repo}"]\n'
        f"Source: https://api.github.com/repos/{owner}/{repo}/releases\n"
        f"recent {len(rows)} releases (newest first):\n\n"
        f"| Tag | Published |\n"
        f"| :--- | :--- |\n"
        + "\n".join(rows)
    )


_DISPATCH = {
    "npm": _npm_fetch,
    "pypi": _pypi_fetch,
    "github_releases": _github_releases_fetch,
}


# ─── Public API ────────────────────────────────────────────────────────────


async def gather_facts(question: str) -> FactsResult:
    """
    Classify the user's question, then fetch from the chosen sources in
    parallel. Returns a `FactsResult` whose `text` is empty when the
    classifier decided no facts were needed (or when every fetch failed).
    """
    queries, reasoning = await _classify(question)
    if not queries:
        return FactsResult(text="", sources=[], reasoning=reasoning)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_DISPATCH[q.source](client, q) for q in queries),
            return_exceptions=True,
        )

    blocks: List[str] = []
    used: List[str] = []
    for q, res in zip(queries, results):
        if isinstance(res, Exception):
            logger.warning("retriever %s/%s raised: %s", q.source, q.name, res)
            continue
        if res:
            blocks.append(res)
            used.append(f"{q.source}:{q.name}")
    return FactsResult(
        text="\n\n".join(blocks),
        sources=used,
        reasoning=reasoning,
    )
