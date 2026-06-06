// components/WorkspacePanel.tsx
'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Workspace, WorkspaceDocument } from '@/lib/types';

interface WorkspacePanelProps {
  activeWorkspaceId: string | null;
  onSelectWorkspace: (id: string | null) => void;
  /** Called after create/delete so parent can reload docs */
  onWorkspaceChange?: () => void;
  documents?: WorkspaceDocument[];
  onDeleteDocument?: (doc: WorkspaceDocument) => void;
  /** Increment this to force a workspace list refresh (e.g. after doc upload) */
  refreshTrigger?: number;
}

export default function WorkspacePanel({
  activeWorkspaceId,
  onSelectWorkspace,
  onWorkspaceChange,
  documents = [],
  onDeleteDocument,
  refreshTrigger = 0,
}: WorkspacePanelProps) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadWorkspaces();
  }, [refreshTrigger]);

  const loadWorkspaces = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getWorkspaces();
      setWorkspaces(data);
    } catch {
      setError('Failed to load workspaces');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const result = await api.createWorkspace(newName.trim(), newDesc.trim() || undefined);
      setNewName('');
      setNewDesc('');
      setShowForm(false);
      await loadWorkspaces();
      onSelectWorkspace(result.workspace_id);
      onWorkspaceChange?.();
    } catch {
      setError('Failed to create workspace');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this workspace and all its indexed documents?')) return;
    try {
      await api.deleteWorkspace(id);
      if (activeWorkspaceId === id) onSelectWorkspace(null);
      await loadWorkspaces();
      onWorkspaceChange?.();
    } catch {
      setError('Failed to delete workspace');
    }
  };

  return (
    <div className="mt-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Workspaces
        </label>
        <button
          id="workspace-add-btn"
          onClick={() => { setShowForm(!showForm); setError(null); }}
          className="w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
          title="New workspace"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="mb-3 p-3 bg-card border border-border rounded-lg space-y-2 animate-slide-in">
          <input
            id="workspace-name-input"
            type="text"
            placeholder="Workspace name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            autoFocus
            className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary text-foreground placeholder:text-muted-foreground"
          />
          <input
            id="workspace-desc-input"
            type="text"
            placeholder="Description (optional)"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary text-foreground placeholder:text-muted-foreground"
          />
          <div className="flex gap-2">
            <button
              id="workspace-create-btn"
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="flex-1 py-2 text-xs font-semibold bg-primary text-primary-foreground rounded-md hover:bg-primary/90 active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 transition-[background-color,opacity,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
            >
              {creating ? (
                <span className="flex items-center justify-center gap-1.5">
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Creating…
                </span>
              ) : 'Create'}
            </button>
            <button
              onClick={() => { setShowForm(false); setNewName(''); setNewDesc(''); }}
              className="px-3 py-2 text-xs text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 active:scale-[0.97] transition-[background-color,color,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-destructive mb-2 flex items-center gap-1">
          <span>⚠</span>{error}
        </p>
      )}

      {/* No workspace option */}
      <button
        onClick={() => onSelectWorkspace(null)}
        className={`w-full text-left px-3 py-2 rounded-lg text-xs mb-1 transition-colors ${
          activeWorkspaceId === null
            ? 'bg-muted/60 text-foreground font-medium'
            : 'text-muted-foreground hover:bg-muted/30'
        }`}
      >
        No workspace (direct chat)
      </button>

      {/* Workspace list */}
      {loading ? (
        <div className="flex justify-center py-4">
          <span className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-1">
          {workspaces.map((ws) => {
            const isActive = activeWorkspaceId === ws.id;
            return (
              <div key={ws.id}>
                <div
                  onClick={() => onSelectWorkspace(ws.id)}
                  className={`group flex items-start justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-[background-color,border-color,color] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] ${
                    isActive
                      ? 'bg-emerald-500/10 border border-emerald-500/25 text-emerald-300'
                      : 'text-foreground hover:bg-muted/40 border border-transparent hover:border-border'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold truncate flex items-center gap-1.5">
                      <svg className="w-3 h-3 shrink-0 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                      </svg>
                      <span className="truncate">{ws.name}</span>
                    </p>

                    <div className="flex items-center gap-2 mt-0.5">
                      {ws.description && (
                        <p className="text-xs text-muted-foreground truncate max-w-[110px]">{ws.description}</p>
                      )}
                      {!ws.description && (
                        <p className="text-xs text-muted-foreground">
                          {ws.document_count} doc{ws.document_count !== 1 ? 's' : ''}
                          {ws.total_chunks > 0 && (
                            <span className="ml-1 opacity-70">· {ws.total_chunks} chunks</span>
                          )}
                        </p>
                      )}
                    </div>

                    {ws.description && ws.document_count > 0 && (
                      <p className="text-xs text-muted-foreground/60 mt-0.5">
                        {ws.document_count} doc{ws.document_count !== 1 ? 's' : ''}
                        {ws.total_chunks > 0 && ` · ${ws.total_chunks} chunks`}
                      </p>
                    )}
                  </div>

                  <button
                    onClick={(e) => handleDelete(ws.id, e)}
                    className="shrink-0 ml-2 mt-0.5 opacity-0 group-hover:opacity-100 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 active:scale-95 transition-[opacity,color,background-color,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
                    title="Delete workspace"
                    aria-label={`Delete workspace ${ws.name}`}
                  >
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>

                {/* Document list shown under the active workspace */}
                {isActive && (
                  <div className="mt-1 mb-1 ml-2 space-y-0.5">
                    {documents.map((doc) => (
                      <div key={doc.id} className="group/doc flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-muted/40 transition-colors">
                        <svg className="w-3 h-3 shrink-0 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <span className="flex-1 text-[10px] text-muted-foreground truncate" title={doc.filename}>
                          {doc.filename}
                        </span>
                        <span className={`shrink-0 w-1.5 h-1.5 rounded-full ${
                          doc.status === 'ready' ? 'bg-emerald-500' :
                          doc.status === 'error' ? 'bg-destructive' : 'bg-amber-400 animate-pulse'
                        }`} title={doc.status} />
                        {onDeleteDocument && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onDeleteDocument(doc); }}
                            className="shrink-0 opacity-0 group-hover/doc:opacity-100 p-0.5 rounded text-muted-foreground hover:text-destructive active:scale-95 transition-[opacity,color,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
                            title="Remove document"
                            aria-label={`Remove ${doc.filename}`}
                          >
                            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        )}
                      </div>
                    ))}
                    {documents.length === 0 && (
                      <p className="px-2 text-[10px] text-muted-foreground/60 italic">No documents. Attach one in the chat.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {workspaces.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4 italic">
              No workspaces yet. Create one above.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
