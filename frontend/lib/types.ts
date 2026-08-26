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


/** Read-only snapshot of the synthetic environment, for the data browser. */

export interface SnapshotLine {
  line_number: number;
  sku: string;
  product_name: string;
  quantity: number;
  unit_of_measure: string;
  status: string;
  modifiable: boolean;
}

export interface SnapshotShipment {
  carrier: string;
  status: string;
  estimated_ship_date: string | null;
  estimated_ship_day: string | null;
  tracking_number: string | null;
  line_numbers: number[];
}

export interface SnapshotOrder {
  po_number: string;
  company_name: string;
  account_number: string;
  status: string;
  modifiable: boolean;
  created_at: string;
  customer_reference: string | null;
  lines: SnapshotLine[];
  shipments: SnapshotShipment[];
}

export interface SnapshotProduct {
  sku: string;
  name: string;
  description: string;
  category: string;
  unit_of_measure: string;
  unit_price: number;
  attributes: Record<string, unknown>;
  quantity_available: number;
  quantity_on_hand: number;
  expected_restock_date: string | null;
}

export interface SnapshotCustomer {
  account_number: string;
  company_name: string;
  contact_name: string;
  email: string;
  phone: string;
  status: string;
  order_count: number;
}

export interface SnapshotRfq {
  rfq_number: string;
  company_name: string;
  status: string;
  source: string;
  created_at: string;
  lines: { sku: string; product_name: string; quantity: number }[];
}

export interface DatabaseSnapshot {
  customers: SnapshotCustomer[];
  orders: SnapshotOrder[];
  products: SnapshotProduct[];
  rfqs: SnapshotRfq[];
  counts: { customers: number; orders: number; products: number; rfqs: number };
}
