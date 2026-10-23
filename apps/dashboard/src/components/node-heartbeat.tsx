"use client";

import { useEffect, useState } from "react";
import { localTime } from "../lib/contracts";

export const HEARTBEAT_WINDOW_MS = 60_000;

export function recordHeartbeat(
  previous: readonly number[],
  at: string | null,
): number[] {
  const timestamp = at ? Date.parse(at) : NaN;
  if (!Number.isFinite(timestamp) || previous.includes(timestamp))
    return [...previous];
  const latest = Math.max(timestamp, ...previous);
  return [...previous, timestamp]
    .filter((beat) => latest - beat <= HEARTBEAT_WINDOW_MS)
    .sort((a, b) => a - b)
    .slice(-64);
}

export function heartbeatPath(
  receipts: readonly number[],
  now: number,
): string {
  let path = "M0 14";
  for (const timestamp of receipts) {
    const age = now - timestamp;
    if (!Number.isFinite(age) || age < 0 || age > HEARTBEAT_WINDOW_MS) continue;
    const x = 144 - (age / HEARTBEAT_WINDOW_MS) * 144;
    path += ` H${(x - 8).toFixed(2)} l3 -3 2 3 2 -11 3 23 3 -12 3 0`;
  }
  return path + " H144";
}
export function NodeHeartbeat({
  at,
  connection,
  stale = false,
}: {
  at: string | null;
  connection: string;
  stale?: boolean;
}) {
  const [now, setNow] = useState<number | null>(null);
  const [history, setHistory] = useState(() => ({
    at,
    receipts: recordHeartbeat([], at),
  }));
  if (history.at !== at) {
    // Keep the earlier receipts when a refreshed snapshot delivers the next one.
    setHistory({ at, receipts: recordHeartbeat(history.receipts, at) });
  }
  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number;
    const start = () => {
      window.clearInterval(timer);
      timer = window.setInterval(
        () => setNow(Date.now()),
        motion.matches ? 1000 : 100,
      );
    };
    start();
    motion.addEventListener("change", start);
    return () => {
      window.clearInterval(timer);
      motion.removeEventListener("change", start);
    };
  }, []);
  const online = connection === "online" && !stale;
  return (
    <span
      className={`node-heartbeat ${online ? "heartbeat-online" : "heartbeat-stale"}`}
    >
      <span>{localTime(at)}</span>
      <svg
        viewBox="0 0 144 30"
        width="144"
        height="30"
        role="img"
        aria-label={`Latest received heartbeat: ${at ? localTime(at) : "unknown"}. ${stale ? "Displayed data is stale" : connection}. Observed heartbeats scroll through a 60-second window while this view is open; earlier pulses remain until they leave the window.`}
      >
        <path
          d={now === null ? "M0 14 H144" : heartbeatPath(history.receipts, now)}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
