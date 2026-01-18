// components/ChatWindow.tsx
'use client';

import { Message, JudgeVerdict } from '@/lib/types';
import { useState, useRef, useEffect } from 'react';

interface ChatWindowProps {
  messages: Message[];
  onSendMessage: (message: string) => void;
  loading: boolean;
  sessionActive: boolean;
  judgeVerdicts: Record<string, JudgeVerdict>;
}

export default function ChatWindow({
  messages,
  onSendMessage,
  loading,
  sessionActive,
  judgeVerdicts,
}: ChatWindowProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !loading) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case 'PASS':
        return 'bg-green-100 text-green-700 border-green-200';
      case 'REWRITE':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      case 'BLOCK':
        return 'bg-red-100 text-red-700 border-red-200';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  if (!sessionActive) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center p-8 max-w-md animate-slide-in">
          <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-muted-foreground/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <p className="text-xl font-medium text-foreground">No active session</p>
          <p className="text-sm mt-2 opacity-80">Select a persona from the sidebar to begin your journey.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-background/50">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          <div className="text-center text-muted-foreground mt-12 animate-slide-in opacity-0" style={{ animationFillMode: 'forwards' }}>
            <p className="text-sm font-medium">Start the conversation...</p>
          </div>
        ) : (
          messages.map((message) => {
            const verdict = judgeVerdicts[message.id];
            const isUser = message.role === 'user';

            return (
              <div
                key={message.id}
                className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} animate-slide-in`}
              >
                <div
                  className={`max-w-[75%] rounded-2xl px-5 py-3 shadow-sm transition-all duration-200 hover:shadow-md ${isUser
                    ? 'bg-gradient-to-br from-primary to-violet-600 text-white rounded-tr-sm'
                    : 'bg-card border border-border text-foreground rounded-tl-sm'
                    }`}
                >
                  <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>


                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-background/80 backdrop-blur-md border-t border-border">
        <form onSubmit={handleSubmit} className="flex gap-3 max-w-4xl mx-auto items-center">
          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              disabled={loading}
              className="w-full pl-5 pr-4 py-3.5 bg-muted/50 border border-transparent focus:bg-background focus:border-border rounded-full outline-none focus:ring-4 focus:ring-primary/10 transition-all shadow-inner"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="p-3.5 bg-primary text-primary-foreground rounded-full hover:bg-primary/90 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:scale-100 disabled:hover:bg-primary transition-all shadow-md"
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-5 h-5 translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}