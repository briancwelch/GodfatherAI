"use client";

import { useEffect, useSyncExternalStore } from "react";
import { CommandIcon } from "./command-icon";
import {
  dismissToast,
  finishWatchedJob,
  emptyToasts,
  notifyError,
  notifyToast,
  subscribeToasts,
  toastSnapshot,
  watchedJobs,
  type ToastMessage,
} from "../lib/notifications";

export function useFeedback(error: string, notice = "") {
  useEffect(() => {
    if (error) notifyError(error);
  }, [error]);
  useEffect(() => {
    if (notice)
      notifyToast({
        id: `notice:${notice}`,
        kind: "notification",
        title: "Notification",
        message: notice,
      });
  }, [notice]);
}

export function ToastCard({
  toast,
  dismiss,
}: {
  toast: ToastMessage;
  dismiss: () => void;
}) {
  return (
    <article
      className={`corner-toast toast-${toast.kind}`}
      role={toast.kind === "error" ? "alert" : "status"}
      aria-atomic="true"
    >
      <span className="toast-symbol">
        <CommandIcon
          label={
            toast.kind === "error"
              ? "Warning"
              : toast.kind === "success"
                ? "Verified"
                : toast.kind === "processing"
                  ? "Run"
                  : "Notification"
          }
        />
      </span>
      <div className="toast-copy">
        <strong>{toast.title}</strong>
        <span>{toast.message}</span>
        {toast.kind === "processing" && (
          <progress
            max={100}
            value={toast.progress}
            aria-label={
              toast.progress === undefined
                ? "Processing; progress not reported"
                : "Reported job progress"
            }
          />
        )}
      </div>
      {toast.href && (
        <a className="toast-action" href={toast.href}>
          View
        </a>
      )}
      <button
        type="button"
        className="toast-dismiss"
        onClick={dismiss}
        aria-label={`Dismiss ${toast.title}`}
      >
        {"\u00d7"}
      </button>
    </article>
  );
}

export function ToastNotifications() {
  const messages = useSyncExternalStore(
    subscribeToasts,
    toastSnapshot,
    () => emptyToasts,
  );
  useEffect(() => {
    let active = true,
      loading = false;
    const refresh = async () => {
      if (loading) return;
      loading = true;
      try {
        await Promise.all(
          [...watchedJobs.values()].map(async (job) => {
            try {
              const response = await fetch(`/api/control/${job.path}`, {
                cache: "no-store",
                signal: AbortSignal.timeout(10000),
              });
              if (!active) return;
              if (
                response.status === 401 ||
                response.status === 403 ||
                response.status === 404
              ) {
                finishWatchedJob(job.id);
                dismissToast(`job:${job.id}`);
                return;
              }
              if (!response.ok) throw new Error("Status unavailable");
              const data = await response.json();
              if (!active) return;
              if (!watchedJobs.has(job.id)) return;
              const status = data.job?.status || data.status;
              const lastError = data.attempts?.at(-1)?.error?.code;
              const failure =
                typeof data.error === "string" && data.error
                  ? data.error
                  : typeof lastError === "string"
                    ? `Job failed: ${lastError.replaceAll("_", " ")}. Open details for retained results.`
                    : "Job failed. Open its details for the error and retained results.";
              const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(
                status,
              );
              const tasks = data.tasks as { status: string }[] | undefined;
              const stepCount = Array.isArray(data.steps)
                ? data.steps.length
                : 0;
              const layerProgress = data.events?.items?.find(
                (event: { type: string }) => event.type === "job.progress",
              )?.details?.percent;
              const progress = tasks?.length
                ? (tasks.filter((task) => task.status === "COMPLETED").length /
                    tasks.length) *
                  100
                : stepCount && typeof data.workflow?.current_step === "number"
                  ? Math.min(
                      100,
                      (data.workflow.current_step / stepCount) * 100,
                    )
                  : typeof layerProgress === "number" &&
                      layerProgress >= 0 &&
                      layerProgress <= 100
                    ? layerProgress
                    : undefined;
              notifyToast({
                id: `job:${job.id}`,
                title: job.name,
                kind:
                  status === "COMPLETED"
                    ? "success"
                    : status === "FAILED"
                      ? "error"
                      : status === "CANCELLED"
                        ? "notification"
                        : "processing",
                message:
                  status === "COMPLETED"
                    ? "Completed successfully"
                    : status === "FAILED"
                      ? failure
                      : status === "CANCELLED"
                        ? "Cancellation confirmed"
                        : status === "PENDING"
                          ? "Queued - waiting for compatible workers"
                          : status === "RETRY_WAIT"
                            ? "Waiting for a safe retry"
                            : "Processing",
                progress,
                href: job.href,
              });
              if (terminal) finishWatchedJob(job.id);
            } catch {
              if (active)
                notifyToast({
                  id: `job:${job.id}`,
                  kind: "processing",
                  title: job.name,
                  message: "Connection interrupted - job status is unknown",
                  href: job.href,
                });
            }
          }),
        );
      } finally {
        loading = false;
      }
    };
    const timer = window.setInterval(() => {
      void refresh();
    }, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  if (!messages.length) return null;
  return (
    <aside className="corner-toasts" aria-label="Notifications" tabIndex={-1}>
      {messages.map((toast) => (
        <ToastCard
          key={toast.id}
          toast={toast}
          dismiss={() => dismissToast(toast.id)}
        />
      ))}
    </aside>
  );
}
