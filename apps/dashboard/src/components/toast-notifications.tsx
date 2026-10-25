"use client";

import { ProgressBar } from "./progress-bar";

import { useEffect, useSyncExternalStore } from "react";
import { CommandIcon } from "./command-icon";
import {
  authenticationRequired,
  control,
  ControlError,
  subscribeAuthentication,
} from "../lib/control-client";
import { startPolling } from "../lib/polling";
import type { JobDetail } from "../lib/contracts";
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
      className={`toast show corner-toast toast-${toast.kind}`}
      role={toast.kind === "error" ? "alert" : "status"}
      aria-atomic="true"
    >
      <div className="toast-header">
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
        <strong>{toast.title}</strong>
        <button
          type="button"
          className="btn-close"
          onClick={dismiss}
          aria-label={`Dismiss ${toast.title}`}
        />
      </div>
      <div className="toast-body">
        <span>{toast.message}</span>
        {toast.kind === "processing" && (
          <ProgressBar
            value={toast.progress}
            aria-label={
              toast.progress === undefined
                ? "Processing; progress not reported"
                : "Reported job progress"
            }
          />
        )}
        {toast.href && (
          <a className="toast-action" href={toast.href}>
            View
          </a>
        )}
      </div>
    </article>
  );
}

export function ToastNotifications() {
  const signInRequired = useSyncExternalStore(
    subscribeAuthentication,
    authenticationRequired,
    () => false,
  );
  const messages = useSyncExternalStore(
    subscribeToasts,
    toastSnapshot,
    () => emptyToasts,
  );
  useEffect(() => {
    return startPolling({
      request: async (signal) => {
        const results = await Promise.allSettled(
          [...watchedJobs.values()].map(async (job) => {
            try {
              const data = await control<
                Partial<JobDetail> & {
                  status?: string;
                  error?: string;
                  tasks?: { status: string }[];
                }
              >(job.path, undefined, 10000, signal);
              if (signal.aborted) return;
              if (!watchedJobs.has(job.id)) return;
              const status = data.job?.status || data.status;
              if (!status) throw new Error("Status unavailable");
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
            } catch (error) {
              if (signal.aborted) return;
              if (
                error instanceof ControlError &&
                [403, 404].includes(error.status)
              ) {
                finishWatchedJob(job.id);
                dismissToast(`job:${job.id}`);
                return;
              }
              if (!authenticationRequired())
                notifyToast({
                  id: `job:${job.id}`,
                  kind: "processing",
                  title: job.name,
                  message: "Connection interrupted - job status is unknown",
                  href: job.href,
                });
              throw error;
            }
          }),
        );
        const failed = results.find((result) => result.status === "rejected");
        if (failed?.status === "rejected") throw failed.reason;
      },
      onData: () => {},
      onError: () => {},
    });
  }, []);
  if (signInRequired || !messages.length) return null;
  return (
    <aside
      className="toast-container corner-toasts"
      aria-label="Notifications"
      tabIndex={-1}
    >
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
