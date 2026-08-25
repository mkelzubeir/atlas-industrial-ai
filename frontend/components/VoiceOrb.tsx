"use client";

import styles from "./console.module.css";

interface VoiceOrbProps {
  status: "disconnected" | "connecting" | "connected" | "error";
  isSpeaking: boolean;
  /** 0..1 output level, sampled from the SDK's frequency data. */
  level: number;
}

/**
 * The call's state, as one object.
 *
 * Scale is driven by real output amplitude rather than a looping animation, so
 * what you see corresponds to what the agent is actually saying.
 */
export function VoiceOrb({ status, isSpeaking, level }: VoiceOrbProps) {
  const active = status === "connected";
  const scale = active && isSpeaking ? 1 + Math.min(level, 1) * 0.22 : 1;

  return (
    <div className={styles.orbWrap} aria-hidden="true">
      <div
        className={[
          styles.orbRing,
          active ? styles.orbRingActive : "",
          isSpeaking ? styles.orbRingSpeaking : "",
        ].join(" ")}
        style={{ transform: `scale(${scale.toFixed(3)})` }}
      />
      <div
        className={[
          styles.orb,
          active ? styles.orbActive : "",
          status === "connecting" ? styles.orbConnecting : "",
          status === "error" ? styles.orbError : "",
        ].join(" ")}
      />
    </div>
  );
}
