export function ProgressBar({
  value,
  max = 100,
  "aria-label": label,
}: {
  value?: number;
  max?: number;
  "aria-label": string;
}) {
  const measured = value !== undefined && Number.isFinite(value) && max > 0;
  const percent = measured
    ? Math.max(0, Math.min(100, (value / max) * 100))
    : undefined;
  return (
    <div
      className={`progress ${measured ? "" : "progress-indeterminate"}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={
        percent === undefined ? "Progress not reported" : undefined
      }
    >
      <div
        className="progress-bar progress-bar-striped progress-bar-animated"
        style={{ width: percent === undefined ? "100%" : `${percent}%` }}
      />
    </div>
  );
}
