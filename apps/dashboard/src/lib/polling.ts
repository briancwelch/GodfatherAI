import {
  authenticationRequired,
  cancelSessionVerification,
  ControlError,
  subscribeAuthentication,
  verifySession,
} from "./control-client";

const pollers = new Set<() => void>();

/** One request at a time; effect cleanup cancels requests, timers and listeners. */
export function startPolling<T>({
  request,
  onData,
  onError,
  intervalMs = 3000,
  sessionCheck = false,
}: {
  request: (signal: AbortSignal) => Promise<T>;
  onData: (value: T) => void;
  onError: (error: unknown) => void;
  intervalMs?: number | null;
  sessionCheck?: boolean;
}) {
  let active = true;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending: AbortController | null = null;
  function cancel() {
    clearTimeout(timer);
    timer = undefined;
    pending?.abort();
    pending = null;
  }
  async function poll() {
    if (
      !active ||
      pending ||
      authenticationRequired() ||
      document.visibilityState === "hidden"
    )
      return;
    clearTimeout(timer);
    timer = undefined;
    const controller = new AbortController();
    pending = controller;
    try {
      const value = await request(controller.signal);
      if (!active || controller.signal.aborted || authenticationRequired())
        return;
      failures = 0;
      onData(value);
    } catch (error) {
      if (!active || controller.signal.aborted || authenticationRequired())
        return;
      failures += 1;
      // Cancel siblings when a batch request fails before retrying the batch.
      controller.abort();
      onError(error);
    } finally {
      if (
        pending === controller &&
        active &&
        !authenticationRequired() &&
        (intervalMs !== null || failures > 0)
      )
        timer = setTimeout(
          () => void poll(),
          Math.min((intervalMs ?? 3000) * 2 ** Math.min(failures, 10), 60000),
        );
      if (pending === controller) pending = null;
    }
  }
  function authenticationChanged() {
    cancel();
    if (authenticationRequired())
      onError(new ControlError("Sign in required", 401));
    else {
      failures = 0;
      void poll();
    }
  }
  function focus() {
    if (document.visibilityState === "hidden") return;
    const paused = authenticationRequired();
    if (!paused && sessionCheck) void poll();
    else
      void verifySession()
        .then(() => {
          if (!paused) void poll();
        })
        .catch(() => {});
  }
  const unsubscribe = subscribeAuthentication(authenticationChanged);
  pollers.add(cancel);
  window.addEventListener("focus", focus);
  document.addEventListener("visibilitychange", focus);
  if (authenticationRequired()) authenticationChanged();
  else void poll();
  return () => {
    active = false;
    cancel();
    unsubscribe();
    window.removeEventListener("focus", focus);
    document.removeEventListener("visibilitychange", focus);
    pollers.delete(cancel);
    if (!pollers.size) cancelSessionVerification();
  };
}
