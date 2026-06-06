// lib/api.ts
import {
  AssistantMode,
  Session,
  Message,
  ChatResponse,
  Alert,
  AlertsResponse,
  SessionMessagesResponse,
  SessionSummary,
  SessionSummaryResponse,
  Workspace,
  WorkspaceDocument,
  DocumentUploadResponse,
  WorkspaceQueryResponse,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error: ${response.status} - ${error}`);
  }

  return response.json();
}

export const api = {
  // ─── AssistantModes (replaces getPersonas) ─────────────────────────────────
  async getModes(): Promise<AssistantMode[]> {
    return fetchJSON<AssistantMode[]>('/modes');
  },

  async getMode(mode_id: string): Promise<AssistantMode> {
    return fetchJSON<AssistantMode>(`/modes/${mode_id}`);
  },

  // ─── Sessions ──────────────────────────────────────────────────────────────
  async createSession(mode_id: string): Promise<{ session_id: string }> {
    return fetchJSON('/sessions', {
      method: 'POST',
      body: JSON.stringify({ mode_id }),
    });
  },

  async getSessionMessages(
    session_id: string,
    limit: number = 50
  ): Promise<SessionMessagesResponse> {
    return fetchJSON(`/sessions/${session_id}/messages?limit=${limit}`);
  },

  async getSessionSummary(session_id: string): Promise<SessionSummaryResponse> {
    return fetchJSON(`/sessions/${session_id}/summary`);
  },

  // ─── Chat ──────────────────────────────────────────────────────────────────
  async sendMessage(
    session_id: string,
    message: string,
    workspace_id?: string | null,
    mode_id?: string | null
  ): Promise<ChatResponse> {
    return fetchJSON('/chat/send', {
      method: 'POST',
      body: JSON.stringify({ session_id, message, workspace_id: workspace_id || null, mode_id: mode_id || null }),
    });
  },

  // ─── Alerts ────────────────────────────────────────────────────────────────
  async getAlerts(params: {
    scope?: 'session' | 'global';
    session_id?: string;
    status?: 'active' | 'done' | 'cancelled' | 'all';
    limit?: number;
  }): Promise<Alert[]> {
    const queryParams = new URLSearchParams();
    if (params.scope) queryParams.append('scope', params.scope);
    if (params.session_id) queryParams.append('session_id', params.session_id);
    if (params.status) queryParams.append('status', params.status);
    if (params.limit) queryParams.append('limit', params.limit.toString());
    return fetchJSON(`/alerts?${queryParams.toString()}`);
  },

  async updateAlert(alert_id: string, status: 'done' | 'cancelled'): Promise<{ ok: boolean }> {
    if (status === 'done') {
      return fetchJSON(`/alerts/${alert_id}/done`, { method: 'POST' });
    } else if (status === 'cancelled') {
      return fetchJSON(`/alerts/${alert_id}/cancel`, { method: 'POST' });
    }
    throw new Error(`Invalid status update: ${status}`);
  },

  async getDueAlerts(session_id?: string): Promise<Alert[]> {
    const queryParams = new URLSearchParams();
    if (session_id) queryParams.append('session_id', session_id);
    return fetchJSON(`/alerts/due?${queryParams.toString()}`);
  },

  // ─── Workspaces (Feature 1) ────────────────────────────────────────────────
  async getWorkspaces(): Promise<Workspace[]> {
    return fetchJSON<Workspace[]>('/workspaces');
  },

  async createWorkspace(name: string, description?: string): Promise<{ workspace_id: string; name: string }> {
    return fetchJSON('/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
  },

  async deleteWorkspace(workspace_id: string): Promise<{ deleted: boolean }> {
    return fetchJSON(`/workspaces/${workspace_id}`, { method: 'DELETE' });
  },

  async getDocuments(workspace_id: string): Promise<WorkspaceDocument[]> {
    return fetchJSON<WorkspaceDocument[]>(`/workspaces/${workspace_id}/documents`);
  },

  async uploadDocument(workspace_id: string, file: File): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE}/workspaces/${workspace_id}/documents`, {
      method: 'POST',
      body: formData,
      // Note: do NOT set Content-Type — browser sets multipart boundary automatically
    });
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Upload failed: ${response.status} - ${error}`);
    }
    return response.json();
  },

  async deleteDocument(workspace_id: string, doc_id: string): Promise<{ deleted: boolean }> {
    return fetchJSON(`/workspaces/${workspace_id}/documents/${doc_id}`, { method: 'DELETE' });
  },

  async queryWorkspace(workspace_id: string, query: string, top_k: number = 3): Promise<WorkspaceQueryResponse> {
    return fetchJSON(`/workspaces/${workspace_id}/query`, {
      method: 'POST',
      body: JSON.stringify({ query, top_k }),
    });
  },

};