"""Request body schemas shared across route modules."""

from typing import Optional

from pydantic import BaseModel, Field


class CreateSessionReq(BaseModel):
    mode_id: str = Field(..., description="AssistantMode ID (e.g. 'focus', 'research')")


class ChatSendReq(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    workspace_id: Optional[str] = Field(
        None, description="Optional workspace for RAG context injection"
    )
    mode_id: Optional[str] = Field(
        None,
        description="Override session mode for this message (e.g. switching modes mid-conversation)",
    )


class MemoryUpsertReq(BaseModel):
    scope: str = Field(..., pattern="^(global|session)$")
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=400)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    session_id: str | None = None


class CreateAlertReq(BaseModel):
    scope: str = Field("session", pattern="^(global|session)$")
    session_id: str | None = None
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=500)


class ToolSettingUpsertReq(BaseModel):
    scope: str = Field(..., pattern="^(global|session)$")
    tool_id: str = Field(..., min_length=1, max_length=64)
    enabled: bool
    session_id: str | None = None


class CreateWorkspaceReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)


class WorkspaceQueryReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(3, ge=1, le=10)


class ScanTextReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    document_id: str | None = Field(None)


class StartResearchReq(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    workspace_id: Optional[str] = Field(None)


class SaveResearchReq(BaseModel):
    session_id: str = Field(..., description="Chat session to save memory into")
    scope: str = Field("global", pattern="^(global|session)$")
