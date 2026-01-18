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
        return 'border-l-red-500 bg-red-50/50';
      case 'medium':
        return 'border-l-yellow-500 bg-yellow-50/50';
      case 'low':
        return 'border-l-blue-500 bg-blue-50/50';
      default:
        return 'border-l-gray-300 bg-gray-50/50';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-orange-100 text-orange-700 border border-orange-200';
      case 'done':
        return 'bg-green-100 text-green-700 border border-green-200';
      case 'cancelled':
        return 'bg-muted text-muted-foreground border border-border';
      default:
        return 'bg-muted text-muted-foreground';
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
            className="p-1 hover:bg-muted rounded-full transition-colors text-muted-foreground hover:text-foreground"
            title="Close Panel"
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
              className={`border border-border rounded-xl p-4 shadow-sm hover:shadow-md transition-all duration-200 border-l-[3px] group bg-card ${getPriorityColor(alert.priority)}`}
            >
              <div className="flex items-start justify-between mb-3">
                <span
                  className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${getStatusBadge(
                    alert.status
                  )}`}
                >
                  {alert.status}
                </span>
                <span className="text-xs font-semibold uppercase text-muted-foreground opacity-70 group-hover:opacity-100 transition-opacity">
                  {alert.priority} Priority
                </span>
              </div>

              <p className="text-sm text-foreground font-medium mb-4 leading-relaxed">{alert.content}</p>

              <div className="flex items-center justify-between mt-auto">
                <span className="text-[10px] text-muted-foreground">
                  {new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>

                {alert.status === 'active' && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => onUpdateAlert(alert.id, 'done')}
                      className="p-1.5 text-green-600 hover:bg-green-100 rounded-md transition-colors"
                      title="Mark Done"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                    </button>
                    <button
                      onClick={() => onUpdateAlert(alert.id, 'cancelled')}
                      className="p-1.5 text-gray-500 hover:bg-gray-100 rounded-md transition-colors"
                      title="Cancel"
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