// lib/api.ts
import {
  Persona,
  Session,
  Message,
  ChatResponse,
  Alert,
  AlertsResponse,
  SessionMessagesResponse,
  SessionSummary,
  SessionSummaryResponse,
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
  // Personas
  async getPersonas(): Promise<Persona[]> {
    return fetchJSON<Persona[]>('/personas');
  },

  // Sessions
  async createSession(persona_id: string): Promise<{ session_id: string }> {
    return fetchJSON('/sessions', {
      method: 'POST',
      body: JSON.stringify({ persona_id }),
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

  // Chat
  async sendMessage(session_id: string, message: string): Promise<ChatResponse> {
    return fetchJSON('/chat/send', {
      method: 'POST',
      body: JSON.stringify({ session_id, message }),
    });
  },

  // Alerts
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
};