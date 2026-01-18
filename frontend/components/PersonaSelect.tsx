// components/PersonaSelect.tsx
'use client';

import { Persona } from '@/lib/types';

interface PersonaSelectProps {
  personas: Persona[];
  selectedPersonaId: string | null;
  onSelect: (personaId: string) => void;
  onStartSession: () => void;
  loading: boolean;
  hasActiveSession: boolean;
}

export default function PersonaSelect({
  personas,
  selectedPersonaId,
  onSelect,
  onStartSession,
  loading,
  hasActiveSession,
}: PersonaSelectProps) {
  const selectedPersona = personas.find((p) => p.id === selectedPersonaId);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Select Persona
        </label>
        <div className="relative">
          <select
            value={selectedPersonaId || ''}
            onChange={(e) => onSelect(e.target.value)}
            className="w-full px-4 py-3 bg-card border border-border rounded-lg text-foreground appearance-none focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all duration-200 cursor-pointer hover:border-primary/50"
            disabled={loading || hasActiveSession}
          >
            <option value="">Choose a persona...</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.name}
              </option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-0 flex items-center px-4 pointer-events-none text-muted-foreground">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </div>

      {selectedPersona && (
        <div className="bg-card p-5 rounded-xl border border-border shadow-sm border-l-4 border-l-primary animate-slide-in">
          <h3 className="font-bold text-lg text-foreground mb-2 flex items-center gap-2">
            {selectedPersona.name}
          </h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{selectedPersona.description}</p>
        </div>
      )}

      {!hasActiveSession && (
        <button
          onClick={onStartSession}
          disabled={!selectedPersonaId || loading}
          className="w-full px-6 py-3 bg-primary text-primary-foreground font-medium rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-md hover:shadow-lg disabled:shadow-none active:scale-[0.98]"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Starting...
            </span>
          ) : (
            'Start Session'
          )}
        </button>
      )}

      {hasActiveSession && (
        <div className="flex items-center gap-2 text-sm text-green-600 font-medium p-3 bg-green-50 border border-green-100 rounded-lg">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
          </span>
          Session Active
        </div>
      )}
    </div>
  );
}