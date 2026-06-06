// components/WebSourceBadge.tsx
'use client';

import { WebSource } from '@/lib/types';

interface WebSourceBadgeProps {
  sources: WebSource[];
}

export default function WebSourceBadge({ sources }: WebSourceBadgeProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 text-xs text-blue-400">
      <details className="group">
        <summary className="flex cursor-pointer items-center gap-1.5 list-none select-none hover:text-blue-300 transition-colors">
          <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" />
          </svg>
          <span className="font-medium">{sources.length} web sources</span>
          <svg className="w-3 h-3 ml-auto group-open:rotate-180 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </summary>

        <div className="mt-2 space-y-1.5 border-l border-blue-500/20 pl-3">
          {sources.map((src, idx) => (
            <a
              key={idx}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block group/link hover:bg-blue-500/5 rounded px-1.5 py-1 -mx-1.5 transition-colors"
            >
              <p className="font-medium text-blue-300 group-hover/link:text-blue-200 truncate leading-tight">
                {idx + 1}. {src.title || src.url}
              </p>
              {src.snippet && (
                <p className="text-blue-400/70 text-[11px] mt-0.5 line-clamp-2 leading-relaxed">
                  {src.snippet}
                </p>
              )}
              <p className="text-blue-500/50 text-[10px] mt-0.5 truncate">{src.url}</p>
            </a>
          ))}
        </div>
      </details>
    </div>
  );
}
