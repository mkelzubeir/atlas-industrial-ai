/** Shared shapes for the console UI. */

export type Speaker = "customer" | "agent";

export interface TranscriptEntry {
  id: string;
  speaker: Speaker;
  text: string;
  at: number;
}

/**
 * A tool call as observed from the browser.
 *
 * The ElevenLabs client reports the tool name, whether it errored and the raw
 * result, but not the arguments the agent chose — those live only on the
 * backend, and are merged in from /api/atlas/demo/activity by matching on the
 * tool name in call order.
 */
export interface ToolEvent {
  id: string;
  toolName: string;
  toolType: string;
  status: "running" | "ok" | "error";
  requestedAt: number;
  completedAt?: number;
  durationMs?: number;
  result?: string;
  /** Merged from the backend activity feed. */
  params?: Record<string, unknown>;
  httpStatus?: number;
  errorCode?: string;
  method?: string;
  path?: string;
}

export interface ActivityEntry {
  seq: number;
  timestamp: string;
  tool: string | null;
  method: string;
  path: string;
  query: string | null;
  status_code: number;
  ok: boolean;
  duration_ms: number;
  request_id: string;
  conversation_id: string | null;
  params: Record<string, unknown>;
  error_code: string | null;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  outcome: "success" | "rejected";
  source: string;
  conversation_id: string | null;
  payload: Record<string, unknown>;
}
