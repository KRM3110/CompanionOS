// components/AlertsPanel.tsx
'use client';

import { Alert } from '@/lib/types';
import { useState } from 'react';

interface AlertsPanelProps {
  alerts: Alert[];
  onUpdateAlert: (alertId: string, status: 'done' | 'cancelled') => void;
  onRefresh: (status: string) => void;
  onClose: () => void;
  loading: boolean;
}

export default function AlertsPanel({
  alerts,
  onUpdateAlert,
  onRefresh,
  onClose,
  loading,
}: AlertsPanelProps) {
  const [filter, setFilter] = useState<string>('active');

  const handleFilterChange = (newFilter: string) => {
    setFilter(newFilter);
    onRefresh(newFilter);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'border-l-red-500/70 bg-red-500/5';
      case 'medium':
        return 'border-l-amber-500/70 bg-amber-500/5';
      case 'low':
        return 'border-l-violet-500/60 bg-violet-500/5';
      default:
        return 'border-l-slate-500/40 bg-slate-500/5';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-amber-500/10 text-amber-300 border border-amber-500/20';
      case 'done':
        return 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20';
      case 'cancelled':
        return 'bg-muted/40 text-muted-foreground border border-border';
      default:
        return 'bg-muted/40 text-muted-foreground border border-border';
    }
  };

  return (
    <div className="flex flex-col h-full bg-transparent">
      {/* Header */}
      <div className="p-6 border-b border-border bg-muted/20 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-foreground">Alerts</h2>
          <button
            onClick={onClose}
            className="p-1 [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-muted active:scale-95 transition-[background-color,color,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
            title="Close Panel"
            aria-label="Close alerts panel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="relative">
          <select
            value={filter}
            onChange={(e) => handleFilterChange(e.target.value)}
            aria-label="Filter alerts by status"
            className="w-full px-4 py-2 bg-background border border-border rounded-lg text-sm text-foreground appearance-none focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer hover:border-primary/30 transition-colors"
          >
            <option value="active">Active Alerts</option>
            <option value="done">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="all">All Alerts</option>
          </select>
          <div className="absolute inset-y-0 right-0 flex items-center px-3 pointer-events-none text-muted-foreground">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </div>

      {/* Alerts List */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {loading ? (
          <div className="flex justify-center p-8">
            <span className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : alerts.length === 0 ? (
          <div className="text-center p-8 border-2 border-dashed border-border rounded-xl">
            <p className="text-muted-foreground text-sm">No alerts found</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`border border-border rounded-xl p-4 shadow-sm hover:shadow-md border-l-2 group bg-card transition-[box-shadow,border-color,background-color] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] ${getPriorityColor(alert.priority)}`}
            >
              <div className="flex items-start justify-between mb-3">
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${getStatusBadge(
                    alert.status
                  )}`}
                >
                  {alert.status}
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors duration-150">
                  {alert.priority} priority
                </span>
              </div>

              <p className="text-sm text-foreground font-medium mb-4 leading-relaxed">{alert.content}</p>

              <div className="flex items-center justify-between mt-auto">
                <span className="text-[10px] text-muted-foreground">
                  {new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>

                {alert.status === 'active' && (
                  <div className="flex gap-1">
                    <button
                      onClick={() => onUpdateAlert(alert.id, 'done')}
                      className="p-1.5 [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11 flex items-center justify-center text-emerald-400 hover:bg-emerald-500/10 active:scale-95 rounded-md transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
                      title="Mark done"
                      aria-label="Mark alert done"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                    </button>
                    <button
                      onClick={() => onUpdateAlert(alert.id, 'cancelled')}
                      className="p-1.5 [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:min-w-11 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/50 active:scale-95 rounded-md transition-[background-color,color,transform] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)]"
                      title="Cancel"
                      aria-label="Cancel alert"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}