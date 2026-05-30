// lib/types.ts

// ─── AssistantModes ───────────────────────────────────────────────────────────

export interface ResponsePolicy {
  empathy_level: number;
  directness_level: number;
  verbosity: 'short' | 'medium' | 'long';
  format: 'freeform' | 'bullets' | 'steps';
  tone: string;
}

export interface MemoryPolicy {
  enabled: boolean;
  scope: 'session' | 'global';
  decay_days: number | null;
}

export interface SafetyPolicy {
  strictness: number;
  no_deception: boolean;
  no_dependency: boolean;
  no_medical_legal_claims: boolean;
}

export interface ToolPolicy {
  auto_invoke: boolean;
  allowed_tools: string[];
}

export interface AssistantMode {
  id: string;
  name: string;
  description: string;
  response_policy: ResponsePolicy;
  memory_policy: MemoryPolicy;
  safety_policy: SafetyPolicy;
  tool_policy: ToolPolicy;
}

// ─── Sessions ─────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  mode_id: string;
  created_at: string;
  summary?: string;
}

// ─── Messages ─────────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ToolEvent {
  type: string;
  count?: number;
  message?: string;
}

export interface RAGSource {
  document_id: string;
  filename: string;
  chunk_index: number;
  score: number;
  snippet: string;
}

export interface WebSource {
  title: string;
  url: string;
  snippet: string;
}

export interface ChatResponse {
  session_id: string;
  mode_id: string;
  assistant: string;
  rag_used: boolean;
  sources: RAGSource[];
  web_sources?: WebSource[];
  pipeline: any;
  tool_events: ToolEvent[];
}

// ─── Alerts ───────────────────────────────────────────────────────────────────

export interface Alert {
  id: string;
  session_id: string;
  title?: string;
  body?: string;
  content: string;
  priority: 'low' | 'medium' | 'high';
  status: 'active' | 'done' | 'cancelled';
  due_at?: string;
  created_at: string;
  updated_at: string;
}

export interface AlertsResponse {
  alerts: Alert[];
  total: number;
}

// ─── Session Summary ──────────────────────────────────────────────────────────

export interface SessionSummary {
  session_id: string;
  summary: string;
  open_loops: string[];
  updated_at: string;
}

export interface SessionMessagesResponse {
  session: Session;
  messages: Message[];
}

export interface SessionSummaryResponse {
  session: Session;
  summary: SessionSummary | null;
  debug: any;
}

// ─── RAG Workspaces (Feature 1) ───────────────────────────────────────────────

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  document_count: number;
  total_chunks: number;
}

export interface WorkspaceDocument {
  id: string;
  workspace_id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  guard_status: 'clean' | 'flagged' | 'blocked';
  status: 'pending' | 'ready' | 'error';
  created_at: string;
}

export interface DocumentUploadResponse {
  doc_id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  guard_status: string;
}

export interface WorkspaceQueryResponse {
  workspace_id: string;
  query: string;
  context: string;
}

