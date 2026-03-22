/**
 * GuardBadge.tsx — Feature 3: RAG Security / Content Guard
 *
 * Displays a coloured pill badge showing the Content Guard verdict for a document.
 * Props:
 *   verdict: "CLEAN" | "FLAGGED" | "BLOCKED" | null
 *   patternsHit?: string[]  — optional tooltip listing matched pattern categories
 */

import React, { useState } from "react";

type Verdict = "CLEAN" | "FLAGGED" | "BLOCKED";

interface GuardBadgeProps {
  verdict: Verdict | null | undefined;
  patternsHit?: string[];
  className?: string;
}

const BADGE_CONFIG: Record<
  Verdict,
  { label: string; bg: string; text: string; icon: string }
> = {
  CLEAN: {
    label: "Clean",
    bg: "#16a34a",       // green-600
    text: "#ffffff",
    icon: "✓",
  },
  FLAGGED: {
    label: "Flagged",
    bg: "#d97706",       // amber-600
    text: "#ffffff",
    icon: "⚠",
  },
  BLOCKED: {
    label: "Blocked",
    bg: "#dc2626",       // red-600
    text: "#ffffff",
    icon: "✕",
  },
};

export default function GuardBadge({
  verdict,
  patternsHit = [],
  className = "",
}: GuardBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (!verdict) return null;

  const config = BADGE_CONFIG[verdict];
  const hasPatterns = patternsHit.length > 0;

  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <span
        title={
          hasPatterns
            ? `Patterns detected: ${patternsHit.join(", ")}`
            : `Guard verdict: ${verdict}`
        }
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className={className}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "3px",
          padding: "2px 8px",
          borderRadius: "999px",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.04em",
          backgroundColor: config.bg,
          color: config.text,
          cursor: hasPatterns ? "help" : "default",
          userSelect: "none",
          lineHeight: "1.5",
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ fontSize: "10px" }}>{config.icon}</span>
        {config.label}
      </span>

      {/* Tooltip showing matched pattern categories */}
      {showTooltip && hasPatterns && (
        <span
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: "50%",
            transform: "translateX(-50%)",
            backgroundColor: "#1e293b",
            color: "#f1f5f9",
            fontSize: "11px",
            padding: "6px 10px",
            borderRadius: "6px",
            whiteSpace: "nowrap",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
            zIndex: 50,
            pointerEvents: "none",
          }}
        >
          <strong>Patterns hit:</strong>
          <br />
          {patternsHit.map((p) => (
            <span key={p} style={{ display: "block", marginTop: "2px" }}>
              • {p.replace(/_/g, " ")}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
