"use client";

import { useEffect, useState } from "react";
import { localTime } from "../lib/contracts";

export function heartbeatPath(ageSeconds: number, online: boolean): string {
  if (
    !online ||
    !Number.isFinite(ageSeconds) ||
    ageSeconds < 0 ||
    ageSeconds > 30
  )
    return "M0 14 H144";
  const x = Math.max(12, Math.min(132, 144 - ageSeconds * 4));
  return `M0 14 H${x - 10} l3 -3 3 3 2 -11 3 23 3 -12 3 0 H144`;
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
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const age =
    at && now !== null ? (now - new Date(at).getTime()) / 1000 : Infinity;
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
        aria-label={`Latest received heartbeat: ${at ? localTime(at) : "unknown"}. ${stale ? "Displayed data is stale" : connection}. The pulse marks the last received heartbeat in a 30-second window.`}
      >
        <path
          d={heartbeatPath(age, online)}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
