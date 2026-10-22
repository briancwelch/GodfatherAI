"use client";

import { useState } from "react";

export function Avatar({
  name,
  picture,
}: {
  name: string;
  picture?: string | null;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const initials =
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((s) => s[0])
      .join("")
      .toUpperCase() || "GF";
  return picture?.startsWith("https://") && failed !== picture ? (
    <img
      className="account-avatar"
      src={picture}
      alt=""
      width={16}
      height={16}
      referrerPolicy="no-referrer"
      onError={() => setFailed(picture)}
    />
  ) : (
    <span className="account-avatar avatar-fallback" aria-hidden="true">
      {initials}
    </span>
  );
}
