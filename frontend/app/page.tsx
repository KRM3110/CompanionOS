// app/page.tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import {
  AssistantMode,
  Alert,
  WorkspaceDocument,
} from '@/lib/types';
import ChatWindow from '@/components/ChatWindow';
import AlertsPanel from '@/components/AlertsPanel';
import WorkspacePanel from '@/components/WorkspacePanel';
import Toast from '@/components/Toast';
import { useChatSession } from '@/hooks/useChatSession';

const MODE_DISPLAY: Record<string, { label: string; icon: string }> = {
  safe:     { label: 'Chat',          icon: '💬' },
  focus:    { label: 'Web Search',    icon: '🌐' },
  research: { label: 'Deep Research', icon: '🔬' },
};

export default function Home() {
  // ─── Modes ──────────────────────────────────────────────────────────────────
  const [modes, setModes] = useState<AssistantMode[]>([]);
  const [selectedModeId, setSelectedModeId] = useState<string | null>(null);

  // ─── Workspace ──────────────────────────────────────────────────────────────
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [workspaceDocs, setWorkspaceDocs] = useState<WorkspaceDocument[]>([]);
  const [workspaceRefreshKey, setWorkspaceRefreshKey] = useState(0);

  // ─── Alerts ─────────────────────────────────────────────────────────────────
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [showAlerts, setShowAlerts] = useState(false);
  const [alertFilter, setAlertFilter] = useState<string>('active');

  // ─── UI ─────────────────────────────────────────────────────────────────────
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const loadAlerts = useCallback(async (sid: string, status: string) => {
    setAlertsLoading(true);
    try {
      const data = await api.getAlerts({ scope: 'session', session_id: sid, status: status as any, limit: 50 });
      setAlerts(data || []);
    } catch (err) {
      console.error('Failed to load alerts:', err);
    } finally {
      setAlertsLoading(false);
    }
  }, []);

  // ─── Chat session (extracted hook) ──────────────────────────────────────────
  const {
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
  } = useChatSession({
    activeWorkspaceId,
    selectedModeId,
    setSelectedModeId,
    onToast: setToast,
    onError: setError,
    onSessionCreated: (sid) => loadAlerts(sid, 'active'),
    onAlertCreated: (message) => {
      setToast({ message: message || 'New alert created', type: 'info' });
      if (sessionId) loadAlerts(sessionId, alertFilter);
    },
  });

  // ─── Init ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const data = await api.getModes();
        setModes(data);
      } catch (err) {
        console.error('Failed to load modes', err);
      }
    })();

    const storedWorkspaceId = localStorage.getItem('workspace_id');
    if (storedWorkspaceId) setActiveWorkspaceId(storedWorkspaceId);
  }, []);

  useEffect(() => {
    if (!activeWorkspaceId) {
      setWorkspaceDocs([]);
      return;
    }
    (async () => {
      try {
        const docs = await api.getDocuments(activeWorkspaceId);
        setWorkspaceDocs(docs);
      } catch (e) {
        console.error('Failed to load workspace documents:', e);
      }
    })();
  }, [activeWorkspaceId]);

  // ─── Due Alerts Polling ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;
    const notifiedAlerts = new Set<string>();
    const checkDueAlerts = async () => {
      try {
        const dueAlerts = await api.getDueAlerts(sessionId);
        for (const alert of dueAlerts) {
          if (!notifiedAlerts.has(alert.id)) {
            notifiedAlerts.add(alert.id);
            setToast({ message: `🔔 Reminder: ${alert.title || alert.content}`, type: 'info' });
            try { new Audio('/notification.mp3').play().catch(() => {}); } catch {}
          }
        }
      } catch {}
    };
    checkDueAlerts();
    const interval = setInterval(checkDueAlerts, 30000);
    return () => clearInterval(interval);
  }, [sessionId]);

  // ─── Handlers ───────────────────────────────────────────────────────────────
  const refreshWorkspaceDocs = useCallback(async (wsId: string) => {
    try {
      const docs = await api.getDocuments(wsId);
      setWorkspaceDocs(docs);
    } catch (e) {
      console.error('Failed to load workspace documents:', e);
    }
  }, []);

  const handleUploadDocument = async (file: File) => {
    if (!activeWorkspaceId) {
      setToast({ message: 'Select or create a workspace first to upload files', type: 'info' });
      return;
    }
    await api.uploadDocument(activeWorkspaceId, file);
    await refreshWorkspaceDocs(activeWorkspaceId);
    setWorkspaceRefreshKey((k) => k + 1);
  };

  const handleDeleteDocument = async (doc: WorkspaceDocument) => {
    if (!activeWorkspaceId) return;
    if (!confirm(`Remove "${doc.filename}" from this workspace?`)) return;
    await api.deleteDocument(activeWorkspaceId, doc.id);
    await refreshWorkspaceDocs(activeWorkspaceId);
    setWorkspaceRefreshKey((k) => k + 1);
  };

  const handleUpdateAlert = async (alertId: string, status: 'done' | 'cancelled') => {
    try {
      await api.updateAlert(alertId, status);
      if (sessionId) loadAlerts(sessionId, alertFilter);
      setToast({ message: `Alert ${status}`, type: 'success' });
    } catch {
      setToast({ message: 'Failed to update alert', type: 'error' });
    }
  };

  const handleRefreshAlerts = (status: string) => {
    setAlertFilter(status);
    if (sessionId) loadAlerts(sessionId, status);
  };

  const handleEndSession = () => {
    endSession();
    setAlerts([]);
  };

  const handleSelectWorkspace = (id: string | null) => {
    if (id === activeWorkspaceId) return;
    // Switching workspace starts a fresh chat.
    setActiveWorkspaceId(id);
    resetForWorkspaceSwitch();
    setAlerts([]);
    if (id) localStorage.setItem('workspace_id', id);
    else localStorage.removeItem('workspace_id');
  };

  const handleSelectMode = (id: string) => {
    if (id === selectedModeId) return;
    setSelectedModeId(id);
    // Mode is sent per-request to the backend, so it takes effect immediately
    // on the next message without needing to reset the conversation.
    const modeLabel = MODE_DISPLAY[id]?.label ?? id;
    setToast({ message: `Switched to ${modeLabel}`, type: 'info' });
  };

  const activeModeDisplay = selectedModeId
    ? (MODE_DISPLAY[selectedModeId] ?? { label: selectedModeId, icon: '✦' })
    : null;

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">

      {/* ── Left Sidebar ──────────────────────────────────────────────────── */}
      <div className="w-12 bg-muted/10 border-r border-border flex flex-col items-center py-3 gap-1 shrink-0">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="w-9 h-9 flex items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>

        <button
          onClick={handleEndSession}
          className="w-9 h-9 flex items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          title="New chat"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </button>

        <button
          onClick={() => setSidebarOpen(true)}
          className={`w-9 h-9 flex items-center justify-center rounded-lg transition-colors ${
            activeWorkspaceId ? 'text-primary hover:bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
          }`}
          title="Workspaces"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
          </svg>
        </button>

        {sessionId && (
          <button
            onClick={() => setShowAlerts(!showAlerts)}
            className={`relative w-9 h-9 flex items-center justify-center rounded-lg transition-colors ${
              showAlerts ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            }`}
            title="Alerts"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            {alerts.length > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-primary" />
            )}
          </button>
        )}

      </div>

      <div className={`${sidebarOpen ? 'w-56' : 'w-0'} bg-muted/20 border-r border-border flex flex-col shrink-0 overflow-hidden transition-all duration-300`}>
        <div className="min-w-[224px]">

          <div className="px-4 py-4 border-b border-border shrink-0">
            <h1 className="text-sm font-bold bg-gradient-to-r from-primary to-violet-600 bg-clip-text text-transparent">
              CompanionOS
            </h1>
          </div>

          <div className="overflow-y-auto p-3 space-y-5" style={{ maxHeight: 'calc(100vh - 120px)' }}>

            <WorkspacePanel
              activeWorkspaceId={activeWorkspaceId}
              onSelectWorkspace={handleSelectWorkspace}
              documents={workspaceDocs}
              onDeleteDocument={handleDeleteDocument}
              refreshTrigger={workspaceRefreshKey}
            />

            {activeWorkspaceId && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Documents
                  </label>
                  <label
                    className="w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                    title="Upload document"
                  >
                    <input
                      type="file"
                      accept=".pdf,.docx,.doc,.txt,.md"
                      className="hidden"
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        if (f) { await handleUploadDocument(f); e.target.value = ''; }
                      }}
                    />
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                  </label>
                </div>
                {workspaceDocs.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic text-center py-3">No documents yet. Click + to upload.</p>
                ) : (
                  <div className="space-y-0.5">
                    {workspaceDocs.map((doc) => (
                      <div key={doc.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-muted/40 group transition-colors">
                        <svg className="w-3.5 h-3.5 text-muted-foreground shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <span className="text-xs text-foreground truncate flex-1">{doc.filename}</span>
                        <button onClick={() => handleDeleteDocument(doc)} className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all" title="Remove">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {sessionId && summary && (
              <div className="p-3 bg-primary/5 border border-primary/10 rounded-xl">
                <h3 className="text-xs font-semibold text-primary mb-1.5 uppercase tracking-wider">Summary</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{summary}</p>
              </div>
            )}
          </div>

          {sessionId && (
            <div className="p-3 border-t border-border space-y-2">
              {activeModeDisplay && (
                <div className="flex items-center gap-2 text-xs text-green-400 font-medium px-2.5 py-1.5 bg-green-500/10 border border-green-500/20 rounded-lg">
                  <span className="flex h-1.5 w-1.5 relative shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400/75" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-400" />
                  </span>
                  <span className="truncate">{activeModeDisplay.icon} {activeModeDisplay.label}</span>
                </div>
              )}
              <button
                onClick={handleEndSession}
                className="w-full px-2 py-1.5 text-xs font-medium text-destructive bg-destructive/10 hover:bg-destructive/20 rounded-lg transition-colors"
              >
                End Session
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Main Chat Area ────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden relative bg-background">

        <div className="flex flex-1 overflow-hidden">
        {error && (
          <div className="absolute top-3 left-3 right-3 z-50 animate-fade-in">
            <div className="bg-destructive/10 border border-destructive/20 px-4 py-2.5 rounded-lg text-sm text-destructive flex items-center gap-2 shadow-lg">
              <span className="font-semibold">Error:</span>
              {error}
              <button onClick={() => setError(null)} className="ml-auto text-destructive/60 hover:text-destructive">✕</button>
            </div>
          </div>
        )}

        <ChatWindow
          messages={messages}
          onSendMessage={sendMessage}
          loading={loading}
          ragUsedMap={ragUsedMap}
          ragSourcesMap={ragSourcesMap}
          modes={modes.filter((m) => ['safe', 'focus', 'research'].includes(m.id))}
          selectedModeId={selectedModeId}
          onSelectMode={handleSelectMode}
          workspaceId={activeWorkspaceId}
          onUploadDocument={handleUploadDocument}
          webSourcesMap={webSourcesMap}
        />

        {showAlerts && sessionId && (
          <div className="w-96 bg-background/80 border-l border-border backdrop-blur-md animate-slide-in shadow-xl z-20 overflow-y-auto shrink-0">
            <AlertsPanel
              alerts={alerts}
              onUpdateAlert={handleUpdateAlert}
              onRefresh={handleRefreshAlerts}
              onClose={() => setShowAlerts(false)}
              loading={alertsLoading}
            />
          </div>
        )}
        </div>
      </div>

      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}
    </div>
  );
}
