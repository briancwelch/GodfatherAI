# Capacity and model memory admission

The Command Center distinguishes **scheduling capacity** from **measured hardware**.
Consigliere caps scheduling CPU/RAM to its owner's saved contribution settings and
current discovery. Ordinary GPU resources remain unshared. A detected GPU in the
hardware section does not authorize GPU scheduling. Managed shared inference still
requires its existing per-device consent and exclusive engine setup.

CPU utilization is a whole-host measurement. RAM available to scheduling is capped
by the owner budget and measured availability; unknown measurements remain unknown.
These values guide admission, not host-level CPU/RAM isolation guarantees. Separate
physical totals are unavailable on older workers until their owner updates them.

## Explicit runtime memory profiles

Memory requirements vary with model build/quantization, context, runtime options,
offload and concurrency. Do not use the model's download/storage size as inference
RAM. Unknown estimates remain displayed as unavailable. Scheduler checks for explicit
RAM/VRAM requirements still fail closed when the worker lacks known capacity.

The existing provider JSON configuration accepts `memory_profiles`, keyed by the
exact discovered model identifier. Set existing RAM/VRAM byte fields from conservative
owner measurements or documented runtime requirements. Include an evidence note and
the largest context covered. Pin a digest when available; a changed digest makes
that deployment unavailable until reviewed. Example **synthetic values**, not a
recommendation for any real model:

```json
[
  {
    "id": "local-ollama",
    "provider": "ollama",
    "memory_profiles": {
      "SYNTHETIC-MODEL:fixture": {
        "estimated_ram_bytes": 8589934592,
        "estimated_vram_bytes": 0,
        "context_window": 4096,
        "evidence": "Synthetic example only; replace with verified conservative measurements"
      }
    }
  }
]
```

For desktop Consigliere, quit the worker and merge this model-to-profile mapping into
`ollama_memory_profiles` in its existing private `settings.json`; preserve all other
settings and restart. The worker creates its provider configuration from that saved
mapping. Scanned OpenAI-compatible providers can carry their own `memory_profiles`
inside the existing `local_providers` settings. Never put provider keys in profiles.

Profile values populate `ModelDeployment.estimated_ram_bytes` and
`estimated_vram_bytes` with `metadata_source=configured`. They do not replace job
floors: reservations use the larger of the job requirement and model estimate.
The admitted context is limited to the profile's context. Ollama also receives
`num_ctx`; CPU-only profiles explicitly set `num_gpu=0`. For an OpenAI-compatible
server, the owner must keep its configured context, offload and concurrency within
the attested envelope. Profiles do not grant extra GPUs or higher owner budgets.

Ollama's [context documentation](https://docs.ollama.com/context-length) and
[concurrency FAQ](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests)
explain why context and parallel requests affect memory. A loaded footprint or file
size alone does not establish a conservative envelope for all permitted requests.
This change does not load models or perform physical benchmarks.

## Admission and recovery checks

- Required unknown RAM/VRAM rejects admission; measured hardware cannot override it.
- Current scheduling capacity, active attempt reservations and concurrency limits
  prevent a second job from spending already reserved capacity.
- Reservations retain the deployment captured with the active attempt.
- OS, architecture, runtime, model, tools, workspace and node-owner restrictions
  still apply, including after lease expiry.
- Insufficient/unknown memory or unshared GPU capacity on a recovery destination
  leaves the job queued and preserves its committed checkpoint and stale-worker fence.

Regression coverage: `tests/test_capacity_profiles.py`,
`tests/integration/test_capacity_admission.py`, scheduler/failover suites and
dashboard component/browser fixtures. Physical performance remains an evidence gate.
