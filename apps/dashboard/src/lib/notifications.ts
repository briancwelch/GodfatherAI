export type ToastKind = "processing" | "success" | "error" | "notification";
export interface ToastMessage {
  id: string;
  kind: ToastKind;
  title: string;
  message: string;
  progress?: number;
  href?: string;
}
let messages: ToastMessage[] = [];
const listeners = new Set<() => void>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const dismissed = new Set<string>();
const seenErrors = new Map<string, number>();
export const emptyToasts: ToastMessage[] = [];
export const toastSnapshot = () => messages;
export function subscribeToasts(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function dismissToast(id: string) {
  dismissed.add(id);
  clearTimeout(timers.get(id));
  timers.delete(id);
  messages = messages.filter((item) => item.id !== id);
  listeners.forEach((listener) => listener());
}
export function notifyToast(toast: ToastMessage) {
  if (typeof window === "undefined") return;
  if (toast.kind === "processing" && dismissed.has(toast.id)) return;
  if (toast.kind !== "processing") dismissed.delete(toast.id);
  const current = messages.find((item) => item.id === toast.id);
  if (current && JSON.stringify(current) === JSON.stringify(toast)) return;
  clearTimeout(timers.get(toast.id));
  messages = [toast, ...messages.filter((item) => item.id !== toast.id)];
  listeners.forEach((listener) => listener());
  // Errors remain until explicitly dismissed. Pending jobs never use a duration timer.
  if (toast.kind === "success" || toast.kind === "notification")
    timers.set(
      toast.id,
      setTimeout(() => dismissToast(toast.id), 8000),
    );
}
export function notifyError(message: string) {
  if (typeof window === "undefined" || !message) return;
  const prior = seenErrors.get(message) || 0;
  if (Date.now() - prior < 30000) return;
  seenErrors.set(message, Date.now());
  if (seenErrors.size > 100) seenErrors.delete(seenErrors.keys().next().value!);
  notifyToast({
    id: `error:${message}`,
    kind: "error",
    title: "Action needs attention",
    message,
  });
}
export interface WatchedJob {
  id: string;
  path: string;
  href: string;
  name: string;
}
export const watchedJobs = new Map<string, WatchedJob>();
let notificationOwner = "";
function persistWatchedJobs() {
  if (!notificationOwner || typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      `godfather.active-jobs:${notificationOwner}`,
      JSON.stringify(
        [...watchedJobs.values()].map((job) => ({
          id: job.id,
          tasks: job.path.startsWith("distributed/tasks/"),
        })),
      ),
    );
  } catch {
    /* Browser storage can be unavailable; in-page tracking still works. */
  }
}
export function resumeJobNotifications(owner: string) {
  if (notificationOwner === owner || typeof window === "undefined") return;
  clearNotifications();
  notificationOwner = owner;
  try {
    const saved = JSON.parse(
      window.sessionStorage.getItem(`godfather.active-jobs:${owner}`) || "[]",
    );
    if (Array.isArray(saved))
      for (const job of saved.slice(0, 64)) {
        if (
          !job ||
          typeof job.id !== "string" ||
          !/^[0-9a-f-]{36}$/i.test(job.id) ||
          typeof job.tasks !== "boolean"
        )
          continue;
        watchJob({
          id: job.id,
          path: job.tasks
            ? `distributed/tasks/${job.id}`
            : `command-center/jobs/${job.id}`,
          href: job.tasks
            ? `/distributed-tasks?job=${job.id}`
            : `/jobs/${job.id}`,
          name: job.tasks ? "Distributed tasks" : "Job",
        });
      }
  } catch {
    /* Invalid or unavailable storage never grants access. */
  }
}
export function finishWatchedJob(id: string) {
  watchedJobs.delete(id);
  persistWatchedJobs();
}
export function watchJob(job: WatchedJob) {
  if (watchedJobs.has(job.id)) return;
  watchedJobs.set(job.id, job);
  persistWatchedJobs();
  notifyToast({
    id: `job:${job.id}`,
    kind: "processing",
    title: job.name,
    message: "Queued - waiting for worker execution",
    href: job.href,
  });
}
export function clearNotifications() {
  if (notificationOwner && typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(
        `godfather.active-jobs:${notificationOwner}`,
      );
    } catch {
      /* Storage restrictions do not prevent logout. */
    }
  }
  notificationOwner = "";
  timers.forEach(clearTimeout);
  timers.clear();
  watchedJobs.clear();
  seenErrors.clear();
  dismissed.clear();
  messages = [];
  listeners.forEach((listener) => listener());
}
