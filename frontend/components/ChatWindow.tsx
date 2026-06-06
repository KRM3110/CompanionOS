// components/ChatWindow.tsx
'use client';

import { Message, RAGSource, WebSource } from '@/lib/types';
import { useState, useRef, useEffect, useCallback } from 'react';
import RAGSourceBadge from './RAGSourceBadge';
import WebSourceBadge from './WebSourceBadge';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ACCEPTED_TYPES = '.pdf,.docx,.doc,.txt,.md';
const MAX_FILE_MB = 20;

const MODE_DISPLAY: Record<string, { label: string; icon: string }> = {
  safe:     { label: 'Chat',          icon: '💬' },
  focus:    { label: 'Web Search',    icon: '🌐' },
  research: { label: 'Deep Research', icon: '🔬' },
};

interface ModeOption {
  id: string;
  name: string;
}

interface ChatWindowProps {
  messages: Message[];
  onSendMessage: (message: string) => void;
  loading: boolean;
  ragUsedMap?: Record<string, boolean>;
  ragSourcesMap?: Record<string, RAGSource[]>;
  webSourcesMap?: Record<string, WebSource[]>;
  modes: ModeOption[];
  selectedModeId: string | null;
  onSelectMode: (id: string) => void;
  workspaceId?: string | null;
  onUploadDocument?: (file: File) => Promise<void>;
}

