"use client";

import { useEffect, useRef } from "react";

import type { TranscriptEntry } from "@/lib/types";
import styles from "./console.module.css";

export function Transcript({ entries }: { entries: TranscriptEntry[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries.length]);

  if (entries.length === 0) {
    return (
      <p className={styles.transcriptEmpty}>
        The conversation will appear here as you talk.
      </p>
    );
  }

  return (
    <div className={styles.transcript} role="log" aria-live="polite" aria-label="Call transcript">
      {entries.map((entry) => (
        <div key={entry.id} className={styles.turn}>
          <span
            className={[
              styles.speaker,
              entry.speaker === "agent" ? styles.speakerAgent : styles.speakerCustomer,
            ].join(" ")}
          >
            {entry.speaker === "agent" ? "Atlas" : "You"}
          </span>
          <p className={styles.turnText}>{entry.text}</p>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
