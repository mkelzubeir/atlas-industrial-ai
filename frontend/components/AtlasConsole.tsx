"use client";

import { useConversation } from "@elevenlabs/react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AuditEntry, ActivityEntry, ToolEvent, TranscriptEntry } from "@/lib/types";
import styles from "./console.module.css";
import { DeveloperView } from "./DeveloperView";
import { Transcript } from "./Transcript";
import { VoiceOrb } from "./VoiceOrb";

const STATUS_LABEL: Record<string, string> = {
  disconnected: "Not connected",
  connecting: "Connecting",
  connected: "Connected",
  error: "Connection error",
};

let sequence = 0;
const nextId = (prefix: string) => `${prefix}-${++sequence}`;

export function AtlasConsole({ agentId }: { agentId: string }) {
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEntry[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<Record<string, string | undefined>>({});
  const [devOpen, setDevOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [level, setLevel] = useState(0);

  // Maps an ElevenLabs tool_call_id to our local event id, so a response can be
  // matched to the request that opened it.
  const callIndex = useRef(new Map<string, string>());

  const conversation = useConversation({
    onConnect: ({ conversationId: id }) => {
      setConversationId(id);
      setNotice(null);
    },
    onDisconnect: () => {
      setLevel(0);
    },
    onError: (message) => {
      setNotice(message || "The call ended unexpectedly.");
    },
    onMessage: ({ message, source }) => {
      if (!message?.trim()) return;
      setTranscript((prev) => [
        ...prev,
        {
          id: nextId("turn"),
          speaker: source === "ai" ? "agent" : "customer",
          text: message,
          at: Date.now(),
        },
      ]);
    },
    onAgentToolRequest: ({ tool_name, tool_call_id, tool_type }) => {
      const id = nextId("tool");
      callIndex.current.set(tool_call_id, id);
      setToolEvents((prev) => [
        ...prev,
        {
          id,
          toolName: tool_name,
          toolType: tool_type,
          status: "running",
          requestedAt: Date.now(),
        },
      ]);
    },
    onAgentToolResponse: (payload) => {
      const id = callIndex.current.get(payload.tool_call_id);
      const result =
        "full_tool_result" in payload ? (payload.full_tool_result as string) : undefined;

      setToolEvents((prev) =>
        prev.map((event) => {
          if (event.id !== id) return event;
          const completedAt = Date.now();
          return {
            ...event,
            status: payload.is_error ? "error" : "ok",
            completedAt,
            durationMs: completedAt - event.requestedAt,
            result: result ?? event.result,
          };
        }),
      );

      if (result) captureSessionState(payload.tool_name, result, setSessionState);
    },
  });

  const { status, isSpeaking, startSession, endSession, getOutputByteFrequencyData } = conversation;
  const connected = status === "connected";

  // ---- output level, for the orb -----------------------------------------
  useEffect(() => {
    if (!connected || !isSpeaking) {
      setLevel(0);
      return;
    }
    let frame = 0;
    const tick = () => {
      try {
        const data = getOutputByteFrequencyData();
        if (data?.length) {
          let sum = 0;
          for (let i = 0; i < data.length; i += 1) sum += data[i];
          setLevel(sum / data.length / 255);
        }
      } catch {
        /* the analyser is gone once the call ends; ignore */
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [connected, isSpeaking, getOutputByteFrequencyData]);

  // ---- merge backend-side tool arguments ---------------------------------
  // The client SDK never sees the arguments the agent chose, so they are polled
  // from the backend and matched to client events by tool name, in call order.
  useEffect(() => {
    if (!connected || !conversationId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const [activityRes, auditRes] = await Promise.all([
          fetch(`/api/atlas/demo/activity?conversation_id=${encodeURIComponent(conversationId)}`),
          fetch("/api/atlas/demo/audit?limit=25"),
        ]);
        if (cancelled) return;

        if (activityRes.ok) {
          const { entries } = (await activityRes.json()) as { entries: ActivityEntry[] };
          setToolEvents((prev) => mergeActivity(prev, entries));
        }
        if (auditRes.ok) {
          const { events } = (await auditRes.json()) as { events: AuditEntry[] };
          setAuditEvents(events.filter((e) => e.conversation_id === conversationId).reverse());
        }
      } catch {
        /* the Developer View is best-effort; never break the call for it */
      }
    };

    void poll();
    const timer = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [connected, conversationId]);

  // ---- call control -------------------------------------------------------
  const start = useCallback(async () => {
    setStarting(true);
    setNotice(null);
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setNotice("Microphone access is required to start a call.");
      setStarting(false);
      return;
    }

    try {
      const response = await fetch("/api/conversation-token", { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Could not start the session.");

      setTranscript([]);
      setToolEvents([]);
      setAuditEvents([]);
      setSessionState({});
      callIndex.current.clear();

      if (body.token) {
        startSession({ conversationToken: body.token, connectionType: "webrtc" });
      } else {
        startSession({ agentId: body.agentId, connectionType: "webrtc" });
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not start the session.");
    } finally {
      setStarting(false);
    }
  }, [startSession]);

  const resetDemo = useCallback(async () => {
    if (!window.confirm("Restore all Atlas demo data to its seeded state?")) return;
    try {
      const response = await fetch("/api/atlas/demo/reset", { method: "POST" });
      const body = await response.json();
      setNotice(
        response.ok
          ? "Demo data restored to its seeded state."
          : (body?.error?.message ?? "Could not reset the demo data."),
      );
      setAuditEvents([]);
    } catch {
      setNotice("Could not reach the Atlas backend to reset it.");
    }
  }, []);

  const missingAgent = !agentId;

  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <header className={styles.header}>
          <div>
            <div className={styles.brand}>Atlas Industrial Supply</div>
            <h1 className={styles.title}>AI Customer Service</h1>
          </div>
          <span className={[styles.status, connected ? styles.statusLive : ""].join(" ")}>
            <span className={styles.statusDot} />
            {STATUS_LABEL[status] ?? status}
          </span>
        </header>

        <p className={styles.lede}>
          Talk to Atlas about purchase orders, stock availability and quote requests. The agent
          works against live order and inventory APIs — it retrieves what it tells you.
        </p>

        <section className={styles.stage}>
          <VoiceOrb status={status} isSpeaking={isSpeaking} level={level} />

          <div className={styles.controls}>
            {connected ? (
              <button className={styles.buttonDanger} onClick={() => endSession()}>
                End call
              </button>
            ) : (
              <button
                className={styles.buttonPrimary}
                onClick={start}
                disabled={starting || status === "connecting" || missingAgent}
              >
                {starting || status === "connecting" ? "Connecting…" : "Start call"}
              </button>
            )}
          </div>

          <p className={styles.hint}>
            {missingAgent
              ? "Set NEXT_PUBLIC_ELEVENLABS_AGENT_ID in frontend/.env.local to enable calling."
              : connected
                ? isSpeaking
                  ? "Atlas is speaking"
                  : "Listening"
                : "Try: “I'm calling about PO 1847 — are the M8 bolts still shipping Friday?”"}
          </p>
        </section>

        {notice && <div className={styles.notice}>{notice}</div>}

        <Transcript entries={transcript} />

        <div className={styles.footer}>
          <button
            className={styles.buttonQuiet}
            onClick={() => setDevOpen((open) => !open)}
            aria-expanded={devOpen}
          >
            {devOpen ? "Hide" : "Show"} developer view
            {toolEvents.length > 0 && <span className={styles.pill}>{toolEvents.length}</span>}
          </button>
          <button className={styles.buttonQuiet} onClick={resetDemo}>
            Reset demo data
          </button>
        </div>

        {devOpen && (
          <DeveloperView
            conversationId={conversationId}
            toolEvents={toolEvents}
            auditEvents={auditEvents}
            sessionState={sessionState}
          />
        )}

        <p className={styles.disclaimer}>
          Atlas Industrial Supply is fictional. Every customer, product, order, price and API
          behind this demo is synthetic.
        </p>
      </div>
    </main>
  );
}

/**
 * Pull the conversation's working context out of tool results.
 *
 * The agent tracks the same things through ElevenLabs dynamic variables; this
 * is the UI's own read of them, so the panel can show what the call is
 * currently "about" without the agent having to report it.
 */
function captureSessionState(
  toolName: string,
  rawResult: string,
  set: React.Dispatch<React.SetStateAction<Record<string, string | undefined>>>,
) {
  try {
    const parsed = JSON.parse(rawResult) as Record<string, never>;
    if (parsed.error) return;

    if (toolName === "lookup_order" && parsed.po_number) {
      const customer = parsed.customer as { company_name?: string; account_number?: string } | undefined;
      set((prev) => ({
        ...prev,
        active_po_number: String(parsed.po_number),
        order_status: parsed.status ? String(parsed.status) : prev.order_status,
        customer: customer?.company_name ?? prev.customer,
        customer_account: customer?.account_number ?? prev.customer_account,
      }));
    }
    if (toolName === "create_rfq" && parsed.rfq_number) {
      set((prev) => ({ ...prev, active_rfq_number: String(parsed.rfq_number) }));
    }
    if (toolName === "search_customer") {
      const customers = parsed.customers as
        | Array<{ company_name?: string; account_number?: string }>
        | undefined;
      if (customers?.length === 1) {
        set((prev) => ({
          ...prev,
          customer: customers[0].company_name ?? prev.customer,
          customer_account: customers[0].account_number ?? prev.customer_account,
        }));
      }
    }
  } catch {
    /* not JSON; nothing to capture */
  }
}

/** Attach backend-observed arguments to the matching client-side tool events. */
function mergeActivity(events: ToolEvent[], entries: ActivityEntry[]): ToolEvent[] {
  const unclaimed = new Map<string, ActivityEntry[]>();
  for (const entry of entries) {
    if (!entry.tool) continue;
    const bucket = unclaimed.get(entry.tool) ?? [];
    bucket.push(entry);
    unclaimed.set(entry.tool, bucket);
  }

  const used = new Set<number>();
  return events.map((event) => {
    if (event.params) return event;
    const candidates = unclaimed.get(event.toolName);
    const match = candidates?.find((entry) => !used.has(entry.seq));
    if (!match) return event;
    used.add(match.seq);
    return {
      ...event,
      params: match.params,
      httpStatus: match.status_code,
      errorCode: match.error_code ?? undefined,
      method: match.method,
      path: match.path,
    };
  });
}