export default function ChatWindow({
  messages,
  onSendMessage,
  loading,
  ragUsedMap = {},
  ragSourcesMap = {},
  webSourcesMap = {},
  modes,
  selectedModeId,
  onSelectMode,
  onUploadDocument,
}: ChatWindowProps) {
  const [input, setInput] = useState('');
  const [showModeMenu, setShowModeMenu] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const modeMenuRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Close mode menu on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(e.target as Node)) {
        setShowModeMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // Auto-resize textarea whenever input changes
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !loading) {
      onSendMessage(input.trim());
      setInput('');
      // reset height
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !loading) {
        onSendMessage(input.trim());
        setInput('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !onUploadDocument) return;
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      setUploadStatus({ text: `File too large (max ${MAX_FILE_MB} MB)`, ok: false });
      setTimeout(() => setUploadStatus(null), 4000);
      return;
    }
    setUploading(true);
    setUploadStatus({ text: `Uploading ${file.name}…`, ok: true });
    try {
      await onUploadDocument(file);
      setUploadStatus({ text: `✓ ${file.name} uploaded`, ok: true });
    } catch (err: any) {
      const raw = err.message || 'Upload failed';
      let msg = `Upload failed: ${raw}`;
      if (raw.includes('blocked') || raw.includes('BLOCKED')) msg = '🚫 Document blocked by security guard.';
      else if (raw.includes('400')) msg = '⚠ Could not parse this file.';
      setUploadStatus({ text: msg, ok: false });
    } finally {
      setUploading(false);
      setTimeout(() => setUploadStatus(null), 4000);
    }
  }, [onUploadDocument]);

  const selectedMode = selectedModeId ? (MODE_DISPLAY[selectedModeId] ?? { label: selectedModeId, icon: '✦' }) : null;

  // ─── Shared input bar ──────────────────────────────────────────────────────
  const inputBar = (
    <div className="relative w-full">
      {uploadStatus && (
        <div className={`mb-2 px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2 ${
          uploadStatus.ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-destructive/10 text-destructive'
        }`}>
          {uploading && <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />}
          {uploadStatus.text}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 bg-muted/60 border border-border/60 rounded-3xl px-4 py-3 focus-within:border-primary/30 focus-within:bg-muted/80 transition-all shadow-lg w-full"
      >
        {/* + mode picker button */}
        <div className="relative shrink-0 self-end" ref={modeMenuRef}>
          <button
            type="button"
            onClick={() => setShowModeMenu(!showModeMenu)}
            className={`w-8 h-8 flex items-center justify-center rounded-xl transition-colors text-base ${
              selectedMode
                ? 'bg-primary/10 text-primary hover:bg-primary/20'
                : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
            title="Select mode"
          >
            {selectedMode ? selectedMode.icon : '+'}
          </button>

          {/* Dropdown */}
          {showModeMenu && (
            <div className="absolute bottom-full mb-2 left-0 bg-card border border-border rounded-xl shadow-xl py-1.5 min-w-[190px] z-50 animate-fade-in">
              {/* Upload option - always shown */}
              <button
                type="button"
                onClick={() => { setShowModeMenu(false); fileInputRef.current?.click(); }}
                className="w-full text-left px-4 py-2.5 text-sm flex items-center gap-3 text-foreground hover:bg-muted/50 transition-colors"
              >
                <span className="text-base leading-none">📎</span>
                <span className="font-medium">Add files</span>
              </button>
              <div className="h-px bg-border mx-2 my-1" />

              <p className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Mode
              </p>
              <div className="h-px bg-border mx-2 mb-1" />
              {modes.map((mode) => {
                const display = MODE_DISPLAY[mode.id] ?? { label: mode.name, icon: '✦' };
                const isSelected = mode.id === selectedModeId || (!selectedModeId && mode.id === 'safe');
                return (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => { onSelectMode(mode.id); setShowModeMenu(false); }}
                    className={`w-full text-left px-4 py-2.5 text-sm flex items-center gap-3 transition-colors ${
                      isSelected
                        ? 'text-primary bg-primary/5'
                        : 'text-foreground hover:bg-muted/50'
                    }`}
                  >
                    <span className="text-base leading-none">{display.icon}</span>
                    <span className="font-medium">{display.label}</span>
                    {isSelected && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Auto-resizing textarea */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={selectedMode && selectedMode.label !== 'Chat' ? `${selectedMode.label}: ask anything…` : 'Ask anything…'}
          disabled={loading}
          className="flex-1 bg-transparent outline-none text-foreground placeholder:text-muted-foreground text-sm py-1 resize-none overflow-hidden leading-relaxed"
          style={{ maxHeight: '200px', overflowY: 'auto' }}
        />

        {/* Hidden file input - triggered from + menu */}
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          onChange={handleFileChange}
          className="hidden"
          disabled={uploading}
        />

        {/* Send */}
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="w-8 h-8 flex items-center justify-center bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 hover:scale-105 active:scale-95 disabled:opacity-40 disabled:scale-100 transition-all shrink-0 self-end"
        >
          {loading
            ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            : <svg className="w-4 h-4 translate-x-px" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
          }
        </button>
      </form>
    </div>
  );

  // ─── Empty state ─────────────────────────────────────────────────────────
  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center w-full h-full animate-fade-in">
        <div className="w-full max-w-3xl px-6 flex flex-col items-center gap-10">
          <h1 className="text-3xl font-normal text-foreground text-center tracking-tight leading-snug">
            What's on your mind?
          </h1>
          {inputBar}
        </div>
      </div>
    );
  }

  // ─── Active state ─────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex-1 overflow-y-auto p-6 flex flex-col">
        {/* spacer pushes messages to the bottom when chat is short */}
        <div className="flex-1" />
        <div className="max-w-3xl mx-auto w-full space-y-4">
          {messages.map((message) => {
            const isUser = message.role === 'user';
            const msgSources = ragSourcesMap[message.id] || [];
            const msgWebSources = webSourcesMap[message.id] || [];
            const ragUsed = !!ragUsedMap[message.id] || msgSources.length > 0;

            return (
              <div
                key={message.id}
                className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in`}
              >
                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-2.5 shadow-sm ${
                    isUser
                      ? 'bg-gradient-to-br from-primary to-violet-600 text-white rounded-tr-sm'
                      : 'bg-card border border-border text-foreground rounded-tl-sm'
                  }`}
                >
                  <div className="prose prose-sm max-w-none text-sm leading-relaxed prose-invert">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        p: (props) => <p className="mb-2 last:mb-0" {...props} />,
                        strong: (props) => <strong className="font-semibold" {...props} />,
                        ul: (props) => <ul className="list-disc pl-4 mb-2 space-y-1" {...props} />,
                        ol: (props) => <ol className="list-decimal pl-4 mb-2 space-y-1" {...props} />,
                        li: (props) => <li className="leading-relaxed" {...props} />,
                        code: (props) => <code className="bg-white/10 rounded px-1 py-0.5 text-xs font-mono" {...props} />,
                        pre: (props) => <pre className="bg-white/10 rounded-lg p-3 overflow-x-auto text-xs font-mono mb-2" {...props} />,
                        h1: (props) => <h1 className="text-base font-bold mb-2" {...props} />,
                        h2: (props) => <h2 className="text-sm font-bold mb-1.5" {...props} />,
                        h3: (props) => <h3 className="text-sm font-semibold mb-1" {...props} />,
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                  {!isUser && <RAGSourceBadge ragUsed={ragUsed} sources={msgSources} />}
                  {!isUser && <WebSourceBadge sources={msgWebSources} />}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input pinned at bottom */}
      <div className="p-4 bg-background shrink-0">
        <div className="max-w-3xl mx-auto">
          {inputBar}
        </div>
      </div>
    </div>
  );
}
