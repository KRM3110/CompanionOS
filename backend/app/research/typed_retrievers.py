"""
Typed retrievers — authoritative structured data for version/release questions.

When a research question names a package or repository and asks about
versions, releases, or changelogs, the canonical answer lives in a typed API
(npm registry, PyPI, GitHub releases) rather than in any prose page. These
retrievers query those APIs directly and return a markdown table ready to
embed under the report's "Key Findings" heading. The result is used as the
authoritative `FACTS` block by the report builder.

Each retriever exposes two methods:
    matches(question)      — cheap pattern check; True when this retriever
                             is potentially applicable.
    async fetch(question)  — runs the API call. Returns a structured text
                             block or None.

`gather_facts(question)` runs every matching retriever concurrently and
returns one concatenated FACTS string (or "" if nothing matched / fetched).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional, Protocol, Tuple

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 8.0
_MAX_VERSIONS = 25


# Words that, when present in a question, signal the user wants version /
# release / changelog data rather than analytical prose. Used as a gate so we
# don't waste registry calls on "What does Next.js do?" type questions.
_VERSION_INTENT_RE = re.compile(
    r"\b(version|versions|release|releases|patch|patches|changelog|update|"
    r"updates|latest|recent|history)\b",
    re.IGNORECASE,
)

# Curated allow-list of well-known npm package names.
#
# Why curated rather than "any word":
#   Many real npm package ids are also common English words ("next",
#   "react", "vue", "express"). A naive "any token" pattern would match
#   half the words in any sentence and produce noisy false-positive
#   registry calls. The allow-list captures the high-traffic cases
#   cleanly; everything else flows through `_GenericNpmRetriever` below,
#   which does a more conservative extraction and tolerates 404s.
_KNOWN_NPM_PKGS = re.compile(
    r"\b(next\.?js|next|react|vite|typescript|express|webpack|tailwindcss|"
    r"tailwind|svelte|vue|nuxt|angular|astro|remix|eslint|prettier|jest|"
    r"vitest|playwright|puppeteer|axios|redux|zustand|@?[\w-]+/[\w-]+)\b",
    re.IGNORECASE,
)

# Same idea for PyPI — popular packages whose ids are common English words
# get the allow-list; unknown packages flow through the generic path.
_KNOWN_PYPI_PKGS = re.compile(
    r"\b(fastapi|django|flask|requests|httpx|pydantic|sqlalchemy|numpy|"
    r"pandas|scipy|scikit-?learn|pytorch|tensorflow|transformers|langchain|"
    r"openai|anthropic|uvicorn|alembic|aiosqlite|chromadb|pytest|black|"
    r"ruff|mypy)\b",
    re.IGNORECASE,
)

# Matches GitHub-style "owner/repo" tokens. Excludes leading-dot strings so
# that filenames like ".github/workflows" don't accidentally match.
_GITHUB_REPO_RE = re.compile(r"\b([a-zA-Z0-9_-][a-zA-Z0-9._-]*)/([a-zA-Z0-9._-]+)\b")


# Map between aliases users type and the canonical npm/PyPI package id.
# Add new entries whenever you find a name that users say differently than
# the registry stores it.
_PKG_NAME_ALIASES = {
    "nextjs": "next",
    "next.js": "next",
    "scikit-learn": "scikit-learn",
    "scikitlearn": "scikit-learn",
    "pytorch": "torch",
    "tailwindcss": "tailwindcss",
    "tailwind": "tailwindcss",
}

# Map between an npm/PyPI id and the human-readable name users say. Used in
# the FACTS block label so the LLM bridges, e.g., "next" → "Next.js" when
# the question phrases it as "Next.js".
_PKG_DISPLAY_NAMES = {
    "next": "Next.js",
    "react": "React",
    "vue": "Vue.js",
    "nuxt": "Nuxt",
    "svelte": "Svelte",
    "astro": "Astro",
    "remix": "Remix",
    "angular": "Angular",
    "vite": "Vite",
    "webpack": "Webpack",
    "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS",
    "eslint": "ESLint",
    "prettier": "Prettier",
    "jest": "Jest",
    "vitest": "Vitest",
    "playwright": "Playwright",
    "puppeteer": "Puppeteer",
    "axios": "Axios",
    "express": "Express",
    "redux": "Redux",
    "zustand": "Zustand",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "requests": "Requests",
    "httpx": "HTTPX",
    "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy",
    "numpy": "NumPy",
    "pandas": "pandas",
    "scipy": "SciPy",
    "scikit-learn": "scikit-learn",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "transformers": "Transformers (Hugging Face)",
    "langchain": "LangChain",
    "openai": "OpenAI Python SDK",
    "anthropic": "Anthropic Python SDK",
}


def _canonical(name: str) -> str:
    """Map a user-typed name to its canonical registry id."""
    n = name.lower().strip()
    return _PKG_NAME_ALIASES.get(n, n)


def _display_name(pkg: str) -> str:
    """Map a registry id to the human-readable name (or echo the id)."""
    return _PKG_DISPLAY_NAMES.get(pkg, pkg)


def _version_filter(question: str, pkg: str) -> Optional[str]:
    """
    Detect a version hint that scopes the question to a specific major series.

    Examples: "Next.js 14"  → '14'
              "React 18.2"  → '18.2'
              "FastAPI"     → None  (no version mentioned)

    The returned string is used by retrievers as a `startswith` prefix so
    they only surface rows from the requested series instead of dumping the
    package's latest 25 releases regardless of which major the user asked
    about.
    """
    display = _display_name(pkg).lower()
    names = {
        pkg.lower(),
        display,
        display.replace(".", ""),
        display.replace(" ", ""),
    }
    names = {n for n in names if n}
    if not names:
        return None
    name_alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    pattern = (
        rf"\b(?:{name_alt})[\s.\-:]*(?:v|version\s+)?(\d+(?:\.\d+)?)"
    )
    m = re.search(pattern, question, re.IGNORECASE)
    return m.group(1) if m else None


def _filter_by_version(
    rows: List[Tuple[str, str]],
    version_prefix: Optional[str],
) -> List[Tuple[str, str]]:
    """Keep rows whose version equals `<prefix>` or starts with `<prefix>.`."""
    if not version_prefix:
        return rows
    pfx_dot = version_prefix + "."
    return [r for r in rows if r[0] == version_prefix or r[0].startswith(pfx_dot)]


def _format_table_block(
    *,
    source_label: str,
    source_url: str,
    pkg: str,
    display: str,
    rows: List[Tuple[str, str]],
    latest_global: str,
    version_filter: Optional[str],
    header_left: str = "Version",
    header_right: str = "Release Date",
) -> str:
    """Assemble the FACTS block header + markdown table."""
    table_rows = "\n".join(f"| {v} | {d} |" for v, d in rows)
    header = (
        f'[Authoritative version data — {source_label} package '
        f'"{pkg}" ({display})]\n'
        f"Source: {source_url}\n"
    )
    if version_filter:
        header += (
            f"FILTERED to the {version_filter}.x release series "
            f"(question asks about version {version_filter}).\n"
            f"latest stable in this series: {rows[0][0]}\n"
            f"latest stable overall: {latest_global}\n"
            f"showing {len(rows)} most-recent releases in the "
            f"{version_filter}.x series (newest first):\n\n"
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


# ─── Retrievers ────────────────────────────────────────────────────────────


class Retriever(Protocol):
    """A typed source of authoritative facts for a given question shape."""

    name: str

    def matches(self, question: str) -> bool: ...
    async def fetch(
        self, client: httpx.AsyncClient, question: str
    ) -> Optional[str]: ...


class NpmRetriever:
    """
    Fetches version+date data from the npm registry for well-known packages.

    The match is gated on the known-packages allow-list (see `_KNOWN_NPM_PKGS`)
    to avoid false-positive lookups on common English words.
    """

    name = "npm"

    def matches(self, question: str) -> bool:
        return bool(
            _VERSION_INTENT_RE.search(question)
            and _KNOWN_NPM_PKGS.search(question)
        )

    async def fetch(
        self, client: httpx.AsyncClient, question: str
    ) -> Optional[str]:
        m = _KNOWN_NPM_PKGS.search(question)
        if not m:
            return None
        pkg = _canonical(m.group(0))
        return await _npm_fetch(client, pkg, question)


class PypiRetriever:
    """
    Fetches version+date data from PyPI for well-known packages.

    Same gating pattern as `NpmRetriever`.
    """

    name = "pypi"

    def matches(self, question: str) -> bool:
        return bool(
            _VERSION_INTENT_RE.search(question)
            and _KNOWN_PYPI_PKGS.search(question)
        )

    async def fetch(
        self, client: httpx.AsyncClient, question: str
    ) -> Optional[str]:
        m = _KNOWN_PYPI_PKGS.search(question)
        if not m:
            return None
        pkg = _canonical(m.group(0))
        return await _pypi_fetch(client, pkg, question)


class GithubReleasesRetriever:
    """
    Fetches release data from the GitHub Releases API when the question
    contains an `owner/repo` token alongside version intent.
    """

    name = "github_releases"

    def matches(self, question: str) -> bool:
        if not _VERSION_INTENT_RE.search(question):
            return False
        m = _GITHUB_REPO_RE.search(question)
        if not m:
            return False
        owner = m.group(1)
        # Reject obvious non-owner tokens: anything containing a dot is
        # almost certainly a filename or domain, not an org name.
        return "." not in owner

    async def fetch(
        self, client: httpx.AsyncClient, question: str
    ) -> Optional[str]:
        m = _GITHUB_REPO_RE.search(question)
        if not m:
            return None
        owner, repo = m.group(1), m.group(2)
        try:
            r = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/releases",
                params={"per_page": _MAX_VERSIONS},
                timeout=_HTTP_TIMEOUT,
                headers={"Accept": "application/vnd.github+json"},
            )
        except httpx.RequestError as e:
            logger.warning("github fetch failed for %s/%s: %s", owner, repo, e)
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


# Common English words and version-intent vocabulary that should never be
# treated as candidate package names. The list is kept short on purpose:
# anything not in it gets tried against the registry, and a 404 is silent.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "for", "with",
    "from", "to", "into", "on", "off", "at", "by", "as", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do",
    "does", "did", "can", "could", "will", "would", "should", "may",
    "might", "must", "this", "that", "these", "those", "it", "its",
    "they", "them", "their", "our", "you", "your", "any", "all",
    "what", "which", "when", "where", "who", "why", "how",
    "version", "versions", "release", "releases", "patch", "patches",
    "changelog", "update", "updates", "latest", "recent", "history",
    "npm", "pypi", "github", "library", "package", "module", "framework",
    "node", "python", "java", "javascript", "typescript", "stable",
    "between", "compare", "comparison", "list", "show", "tell",
    "now", "currently", "today", "yesterday",
}

# High-confidence package-name patterns. These run first and provide the
# best candidates: words explicitly tagged as packages, kebab-case
# identifiers, and scoped npm names.
_HIGH_CONFIDENCE_PKG_RE = re.compile(
    r"\b(?:package|library|module|framework|lib|dep|dependency)\s+"
    r"([a-z][\w.-]{2,})\b"               # "package <name>"
    r"|\b([a-z][\w-]{2,}(?:-[\w-]+)+)\b"  # kebab-case
    r"|(@[\w-]+/[\w-]+)\b",               # scoped npm "@scope/pkg"
    re.IGNORECASE,
)

# Catch-all for plain lowercase identifiers. Only used after the
# high-confidence patterns; results pass through stopword filtering.
_LOW_CONFIDENCE_PKG_RE = re.compile(r"\b([a-z][a-z0-9_-]{2,19})\b")


def _candidate_packages(question: str) -> List[str]:
    """
    Extract plausible package names from a question that the curated
    allow-lists didn't match.

    Two passes: a high-confidence pass picks up obviously package-shaped
    tokens (kebab-case, scoped npm, explicit "package X" mentions); a
    low-confidence pass picks up any remaining lowercase identifier that
    is not a common English word or version-intent term.

    The generic retrievers tolerate 404s, so an occasional bad guess is
    cheap. Candidates are returned in first-occurrence order, deduplicated,
    and the caller bounds how many are actually queried.
    """
    seen: set[str] = set()
    out: List[str] = []
    for m in _HIGH_CONFIDENCE_PKG_RE.finditer(question):
        for group in m.groups():
            if not group:
                continue
            name = group.lower().strip()
            if name and name not in seen and name not in _STOPWORDS:
                seen.add(name)
                out.append(name)
    for m in _LOW_CONFIDENCE_PKG_RE.finditer(question.lower()):
        name = m.group(1)
        if name in seen or name in _STOPWORDS or name.isdigit():
            continue
        seen.add(name)
        out.append(name)
    return out


async def _npm_fetch(
    client: httpx.AsyncClient, pkg: str, question: str
) -> Optional[str]:
    """Fetch a package from the npm registry and format as a FACTS block."""
    try:
        r = await client.get(
            f"https://registry.npmjs.org/{pkg}", timeout=_HTTP_TIMEOUT
        )
    except httpx.RequestError as e:
        logger.warning("npm fetch failed for %s: %s", pkg, e)
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
    version_filter = _version_filter(question, pkg)
    filtered = _filter_by_version(stable, version_filter)
    if version_filter and not filtered:
        # Question targets a series that doesn't exist for this package —
        # better to surface nothing than a list from a different major.
        return None
    rows_to_show = filtered[:_MAX_VERSIONS]
    dist_tags = data.get("dist-tags", {}) or {}
    latest_global = dist_tags.get("latest", stable[0][0])
    return _format_table_block(
        source_label="npm",
        source_url=f"https://registry.npmjs.org/{pkg}",
        pkg=pkg,
        display=_display_name(pkg),
        rows=rows_to_show,
        latest_global=latest_global,
        version_filter=version_filter,
    )


async def _pypi_fetch(
    client: httpx.AsyncClient, pkg: str, question: str
) -> Optional[str]:
    """Fetch a package from PyPI and format as a FACTS block."""
    try:
        r = await client.get(
            f"https://pypi.org/pypi/{pkg}/json", timeout=_HTTP_TIMEOUT
        )
    except httpx.RequestError as e:
        logger.warning("pypi fetch failed for %s: %s", pkg, e)
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
    version_filter = _version_filter(question, pkg)
    filtered = _filter_by_version(raw, version_filter)
    if version_filter and not filtered:
        return None
    rows_to_show = filtered[:_MAX_VERSIONS]
    latest_global = data.get("info", {}).get("version", raw[0][0])
    return _format_table_block(
        source_label="PyPI",
        source_url=f"https://pypi.org/pypi/{pkg}/json",
        pkg=pkg,
        display=_display_name(pkg),
        rows=rows_to_show,
        latest_global=latest_global,
        version_filter=version_filter,
    )


class GenericNpmRetriever:
    """
    Fallback npm retriever for packages not on the curated allow-list.

    Extracts candidate package names from the question and attempts the
    registry lookup for each. Real packages return data; 404s are silent.
    Bounded to a small number of candidates per question to keep latency
    predictable.
    """

    name = "npm_generic"
    max_candidates = 3

    def matches(self, question: str) -> bool:
        if not _VERSION_INTENT_RE.search(question):
            return False
        # Only run when no allow-listed name was found — otherwise the
        # curated retriever already handles this question.
        if _KNOWN_NPM_PKGS.search(question):
            return False
        return bool(_candidate_packages(question))

    async def fetch(
        self, client: httpx.AsyncClient, question: str
    ) -> Optional[str]:
        candidates = _candidate_packages(question)[: self.max_candidates]
        for raw_name in candidates:
            pkg = _canonical(raw_name)
            block = await _npm_fetch(client, pkg, question)
            if block:
                return block
        return None


class GenericPypiRetriever:
    """Fallback PyPI retriever — mirror of `GenericNpmRetriever` for PyPI."""

    name = "pypi_generic"
    max_candidates = 3

    def matches(self, question: str) -> bool:
        if not _VERSION_INTENT_RE.search(question):
            return False
        if _KNOWN_PYPI_PKGS.search(question):
            return False
        return bool(_candidate_packages(question))

    async def fetch(
        self, client: httpx.AsyncClient, question: str
    ) -> Optional[str]:
        candidates = _candidate_packages(question)[: self.max_candidates]
        for raw_name in candidates:
            pkg = _canonical(raw_name)
            block = await _pypi_fetch(client, pkg, question)
            if block:
                return block
        return None


# Registry order matters: curated retrievers run first because they're
# free of false positives; generic ones run only when the allow-list misses.
_RETRIEVERS: List[Retriever] = [
    NpmRetriever(),
    PypiRetriever(),
    GithubReleasesRetriever(),
    GenericNpmRetriever(),
    GenericPypiRetriever(),
]


async def gather_facts(question: str) -> str:
    """Run every matching retriever concurrently and return joined FACTS."""
    active = [r for r in _RETRIEVERS if r.matches(question)]
    if not active:
        return ""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *(r.fetch(client, question) for r in active),
            return_exceptions=True,
        )
    blocks: List[str] = []
    for r, res in zip(active, results):
        if isinstance(res, Exception):
            logger.warning("retriever %s raised: %s", r.name, res)
            continue
        if res:
            blocks.append(res)
    return "\n\n".join(blocks)


def names_that_matched(question: str) -> List[str]:
    """Names of retrievers that will run for this question. Used by SSE."""
    return [r.name for r in _RETRIEVERS if r.matches(question)]


# ─── Post-process helpers (used by report_builder) ─────────────────────────


_TABLE_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", re.MULTILINE
)
_VERSION_LIKE_RE = re.compile(r"^v?\d+\.\d+(\.\d+)?(-[\w.]+)?$")


def extract_version_date_map(facts_text: str) -> dict[str, str]:
    """
    Parse a FACTS text block and return a mapping of version → canonical date.

    The report builder uses this map after the LLM call: if the model emits a
    version table whose dates disagree with the canonical values, those cells
    are replaced. This is the deterministic safety net for models prone to
    smoothing or interpolating date sequences.
    """
    out: dict[str, str] = {}
    for v, d in _TABLE_ROW_RE.findall(facts_text):
        v_clean = v.strip()
        d_clean = d.strip()
        if v_clean.lower() in {"version", "tag", "release"}:
            continue
        if not _VERSION_LIKE_RE.match(v_clean):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d_clean):
            continue
        out.setdefault(v_clean, d_clean)
    return out
