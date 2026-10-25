import { bytes, type Resource } from "../lib/contracts";

export function MeasuredHardware({ resources }: { resources: Resource }) {
  const hardware = resources.hardware;
  if (!hardware) return <>Physical totals not reported separately</>;
  return (
    <>
      {hardware.cpu_count} CPUs · {bytes(hardware.ram_bytes)} RAM
      <small>
        {hardware.gpus.length
          ? hardware.gpus.map((gpu, index) => (
              <span key={`${gpu.name}:${index}`}>
                {index > 0 && "; "}
                {gpu.name} ·{" "}
                {gpu.unified_memory
                  ? "Unified memory"
                  : bytes(gpu.memory_bytes)}
              </span>
            ))
          : "No measured GPU reported"}
      </small>
      {!!hardware.gpus.length && !resources.gpus.length && (
        <small>Detected GPUs are not shared for scheduling</small>
      )}
    </>
  );
}

export function NodeCapacity({ resources }: { resources: Resource }) {
  return (
    <>
      <small>
        Scheduling capacity: {resources.cpu_count} CPUs ·{" "}
        {bytes(resources.ram_bytes)} RAM
      </small>
      <div className="small">
        {resources.hardware ? "Measured hardware: " : ""}
        <MeasuredHardware resources={resources} />
      </div>
    </>
  );
}
