"use client";

import { useState } from "react";

import type { AuditEntry, ToolEvent } from "@/lib/types";
import styles from "./console.module.css";

interface DeveloperViewProps {
  conversationId: string | null;
  toolEvents: ToolEvent[];
  auditEvents: AuditEntry[];
  sessionState: Record<string, string | undefined>;
}

function formatParams(params: Record<string, unknown> | undefined): string {
  if (!params || Object.keys(params).length === 0) return "";
  return Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(", ");
}

function summarise(event: ToolEvent): string {
  if (event.status === "running") return "waiting for Atlas…";
  if (event.errorCode) return event.errorCode;
  if (!event.result) return event.status === "ok" ? "returned" : "failed";

  try {
    const parsed = JSON.parse(event.result) as Record<string, unknown>;
    if (parsed.error && typeof parsed.error === "object") {
      const err = parsed.error as { code?: string; message?: string };
      return err.code ?? err.message ?? "error";
    }
    // A few hand-picked summaries; anything else falls back to the key list.
    if ("po_number" in parsed && "line_count" in parsed) {
      return `order ${parsed.po_number}, status ${parsed.status}, ${parsed.line_count} lines`;
    }
    if ("match_count" in parsed) {
      return `${parsed.match_count} match(es), resolved=${parsed.resolved}`;
    }
    if ("quantity_available" in parsed) {
      return `${parsed.quantity_available} available${
        parsed.can_fulfil === undefined ? "" : `, can_fulfil=${parsed.can_fulfil}`
      }`;
    }
    if ("rfq_number" in parsed) return `created ${parsed.rfq_number}`;
    if ("new_quantity" in parsed) {
      return `line ${parsed.line_number}: ${parsed.previous_quantity} → ${parsed.new_quantity}`;
    }
    return Object.keys(parsed).slice(0, 4).join(", ");
  } catch {
    return event.result.slice(0, 80);
  }
}

export function DeveloperView({
  conversationId,
  toolEvents,
  auditEvents,
  sessionState,
}: DeveloperViewProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const stateEntries = Object.entries(sessionState).filter(([, v]) => v);

  return (
    <div className={styles.devPanel}>
      <section className={styles.devSection}>
        <h3 className={styles.devHeading}>Session</h3>
        <dl className={styles.devState}>
          <div className={styles.devStateRow}>
            <dt>conversation</dt>
            <dd className={styles.mono}>{conversationId ?? "—"}</dd>
          </div>
          {stateEntries.length === 0 ? (
            <div className={styles.devStateRow}>
              <dt>context</dt>
              <dd className={styles.devFaint}>nothing established yet</dd>
            </div>
          ) : (
            stateEntries.map(([key, value]) => (
              <div key={key} className={styles.devStateRow}>
                <dt>{key}</dt>
                <dd className={styles.mono}>{value}</dd>
              </div>
            ))
          )}
        </dl>
      </section>

      <section className={styles.devSection}>
        <h3 className={styles.devHeading}>
          Tool calls <span className={styles.devCount}>{toolEvents.length}</span>
        </h3>
        {toolEvents.length === 0 ? (
          <p className={styles.devFaint}>No tools called yet.</p>
        ) : (
          <ol className={styles.toolList}>
            {toolEvents.map((event) => {
              const isOpen = expanded === event.id;
              const params = formatParams(event.params);
              return (
                <li key={event.id} className={styles.toolItem}>
                  <button
                    className={styles.toolHeader}
                    onClick={() => setExpanded(isOpen ? null : event.id)}
                    aria-expanded={isOpen}
                  >
                    <span
                      className={[
                        styles.dot,
                        event.status === "ok" ? styles.dotOk : "",
                        event.status === "error" ? styles.dotError : "",
                        event.status === "running" ? styles.dotRunning : "",
                      ].join(" ")}
                    />
                    <span className={styles.toolName}>{event.toolName}</span>
                    {params && <span className={styles.toolParams}>({params})</span>}
                    {event.durationMs !== undefined && (
                      <span className={styles.toolDuration}>{Math.round(event.durationMs)}ms</span>
                    )}
                  </button>
                  <p className={styles.toolSummary}>{summarise(event)}</p>
                  {isOpen && (
                    <pre className={styles.toolRaw}>
                      {(() => {
                        try {
                          return JSON.stringify(JSON.parse(event.result ?? "{}"), null, 2);
                        } catch {
                          return event.result ?? "(no body)";
                        }
                      })()}
                    </pre>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section className={styles.devSection}>
        <h3 className={styles.devHeading}>
          State changes <span className={styles.devCount}>{auditEvents.length}</span>
        </h3>
        {auditEvents.length === 0 ? (
          <p className={styles.devFaint}>
            No writes attempted. Reads never change Atlas records.
          </p>
        ) : (
          <ul className={styles.auditList}>
            {auditEvents.map((event) => (
              <li key={event.id} className={styles.auditItem}>
                <span
                  className={[
                    styles.badge,
                    event.outcome === "success" ? styles.badgeOk : styles.badgeRejected,
                  ].join(" ")}
                >
                  {event.outcome}
                </span>
                <span className={styles.mono}>{event.event_type}</span>
                <span className={styles.devFaint}> {event.entity_id}</span>
                {event.outcome === "rejected" && (
                  <div className={styles.auditReason}>
                    refused by the API: {String(event.payload.rejection_code ?? "")}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
