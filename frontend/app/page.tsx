// app/page.tsx
'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import {
  Persona,
  Message,
  Alert,
  JudgeVerdict,
  SessionSummary,
} from '@/lib/types';
import PersonaSelect from '@/components/PersonaSelect';
import ChatWindow from '@/components/ChatWindow';
import AlertsPanel from '@/components/AlertsPanel';
import Toast from '@/components/Toast';

export default function Home() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [judgeVerdicts, setJudgeVerdicts] = useState<Record<string, JudgeVerdict>>({});
  const [summary, setSummary] = useState<string>('');

  const [loading, setLoading] = useState(false);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const [showAlerts, setShowAlerts] = useState(false);
  const [alertFilter, setAlertFilter] = useState<string>('active');

  // Load personas on mount
  useEffect(() => {
    loadPersonas();
    loadSessionFromStorage();
  }, []);

  const loadPersonas = async () => {
    try {
      const data = await api.getPersonas();
      setPersonas(data);
    } catch (err) {
      setError('Failed to load personas');
      console.error(err);
    }
  };

  const loadSessionFromStorage = () => {
    const storedSessionId = localStorage.getItem('session_id');
    const storedPersonaId = localStorage.getItem('persona_id');
    if (storedSessionId && storedPersonaId) {
      setSessionId(storedSessionId);
      setSelectedPersonaId(storedPersonaId);
      loadSessionMessages(storedSessionId);
      loadAlerts(storedSessionId, 'active');
      loadSummary(storedSessionId);
    }
  };

  const loadSessionMessages = async (sid: string) => {
    try {
      const data = await api.getSessionMessages(sid);
      setMessages(data.messages);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  };

  const loadAlerts = useCallback(async (sid: string, status: string) => {
    setAlertsLoading(true);
    try {
      const data = await api.getAlerts({
        scope: 'session',
        session_id: sid,
        status: status as any,
        limit: 50,
      });
      setAlerts(data || []);
    } catch (err) {
      console.error('Failed to load alerts:', err);
    } finally {
      setAlertsLoading(false);
    }
  }, []);

  // Poll for due alerts and show notifications
  useEffect(() => {
    if (!sessionId) return;

    const notifiedAlerts = new Set<string>();

    const checkDueAlerts = async () => {
      try {
        const dueAlerts = await api.getDueAlerts(sessionId);
        for (const alert of dueAlerts) {
          if (!notifiedAlerts.has(alert.id)) {
            notifiedAlerts.add(alert.id);
            setToast({
              message: `🔔 Reminder: ${alert.title || alert.content}`,
              type: 'info',
            });
            // Play notification sound
            try {
              const audio = new Audio('/notification.mp3');
              audio.volume = 0.5;
              audio.play().catch(() => { }); // Ignore if autoplay blocked
            } catch { }
          }
        }
      } catch (err) {
        console.error('Failed to check due alerts:', err);
      }
    };

    // Check immediately, then every 30 seconds
    checkDueAlerts();
    const interval = setInterval(checkDueAlerts, 30000);

    return () => clearInterval(interval);
  }, [sessionId]);

  const loadSummary = async (sid: string) => {
    try {
      const data = await api.getSessionSummary(sid);
      // The API returns { session:..., summary: { summary: "text", ... } }
      // So data.summary is the object, data.summary.summary is the text.
      if (data.summary && data.summary.summary) {
        setSummary(data.summary.summary);
      }
    } catch (err) {
      // Summary might not exist yet, that's ok
      console.log('No summary available yet');
    }
  };

  const handleStartSession = async () => {
    if (!selectedPersonaId) return;

    setLoading(true);
    setError(null);

    try {
      const data = await api.createSession(selectedPersonaId);
      setSessionId(data.session_id);
      localStorage.setItem('session_id', data.session_id);
      localStorage.setItem('persona_id', selectedPersonaId);
      setMessages([]);
      setSummary('');
      loadAlerts(data.session_id, 'active');
      setToast({ message: 'Session started successfully!', type: 'success' });
    } catch (err: any) {
      setError(err.message);
      setToast({ message: 'Failed to start session', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (message: string) => {
    if (!sessionId) return;

    setLoading(true);
    setError(null);

    // Optimistically add user message
    const tempUserMessage: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    try {
      const response = await api.sendMessage(sessionId, message);

      // Remove temp message and add real messages
      setMessages((prev) => {
        const withoutTemp = prev.filter((m) => m.id !== tempUserMessage.id);
        return [
          ...withoutTemp,
          {
            id: `user-${Date.now()}`,
            role: 'user' as const,
            content: message,
            created_at: new Date().toISOString(),
          },
          {
            id: `assistant-${Date.now()}`,
            role: 'assistant' as const,
            content: response.assistant,
            created_at: new Date().toISOString(),
          },
        ];
      });

      // Store judge verdict
      setJudgeVerdicts((prev) => ({
        ...prev,
        [`assistant-${Date.now()}`]: response.judge,
      }));

      // Check for alert events
      const alertEvent = response.tool_events.find((e) => e.type === 'alert_created');
      if (alertEvent) {
        setToast({
          message: alertEvent.message || 'New alert created',
          type: 'info'
        });
        loadAlerts(sessionId, alertFilter);
      }

      // Refresh summary periodically
      if (messages.length % 5 === 0) {
        loadSummary(sessionId);
      }
    } catch (err: any) {
      setError(err.message);
      setToast({ message: 'Failed to send message', type: 'error' });
      // Remove temp message on error
      setMessages((prev) => prev.filter((m) => m.id !== tempUserMessage.id));
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateAlert = async (alertId: string, status: 'done' | 'cancelled') => {
    try {
      await api.updateAlert(alertId, status);
      if (sessionId) {
        loadAlerts(sessionId, alertFilter);
      }
      setToast({ message: `Alert ${status}`, type: 'success' });
    } catch (err: any) {
      setToast({ message: 'Failed to update alert', type: 'error' });
    }
  };

  const handleRefreshAlerts = (status: string) => {
    setAlertFilter(status);
    if (sessionId) {
      loadAlerts(sessionId, status);
    }
  };

  const handleEndSession = () => {
    setSessionId(null);
    setMessages([]);
    setAlerts([]);
    setSummary('');
    setJudgeVerdicts({});
    localStorage.removeItem('session_id');
    localStorage.removeItem('persona_id');
    setToast({ message: 'Session ended', type: 'info' });
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Left Sidebar */}
      <div className="w-80 bg-muted/30 border-r border-border flex flex-col backdrop-blur-sm transition-all duration-300">
        <div className="p-6 border-b border-border">
          <h1 className="text-xl font-bold bg-gradient-to-r from-primary to-violet-600 bg-clip-text text-transparent">
            CompanionOS
          </h1>
        </div>

        <div className="flex-1 overflow-y-auto p-6 scrollbar-hide">
          <PersonaSelect
            personas={personas}
            selectedPersonaId={selectedPersonaId}
            onSelect={setSelectedPersonaId}
            onStartSession={handleStartSession}
            loading={loading}
            hasActiveSession={!!sessionId}
          />

          {sessionId && (
            <div className="animate-slide-in">
              {summary && (
                <div className="mt-8 p-4 bg-primary/5 border border-primary/10 rounded-xl">
                  <h3 className="text-xs font-semibold text-primary mb-2 uppercase tracking-wider">Session Summary</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{summary}</p>
                </div>
              )}

              <div className="mt-8 space-y-3">
                <button
                  onClick={() => setShowAlerts(!showAlerts)}
                  className={`w-full flex items-center justify-between px-4 py-3 border border-border text-sm font-medium rounded-lg transition-all duration-200 shadow-sm ${showAlerts
                    ? 'bg-primary/10 text-primary border-primary/20'
                    : 'bg-card text-foreground hover:bg-muted/50 hover:border-primary/50'
                    }`}
                >
                  <span>{showAlerts ? 'Hide Alerts Panel' : 'Show Alerts Panel'}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${showAlerts ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}`}>
                    {(alerts || []).length}
                  </span>
                </button>

                <button
                  onClick={handleEndSession}
                  className="w-full px-4 py-3 bg-destructive/10 text-destructive text-sm font-medium rounded-lg hover:bg-destructive/20 transition-colors border border-transparent"
                >
                  End Session
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col relative bg-gradient-to-br from-background to-secondary/30">
        {error && (
          <div className="absolute top-4 left-4 right-4 z-50 animate-slide-in">
            <div className="bg-destructive/10 border border-destructive/20 px-4 py-3 rounded-lg text-sm text-destructive flex items-center gap-2">
              <span className="font-semibold">Error:</span>
              {error}
            </div>
          </div>
        )}

        <ChatWindow
          messages={messages}
          onSendMessage={handleSendMessage}
          loading={loading}
          sessionActive={!!sessionId}
          judgeVerdicts={judgeVerdicts}
        />
      </div>

      {/* Right Alerts Panel */}
      {showAlerts && sessionId && (
        <div className="w-96 bg-background/80 border-l border-border backdrop-blur-md animate-slide-in shadow-xl z-20">
          <AlertsPanel
            alerts={alerts}
            onUpdateAlert={handleUpdateAlert}
            onRefresh={handleRefreshAlerts}
            onClose={() => setShowAlerts(false)}
            loading={alertsLoading}
          />
        </div>
      )}

      {/* Toast Notifications */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}