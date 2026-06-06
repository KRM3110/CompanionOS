"""
config.py — Centralized Application Settings for CompanionOS.

ALL environment-driven configuration lives here. No module should call `os.getenv()`
directly. Instead, every module imports `get_settings()` from this file and reads
the typed value it needs.

How it works:
  - `pydantic-settings` reads from environment variables or a .env file at startup.
  - Field names map 1-to-1 with env var names (case-insensitive).
  - `@lru_cache` ensures the Settings object is only instantiated ONCE per process
    lifetime, making repeated calls to `get_settings()` essentially free.
  - Pydantic validates types at startup, so a misconfigured env (e.g. a non-int
    SUMMARY_CADENCE) fails fast and loudly at boot instead of deep inside a runtime call.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Typed application settings, loaded from environment variables or .env file.

    Defaults here represent safe, sensible values for local development.
    In production, override via environment variables (e.g. in docker-compose or k8s secrets).

    Fields:
        gemini_api_key:          Google Gemini API key (set in backend/.env, never commit).
        gemini_model:            Gemini model to use for all LLM calls. Default: gemini-2.5-flash.
        embed_model:             Gemini embedding model name. Default: models/text-embedding-004.
        summary_cadence:         How many messages between session summary updates.
                                 Lower = more frequent (more LLM calls). Default=6.
        mx1_confidence_threshold: Minimum confidence score (0.0-1.0) for a memory item
                                 extracted by MX1 to be persisted. Default=0.8.
        mx1_recent_messages:     Number of most recent messages to feed into MX1 extraction.
        allow_global_write:      Whether MX1 can write to the global memory scope.
                                 If False, all extracted memories are session-scoped only.
    """

    # Gemini — LangChain-powered chat LLM and RAG embeddings provider
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    modes_dir: str = ""  # Default resolved at runtime from modes/data/ inside the package
    # RAG — ChromaDB persistent storage path (must be on a mounted volume in Docker)
    chroma_data_path: str = "/app/data/chroma"
    # RAG — Gemini embedding model (768-dim)
    embed_model: str = "models/text-embedding-004"
    # RAG — Chunking parameters
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 3
    summary_cadence: int = 6
    mx1_confidence_threshold: float = 0.8
    mx1_recent_messages: int = 10
    allow_global_write: bool = True
    chat_jobs_queue_size: int = 256
    chat_jobs_worker_count: int = 2
    chat_jobs_max_retries: int = 2

    @field_validator("gemini_api_key")
    @classmethod
    def _require_gemini_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "GEMINI_API_KEY is required. Set it in backend/.env or the environment."
            )
        return v.strip()

    class Config:
        # pydantic-settings will read a .env file if present at the working directory.
        # Variables defined in the shell environment take precedence over .env values.
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.

    Uses @lru_cache so that the Settings object is constructed from the environment
    exactly once, regardless of how many modules call this. This avoids both
    redundant disk reads (.env file) and validation overhead on every request.

    Usage:
        from .config import get_settings
        settings = get_settings()
        model = settings.gemini_model
    """
    return Settings()
