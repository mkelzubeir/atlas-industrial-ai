"use client";

import { useEffect, useMemo, useState } from "react";

import type { DatabaseSnapshot, SnapshotOrder, SnapshotProduct } from "@/lib/types";
import styles from "./console.module.css";

type Tab = "orders" | "products" | "customers";

const TABS: { id: Tab; label: string }[] = [
  { id: "orders", label: "Orders" },
  { id: "products", label: "Products" },
  { id: "customers", label: "Customers" },
];

/**
 * A read-only window onto the synthetic environment.
 *
 * Without this the demo is a guessing game — nobody can know that PO 1847
 * exists, that PO 1260 has shipped and will refuse changes, or that "M8
 * stainless screws" deliberately matches four products. Seeing the data is what
 * makes the agent's behaviour legible: you can check what it told you.
 */
export function DemoDataPanel({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<DatabaseSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("orders");
  const [openOrder, setOpenOrder] = useState<string | null>("1847");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/atlas/demo/database", { cache: "no-store" });
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          setError(body?.error?.message ?? "Could not load the demo data.");
          return;
        }
        setData(body as DatabaseSnapshot);
        setError(null);
      } catch {
        if (!cancelled) setError("Could not reach the Atlas backend.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const productsByCategory = useMemo(() => {
    if (!data) return [];
    const needle = filter.trim().toLowerCase();
    const matches = data.products.filter(
      (p) =>
        !needle ||
        p.name.toLowerCase().includes(needle) ||
        p.sku.toLowerCase().includes(needle) ||
        p.category.toLowerCase().includes(needle),
    );
    const grouped = new Map<string, SnapshotProduct[]>();
    for (const product of matches) {
      grouped.set(product.category, [...(grouped.get(product.category) ?? []), product]);
    }
    return [...grouped.entries()];
  }, [data, filter]);

  if (error) {
    return <div className={styles.dataPanel}><p className={styles.devFaint}>{error}</p></div>;
  }
  if (!data) {
    return <div className={styles.dataPanel}><p className={styles.devFaint}>Loading demo data…</p></div>;
  }

  return (
    <div className={styles.dataPanel}>
      <div className={styles.dataIntro}>
        <p className={styles.dataIntroText}>
          This is the entire synthetic world the agent can see. Everything here is fictional —
          use it to pick something real to ask about, then check the answer against these records.
        </p>
        <ul className={styles.suggestList}>
          <li>
            <strong>“I’m calling about PO 1847 — are the M8 bolts still shipping Friday?”</strong>{" "}
            a straight lookup
          </li>
          <li>
            <strong>“Reduce the washers on 1847 to 200.”</strong> a write — it will ask you to
            confirm first
          </li>
          <li>
            <strong>“Change the quantity on PO 1260.”</strong> already shipped, so the API refuses
          </li>
          <li>
            <strong>“Do you have M8 stainless screws?”</strong> four products match, so it has to
            ask which
          </li>
          <li>
            <strong>“Quote me 300 of the 6206 bearings.”</strong> out of stock, with a restock date
          </li>
        </ul>
      </div>

      <div className={styles.tabRow} role="tablist">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={[styles.tab, tab === id ? styles.tabActive : ""].join(" ")}
            onClick={() => setTab(id)}
          >
            {label}
            <span className={styles.tabCount}>{data.counts[id]}</span>
          </button>
        ))}
      </div>

      {tab === "orders" && (
        <div className={styles.dataBody}>
          {data.orders.map((order) => (
            <OrderRow
              key={order.po_number}
              order={order}
              open={openOrder === order.po_number}
              onToggle={() =>
                setOpenOrder(openOrder === order.po_number ? null : order.po_number)
              }
            />
          ))}
        </div>
      )}

      {tab === "products" && (
        <div className={styles.dataBody}>
          <input
            className={styles.filterInput}
            placeholder="Filter by name, SKU or category…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {productsByCategory.map(([category, products]) => (
            <section key={category} className={styles.categoryBlock}>
              <h4 className={styles.categoryHeading}>{category}</h4>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>Product</th>
                    <th className={styles.numeric}>Price</th>
                    <th className={styles.numeric}>Available</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.sku}>
                      <td className={styles.mono}>{product.sku}</td>
                      <td>
                        {product.name}
                        {product.expected_restock_date && (
                          <span className={styles.restock}>
                            restock {product.expected_restock_date}
                          </span>
                        )}
                      </td>
                      <td className={styles.numeric}>${product.unit_price.toFixed(2)}</td>
                      <td
                        className={[
                          styles.numeric,
                          product.quantity_available === 0 ? styles.zeroStock : "",
                        ].join(" ")}
                      >
                        {product.quantity_available.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
          {productsByCategory.length === 0 && (
            <p className={styles.devFaint}>No products match “{filter}”.</p>
          )}
        </div>
      )}

      {tab === "customers" && (
        <div className={styles.dataBody}>
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>Account</th>
                <th>Company</th>
                <th>Contact</th>
                <th className={styles.numeric}>Orders</th>
              </tr>
            </thead>
            <tbody>
              {data.customers.map((customer) => (
                <tr key={customer.account_number}>
                  <td className={styles.mono}>{customer.account_number}</td>
                  <td>
                    {customer.company_name}
                    {customer.status === "on_hold" && (
                      <span className={styles.holdBadge}>credit hold</span>
                    )}
                  </td>
                  <td>{customer.contact_name}</td>
                  <td className={styles.numeric}>{customer.order_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** "ships Friday" for something still to come, "shipped Tuesday" once it has gone. */
function shipmentVerb(status: string): string {
  return status === "pending" ? "ships" : "shipped";
}

function OrderRow({
  order,
  open,
  onToggle,
}: {
  order: SnapshotOrder;
  open: boolean;
  onToggle: () => void;
}) {
  const shipment = order.shipments[0];
  return (
    <div className={styles.orderRow}>
      <button className={styles.orderHeader} onClick={onToggle} aria-expanded={open}>
        <span className={styles.poNumber}>PO {order.po_number}</span>
        <span className={[styles.statusChip, styles[`status_${order.status}`] ?? ""].join(" ")}>
          {order.status}
        </span>
        <span className={styles.orderCompany}>{order.company_name}</span>
        <span className={styles.orderMeta}>
          {order.lines.length} line{order.lines.length === 1 ? "" : "s"}
          {shipment?.estimated_ship_day
            ? ` · ${shipmentVerb(shipment.status)} ${shipment.estimated_ship_day}`
            : ""}
        </span>
      </button>

      {open && (
        <div className={styles.orderDetail}>
          {!order.modifiable && (
            <p className={styles.lockNote}>
              This order is {order.status} — the API will refuse any change to it.
            </p>
          )}
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th className={styles.numeric}>#</th>
                <th>SKU</th>
                <th>Product</th>
                <th className={styles.numeric}>Qty</th>
                <th>Line status</th>
              </tr>
            </thead>
            <tbody>
              {order.lines.map((line) => (
                <tr key={line.line_number}>
                  <td className={styles.numeric}>{line.line_number}</td>
                  <td className={styles.mono}>{line.sku}</td>
                  <td>{line.product_name}</td>
                  <td className={styles.numeric}>{line.quantity.toLocaleString()}</td>
                  <td>
                    {line.status}
                    {!line.modifiable && <span className={styles.lockedTag}>locked</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {order.shipments.map((s, i) => (
            <p key={i} className={styles.shipNote}>
              {s.carrier} · {s.status}
              {s.estimated_ship_date &&
              ` · ${shipmentVerb(s.status)} ${s.estimated_ship_date} (${s.estimated_ship_day})`}
              {s.tracking_number && ` · ${s.tracking_number}`}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
