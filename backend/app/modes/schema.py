"""
modes/schema.py — AssistantMode Pydantic schema for CompanionOS.

Defines the typed policy architecture that replaces the old monolithic persona dict.
Each AssistantMode is decomposed into four orthogonal policy axes:

  - ResponsePolicy:  Controls how the assistant communicates (tone, length, format).
  - MemoryPolicy:    Controls whether and how facts about the user are persisted.
  - SafetyPolicy:    Controls ethical bounds and judge strictness.
  - ToolPolicy:      Controls which tools are available and whether they auto-invoke.

All fields have sensible defaults so partial JSON files are valid — only `id`, `name`,
and `description` are required.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ResponsePolicy(BaseModel):
    """Controls how the assistant communicates."""

    empathy_level: float = Field(0.5, ge=0.0, le=1.0, description="0=detached, 1=highly empathetic")
    directness_level: float = Field(0.5, ge=0.0, le=1.0, description="0=indirect, 1=very direct")
    verbosity: str = Field("short", description="short | medium | long")
    format: str = Field("freeform", description="freeform | bullets | steps")
    tone: str = Field("neutral", description="neutral | warm | clinical | enthusiastic")


class MemoryPolicy(BaseModel):
    """Controls whether and how user facts are persisted."""

    enabled: bool = Field(False, description="Whether memory extraction is active")
    scope: str = Field("session", description="session | global")
    decay_days: Optional[int] = Field(None, description="Days before memory items expire; null=never")


class SafetyPolicy(BaseModel):
    """Controls ethical bounds and judge behaviour."""

    strictness: float = Field(0.5, ge=0.0, le=1.0, description="0=relaxed, 1=maximum strictness. 0=judge disabled.")
    no_deception: bool = Field(True, description="Prevents claiming sentience or real-world experiences")
    no_dependency: bool = Field(True, description="Avoids encouraging emotional dependency")
    no_medical_legal_claims: bool = Field(True, description="Redirects medical/legal advice to professionals")


class ToolPolicy(BaseModel):
    """Controls tool availability and invocation behaviour."""

    auto_invoke: bool = Field(False, description="If True, tools may be called without explicit user request")
    allowed_tools: List[str] = Field(default_factory=list, description="Explicit tool allow-list; empty=all tools")


class AssistantMode(BaseModel):
    """
    Top-level AssistantMode definition.

    Maps to a single *.json file in backend/app/modes/data/.
    The four nested policy models are optional — defaults apply if omitted from JSON.
    """

    id: str = Field(..., description="Unique slug, e.g. 'focus' or 'research'")
    name: str = Field(..., description="Human-readable display name")
    description: str = Field(..., description="One-sentence summary shown in the UI")
    response_policy: ResponsePolicy = Field(default_factory=ResponsePolicy)
    memory_policy: MemoryPolicy = Field(default_factory=MemoryPolicy)
    safety_policy: SafetyPolicy = Field(default_factory=SafetyPolicy)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
