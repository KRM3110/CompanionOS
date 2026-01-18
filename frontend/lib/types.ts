// lib/types.ts
export interface Persona {
  id: string;
  name: string;
  description: string;
  sliders: Record<string, any>;
  style: Record<string, any>;
  memory_policy: Record<string, any>;
}

export interface Session {
  id: string;
  persona_id: string;
  created_at: string;
  updated_at: string;
  summary?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface JudgeVerdict {
  verdict: 'PASS' | 'REWRITE' | 'BLOCK';
  reason: string;
  risk_tags: string[];
}

export interface ToolEvent {
  type: string;
  count?: number;
  message?: string;
}

export interface ChatResponse {
  session_id: string;
  persona_id: string;
  assistant: string;
  judge: JudgeVerdict;
  pipeline: any;
  tool_events: ToolEvent[];
  alerts_created: Alert[];
}

export interface Alert {
  id: string;
  session_id: string;
  persona_id: string;
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

export interface SessionMessagesResponse {
  session: Session;
  messages: Message[];
}

export interface SessionSummary {
  session_id: string;
  summary: string;
  open_loops: string[];
  updated_at: string;
}

export interface SessionSummaryResponse {
  session: Session;
  summary: SessionSummary | null;
  debug: any;
}