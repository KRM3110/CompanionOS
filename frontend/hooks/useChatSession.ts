'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type {
  Message,
  RAGSource,
  WebSource,
} from '@/lib/types';

const ALLOWED_MODES = ['safe', 'focus', 'research'];

type ToastShape = { message: string; type: 'success' | 'error' | 'info' };

interface UseChatSessionOpts {
  activeWorkspaceId: string | null;
  selectedModeId: string | null;
  setSelectedModeId: (id: string) => void;
  onToast?: (toast: ToastShape) => void;
  onError?: (msg: string | null) => void;
  onSessionCreated?: (sessionId: string) => void;
  onAlertCreated?: (message: string) => void;
}

interface UseChatSessionReturn {
  sessionId: string | null;
  messages: Message[];
  ragUsedMap: Record<string, boolean>;
  ragSourcesMap: Record<string, RAGSource[]>;
  webSourcesMap: Record<string, WebSource[]>;
  summary: string;
  loading: boolean;
  sendMessage: (message: string) => Promise<void>;
  endSession: () => void;
  resetForWorkspaceSwitch: () => void;
}

export function useChatSession(opts: UseChatSessionOpts): UseChatSessionReturn {
  const {
    activeWorkspaceId,
    selectedModeId,
    setSelectedModeId,
    onToast,
    onError,
    onSessionCreated,
    onAlertCreated,
  } = opts;

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [ragUsedMap, setRagUsedMap] = useState<Record<string, boolean>>({});
  const [ragSourcesMap, setRagSourcesMap] = useState<Record<string, RAGSource[]>>({});
  const [webSourcesMap, setWebSourcesMap] = useState<Record<string, WebSource[]>>({});
  const [summary, setSummary] = useState<string>('');
  const [loading, setLoading] = useState(false);

  // Keep latest values accessible inside async handlers without re-creating them.
  const activeWorkspaceIdRef = useRef(activeWorkspaceId);
  const selectedModeIdRef = useRef(selectedModeId);
  useEffect(() => { activeWorkspaceIdRef.current = activeWorkspaceId; }, [activeWorkspaceId]);
  useEffect(() => { selectedModeIdRef.current = selectedModeId; }, [selectedModeId]);

  const loadSessionMessages = useCallback(async (sid: string) => {
    try {
      const data = await api.getSessionMessages(sid);
      setMessages(data.messages);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  }, []);

  const loadSummary = useCallback(async (sid: string) => {
    try {
      const data = await api.getSessionSummary(sid);
      if (data.summary?.summary) setSummary(data.summary.summary);
    } catch {
      // Summary may not exist yet for short sessions.
    }
  }, []);

  // Bootstrap from localStorage on mount.
  useEffect(() => {
    const storedSessionId = localStorage.getItem('session_id');
    const storedModeId = localStorage.getItem('mode_id');
    if (storedSessionId && storedModeId && ALLOWED_MODES.includes(storedModeId)) {
      setSessionId(storedSessionId);
      setSelectedModeId(storedModeId);
      loadSessionMessages(storedSessionId);
      loadSummary(storedSessionId);
      onSessionCreated?.(storedSessionId);
    } else {
      localStorage.removeItem('mode_id');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendMessage = useCallback(async (message: string) => {
    setLoading(true);
    onError?.(null);

    let sid = sessionId;
    const currentMode = selectedModeIdRef.current ?? 'safe';
    if (!sid) {
      if (!selectedModeIdRef.current) setSelectedModeId('safe');
      try {
        const data = await api.createSession(currentMode);
        sid = data.session_id;
        setSessionId(sid);
        localStorage.setItem('session_id', sid);
        localStorage.setItem('mode_id', currentMode);
        onSessionCreated?.(sid);
      } catch (err: any) {
        onError?.(err.message);
        onToast?.({ message: 'Failed to start session', type: 'error' });
        setLoading(false);
        return;
      }
    }

    const tempId = `temp-${Date.now()}`;
    const tempUserMessage: Message = {
      id: tempId,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    try {
      const response = await api.sendMessage(
        sid,
        message,
        activeWorkspaceIdRef.current,
        currentMode,
      );
      const assistantId = `assistant-${Date.now()}`;

      setMessages((prev) => {
        const withoutTemp = prev.filter((m) => m.id !== tempId);
        return [
          ...withoutTemp,
          {
            id: `user-${Date.now()}`,
            role: 'user' as const,
            content: message,
            created_at: new Date().toISOString(),
          },
          {
            id: assistantId,
            role: 'assistant' as const,
            content: response.assistant,
            created_at: new Date().toISOString(),
          },
        ];
      });

      const msgSources = response.sources || [];
      if (response.rag_used || msgSources.length > 0) {
        setRagUsedMap((prev) => ({ ...prev, [assistantId]: true }));
      }
      setRagSourcesMap((prev) => ({ ...prev, [assistantId]: msgSources }));
      if (response.web_sources?.length) {
        setWebSourcesMap((prev) => ({ ...prev, [assistantId]: response.web_sources! }));
      }

      const alertEvent = response.tool_events?.find((e) => e.type === 'alert_created');
      if (alertEvent) {
        onAlertCreated?.(alertEvent.message || 'New alert created');
      }

      // Summary cadence: every ~5 turns, refresh the persisted summary.
      setMessages((prev) => {
        if (prev.length % 5 === 0) loadSummary(sid!);
        return prev;
      });
    } catch (err: any) {
      const msg = err.message || 'Unknown error';
      const isServiceError =
        msg.includes('502') || msg.includes('504') || msg.includes('fetch failed');
      onError?.(
        isServiceError
          ? 'Backend service is unavailable. Please check your Docker containers.'
          : msg,
      );
      onToast?.({ message: 'Failed to send message', type: 'error' });
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
    } finally {
      setLoading(false);
    }
  }, [sessionId, setSelectedModeId, onError, onToast, onSessionCreated, onAlertCreated, loadSummary]);

  const endSession = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setSummary('');
    setRagUsedMap({});
    setRagSourcesMap({});
    setWebSourcesMap({});
    localStorage.removeItem('session_id');
    localStorage.removeItem('mode_id');
    onToast?.({ message: 'Session ended', type: 'info' });
  }, [onToast]);

  const resetForWorkspaceSwitch = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setRagUsedMap({});
    setRagSourcesMap({});
    setWebSourcesMap({});
    setSummary('');
    localStorage.removeItem('session_id');
    localStorage.removeItem('mode_id');
  }, []);

  return {
    sessionId,
    messages,
    ragUsedMap,
    ragSourcesMap,
    webSourcesMap,
    summary,
    loading,
    sendMessage,
    endSession,
    resetForWorkspaceSwitch,
  };
}
