# Inference extension v1

Current authentication is documented in [Phase 09](../operations/phase-09.md).
Google OIDC/application sessions replace human bearer login in normal operation;
worker machine credentials remain independent. Earlier bearer/simulator procedures
below are historical and restricted to isolated automated tests. Phase 09 does not
authorize public deployment or Phase 10.

All routes use `/api/v1`, existing bearer credentials, correlation IDs, commit-before-success transactions, safe validation/errors and backend workspace authorization. Provisioned administrator credentials remain the local client foundation. This is not browser authentication or full Phase 09 RBAC. Node-owner consent is enforced independently.

## Endpoints

| Method/path                                           | Contract                                                                                                  |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `GET /models?workspace_id=UUID&limit=100&offset=0`    | Deployment snapshots visible for this user's execution in that workspace; optional `node_id`; limit 1–200 |
| `GET /models/deployments/{node_id}?workspace_id=UUID` | Inspect node deployments, metadata, capability provenance and effective availability                      |
| `POST /inference/jobs`                                | Typed `InferenceSubmission`, returns 201 `JobView`; unsupported deployments remain queued                 |
| `GET /jobs/{job_id}`                                  | Existing durable job status, requirements, current attempt and final result                               |
| `GET /inference/jobs/{job_id}/result`                 | Current attempt identity, valid bounded text, structured final result/error and execution metadata        |
| `GET /inference/jobs/{job_id}/stream`                 | Authenticated SSE full snapshots, resets, invalidations and keepalive comments                            |
| `POST /jobs/{job_id}/cancel`                          | Existing idempotent cancellation; job owner/workspace administrator only                                  |
| `GET /jobs/{job_id}/attempts`                         | Attempt history, times, fences and classified errors                                                      |
| `GET /jobs/{job_id}/events`                           | Existing paginated durable lifecycle events; no prompts/output text                                       |
| `GET /inference/metrics?workspace_id=UUID`            | Job-state counts, terminal failure/cancellation rates and latest 200 attempt metadata records             |

Absent/wrong/revoked credentials return 401, disallowed owners/roles 403, inaccessible workspaces/jobs 404, stale execution reports 409, invalid bounded contracts 422, unsupported worker/job protocols 426. Generic `POST /jobs` also accepts the new typed inference job. The dedicated endpoint always requires `inference.text`. No manual retry route is added; use the existing bounded automatic retry policy.

Example request (use an actual provisioned workspace UUID and a discovered identifier):

```json
{
  "workspace_id": "00000000-0000-0000-0000-000000000001",
  "type": "inference.text",
  "requirements": {
    "os": "any",
    "cpu_count": 1,
    "model_selection": {
      "identifier": "YOUR_INSTALLED_MODEL",
      "provider": "ollama",
      "stream": true
    }
  },
  "input": {
    "prompt": "Reply with one short greeting.",
    "stream": true,
    "parameters": { "temperature": 0.7, "top_p": 1, "max_tokens": 32 }
  },
  "timeout_seconds": 120,
  "retry": { "limit": 0, "backoff_seconds": 1 }
}
```

For capability selection, omit `identifier` and require a nonempty `capabilities` array. `allow_declared_capabilities` defaults false. Optional provider/context constraints still apply. There is no fallback list or model substitution. Input and selection streaming modes must agree. Non-streaming jobs use `stream: false` in both locations. System text, optional seed and all existing execution resource/platform requirements are supported. Unknown fields/provider parameters/tools are refused. See the typed contracts for exact bounds and literals.

## Worker opt-in and reports

Registration v1 gains optional `inference_protocol_version: 1` and `model_deployments`. Each deployment includes local provider alias/type, identifier, available flag, verified/declared capabilities, chat/stream operations, optional context/digest/disk size/estimated memory and metadata source. The server adds hosting node identity. Provider URLs/keys are forbidden. The same session can replace its inventory through authenticated registration. Older registration-only workers need no changes.

Inference uses existing poll/report v1 and adds an optional assigned `deployment`. Old synthetic assignments omit this field, and omit absent `model_selection` from requirements, preserving strict older worker parsers. Inference is sent only to explicitly opted-in workers. Existing synthetic execution remains simulation-only; opting into inference does not grant shell/tool access.

`action: output` adds `output: {sequence, text}`. Sequences start at 1 and append contiguously through at most 512 updates; each batch has 1–4,096 characters and the entire prefix stays at most 32,768 characters. Repeating the last sequence with identical text is idempotent; changed/reordered/gapped updates are refused. Non-streaming jobs cannot publish partial output. Updates do not renew leases; the independent worker monitor renews through existing fenced `renew` reports. No token data is added to audit events.

`complete` requires `{text, deployment, usage, finish_reason}`. The deployment must equal the assigned one and final text must extend any streamed prefix. Usage carries duration, optional first-token latency/counts/rate and explicit measurement sources. Results remain bounded. `fail` accepts safe provider codes: `provider_unavailable`, `model_unavailable`, `provider_auth`, `rate_limited`, `provider_timeout`, `invalid_response`, `invalid_request`, `output_limit`. Only unavailable, rate-limited and provider-timeout errors retry; existing synthetic transient errors and lease/deadline expiry retain Phase 04 rules. Provider response bodies/exceptions never enter error metadata.

## SSE/reconnection and cancellation

Frames are `reset`, `snapshot`, `invalidated`, or `revoked`. Data contains job/attempt UUIDs and the fencing token; snapshot IDs combine attempt, sequence and state. Full text replaces the previous snapshot: do not append snapshots. A reset clears provisional text on any generation change. Clients must discard invalidated provisional output; only `COMPLETED` results are final. Failed/cancelled/expired attempts expose no partial text, even if maintenance has not yet run. Already-consumed client text cannot be retracted.

Connections last at most 30 seconds and close on terminal/retry state or an expired running attempt. Reconnect to the same route for the current snapshot. `Last-Event-ID` does not replay historical token deltas: regardless of the supplied ID, the server selects only the current valid attempt. A replacement attempt starts with reset/new identity. Disconnecting the viewing client does not cancel its job. Authorization is rechecked on each fresh database read; revoked access ends with `revoked`. No SQL transaction/credential lock stays open while waiting.

Cancellation remains the existing durable race policy. The worker monitor checks during provider stalls; an observed cancellation closes the HTTP stream and acknowledges cancellation. A committed cancellation prevents subsequent completion from publishing a result. Network loss, disabled credentials or stale reports abort local generation; leases decide retry. There is no claim of recovering GPU state or continuation of tokens from a previous attempt.
