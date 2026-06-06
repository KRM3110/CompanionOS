// components/RAGSourceBadge.tsx
'use client';

import { RAGSource } from '@/lib/types';

interface RAGSourceBadgeProps {
  /** True when the assistant message was grounded by RAG document context */
  ragUsed: boolean;
  sources?: RAGSource[];
}

/**
 * Small inline badge shown below assistant messages when the reply used
 * retrieved document context from the active workspace.
 */
export default function RAGSourceBadge({ ragUsed, sources = [] }: RAGSourceBadgeProps) {
  if (!ragUsed) return null;

  return (
    <div className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">
      <details className="group">
        <summary className="flex cursor-pointer items-center gap-1.5 list-none">
          <svg
            className="w-3 h-3 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <span className="font-medium">
            Grounded from workspace documents
            {sources.length > 0 ? ` (${sources.length})` : ""}
          </span>
        </summary>
        {sources.length > 0 && (
          <div className="mt-1.5 space-y-1 border-l border-emerald-500/30 pl-2">
            {sources.map((src, idx) => (
              <div key={`${src.document_id}-${src.chunk_index}-${idx}`} className="text-[11px]">
                <p className="font-semibold text-emerald-800 dark:text-emerald-200">
                  {src.filename}
                </p>
                <p className="text-emerald-700/90 dark:text-emerald-300/90">{src.snippet}</p>
              </div>
            ))}
          </div>
        )}
      </details>
    </div>
  );
}
