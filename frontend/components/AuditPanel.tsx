/**
 * AuditPanel.tsx — Feature 3: RAG Security / Content Guard
 *
 * Admin view that lists all guard_audit records fetched from GET /security/audit.
 * Supports filtering by verdict (CLEAN / FLAGGED / BLOCKED).
 *
 * Usage:
 *   <AuditPanel apiBase="http://localhost:8000" />
 */

"use client";

import React, { useEffect, useState, useCallback } from "react";
import GuardBadge from "./GuardBadge";

type Verdict = "CLEAN" | "FLAGGED" | "BLOCKED";

interface AuditRecord {
  id: string;
  document_id: string;
  verdict: Verdict;
  patterns_hit: string[];
  llm_reason: string | null;
  scanned_at: string;
}

interface AuditPanelProps {
  apiBase?: string;
}

const VERDICT_FILTERS: Array<Verdict | "ALL"> = ["ALL", "CLEAN", "FLAGGED", "BLOCKED"];

const FILTER_COLORS: Record<Verdict | "ALL", string> = {
  ALL: "#475569",
  CLEAN: "#16a34a",
  FLAGGED: "#d97706",
  BLOCKED: "#dc2626",
};

export default function AuditPanel({
  apiBase = "http://localhost:8000",
}: AuditPanelProps) {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [filter, setFilter] = useState<Verdict | "ALL">("ALL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url =
        filter === "ALL"
          ? `${apiBase}/security/audit`
          : `${apiBase}/security/audit?verdict=${filter}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AuditRecord[] = await res.json();
      setRecords(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load audit records");
    } finally {
      setLoading(false);
    }
  }, [apiBase, filter]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  return (
    <div
      style={{
        background: "#0f172a",
        borderRadius: "12px",
        padding: "20px",
        color: "#e2e8f0",
        fontFamily: "Inter, system-ui, sans-serif",
        minHeight: "200px",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "16px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "#f1f5f9" }}>
          🛡️ Security Audit Log
        </h2>
        <button
          onClick={fetchRecords}
          disabled={loading}
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            color: "#94a3b8",
            borderRadius: "6px",
            padding: "4px 12px",
            fontSize: "12px",
            cursor: "pointer",
          }}
        >
          {loading ? "Refreshing…" : "↻ Refresh"}
        </button>
      </div>

      {/* Filter tabs */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
        {VERDICT_FILTERS.map((v) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            style={{
              background: filter === v ? FILTER_COLORS[v] : "#1e293b",
              color: filter === v ? "#fff" : "#94a3b8",
              border: `1px solid ${filter === v ? FILTER_COLORS[v] : "#334155"}`,
              borderRadius: "999px",
              padding: "4px 14px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {v}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            background: "#450a0a",
            border: "1px solid #dc2626",
            borderRadius: "8px",
            padding: "10px 14px",
            fontSize: "13px",
            color: "#fca5a5",
            marginBottom: "12px",
          }}
        >
          ⚠ {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && records.length === 0 && (
        <div style={{ textAlign: "center", color: "#475569", padding: "32px 0", fontSize: "13px" }}>
          No audit records found{filter !== "ALL" ? ` for verdict "${filter}"` : ""}.
        </div>
      )}

      {/* Records table */}
      {records.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "13px",
            }}
          >
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b", color: "#64748b" }}>
                <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>
                  Verdict
                </th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>
                  Document ID
                </th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>
                  Patterns Hit
                </th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>
                  LLM Reason
                </th>
                <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>
                  Scanned At
                </th>
              </tr>
            </thead>
            <tbody>
              {records.map((rec, i) => (
                <tr
                  key={rec.id}
                  style={{
                    background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
                    borderBottom: "1px solid #1e293b",
                  }}
                >
                  <td style={{ padding: "10px 10px" }}>
                    <GuardBadge verdict={rec.verdict} patternsHit={rec.patterns_hit} />
                  </td>
                  <td
                    style={{
                      padding: "10px 10px",
                      fontFamily: "monospace",
                      color: "#94a3b8",
                      fontSize: "11px",
                      maxWidth: "140px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={rec.document_id}
                  >
                    {rec.document_id}
                  </td>
                  <td style={{ padding: "10px 10px" }}>
                    {rec.patterns_hit.length > 0 ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                        {rec.patterns_hit.map((p) => (
                          <span
                            key={p}
                            style={{
                              background: "#1e293b",
                              border: "1px solid #334155",
                              borderRadius: "4px",
                              padding: "1px 6px",
                              fontSize: "10px",
                              color: "#94a3b8",
                            }}
                          >
                            {p.replace(/_/g, " ")}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: "#475569", fontSize: "11px" }}>—</span>
                    )}
                  </td>
                  <td
                    style={{
                      padding: "10px 10px",
                      color: "#94a3b8",
                      maxWidth: "200px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={rec.llm_reason ?? ""}
                  >
                    {rec.llm_reason ?? <span style={{ color: "#334155" }}>—</span>}
                  </td>
                  <td style={{ padding: "10px 10px", color: "#64748b", whiteSpace: "nowrap" }}>
                    {formatDate(rec.scanned_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
