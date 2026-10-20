"use client";

import { useState, type ComponentPropsWithoutRef } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import rehypeHighlight from "rehype-highlight";
import type { JobDetail, Json } from "../lib/contracts";

function object(value: Json | undefined): Record<string, Json> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function CodeBlock({ children, ...props }: ComponentPropsWithoutRef<"pre">) {
  const [message, setMessage] = useState("Copy");
  return (
    <div className="result-code">
      <button
        className="action secondary"
        type="button"
        onClick={async (event) => {
          const text =
            event.currentTarget.parentElement?.querySelector("pre")
              ?.textContent || "";
          try {
            await navigator.clipboard.writeText(text);
            setMessage("Copied");
          } catch {
            setMessage("Copy unavailable; select the code");
          }
        }}
      >
        {message}
      </button>
      <pre {...props}>{children}</pre>
    </div>
  );
}

export function SafeMarkdown({ text }: { text: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize, rehypeHighlight]}
      skipHtml
      components={{
        pre: CodeBlock,
        img: ({ alt }) => (
          <span>[Image: {alt || "remote image disabled"}]</span>
        ),
        a: ({ href, children }) => (
          <a href={href} rel="noreferrer noopener" target="_blank">
            {children}
          </a>
        ),
      }}
    >
      {text}
    </Markdown>
  );
}

export function ReadableValue({ value }: { value: Json }) {
  const data = object(value);
  if (typeof value === "string") {
    if (
      value.trimStart().startsWith("[") ||
      value.trimStart().startsWith("{")
    ) {
      let structured: Json | undefined;
      try {
        structured = JSON.parse(value) as Json;
      } catch {
        /* Render ordinary text below. */
      }
      if (structured !== undefined) return <ReadableValue value={structured} />;
    }
    return <SafeMarkdown text={value} />;
  }
  if (typeof data.text === "string") return <ReadableValue value={data.text} />;
  if (typeof data.summary === "string" && typeof data.diff === "string")
    return (
      <>
        <SafeMarkdown text={data.summary} />
        <h4>File changes</h4>
        {Array.isArray(data.search_matches) &&
          data.search_matches.length > 0 && (
            <details>
              <summary>Code search matches</summary>
              <pre>
                {data.search_matches
                  .map((match) => {
                    const m = object(match);
                    return `${String(m.path)}:${String(m.line)} ${String(m.text)}`;
                  })
                  .join("\n")}
              </pre>
            </details>
          )}
        <ul>
          {Array.isArray(data.files_changed) &&
            data.files_changed.map((p, i) => (
              <li key={i}>
                <code>{String(p)}</code>
              </li>
            ))}
        </ul>
        <SafeMarkdown text={`\`\`\`diff\n${data.diff}\n\`\`\``} />
        <DownloadText
          text={data.diff}
          filename="changes.patch"
          label="Download patch"
        />
        <h4>Tests</h4>
        {Array.isArray(data.tests) && data.tests.length ? (
          data.tests.map((test, index) => {
            const t = object(test);
            return (
              <div key={index}>
                <p>
                  <strong>{t.exit_code === 0 ? "Passed" : "Failed"}</strong>
                  {" · "}
                  <code>
                    {Array.isArray(t.command)
                      ? t.command.join(" ")
                      : "Command unavailable"}
                  </code>
                  {` · exit ${String(t.exit_code)}`}
                </p>
                <details>
                  <summary>Command output</summary>
                  <pre>{String(t.output || "No output")}</pre>
                </details>
              </div>
            );
          })
        ) : (
          <p>No tests were run.</p>
        )}
      </>
    );
  if (typeof data.title === "string" && Array.isArray(data.items))
    return (
      <>
        <h4>{data.title}</h4>
        <ul>
          {data.items.map((v, i) => (
            <li key={i}>{String(v)}</li>
          ))}
        </ul>
      </>
    );
  if (Array.isArray(data.columns) && Array.isArray(data.rows)) {
    const columns = data.columns.map(String);
    return (
      <div className="table-scroll">
        <table>
          <caption>
            {typeof data.title === "string" ? data.title : "Analysis results"}
          </caption>
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th key={i} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.slice(0, 500).map((row, i) => (
              <tr key={i}>
                {columns.map((c, j) => (
                  <td key={j}>
                    {JSON.stringify(
                      Array.isArray(row) ? row[j] : object(row)[c],
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (Array.isArray(data.series)) {
    const points = data.series
      .slice(0, 100)
      .map(object)
      .filter(
        (p) => typeof p.label === "string" && typeof p.value === "number",
      );
    const max = Math.max(1, ...points.map((p) => Math.abs(Number(p.value))));
    return (
      <figure>
        <figcaption>
          {typeof data.title === "string" ? data.title : "Analysis chart"}
        </figcaption>
        <svg
          role="img"
          aria-label="Result values; exact values listed below"
          viewBox={`0 0 600 ${Math.max(30, points.length * 28)}`}
        >
          {points.map((p, i) => (
            <g key={i}>
              <text x="0" y={i * 28 + 19}>
                {String(p.label).slice(0, 20)}
              </text>
              <rect
                x="190"
                y={i * 28 + 3}
                width={(Math.abs(Number(p.value)) / max) * 300}
                height="19"
                fill="var(--ion-ink, #087F8C)"
              />
              <text x="500" y={i * 28 + 19}>
                {String(p.value)}
              </text>
            </g>
          ))}
        </svg>
      </figure>
    );
  }
  if (
    typeof data.base64 === "string" &&
    typeof data.media_type === "string" &&
    /^[A-Za-z0-9+/=\s]+$/.test(data.base64)
  ) {
    const src = `data:${data.media_type};base64,${data.base64}`;
    if (
      ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(
        data.media_type,
      )
    ) {
      return (
        <img
          className="result-media"
          src={src}
          alt={typeof data.title === "string" ? data.title : "Generated image"}
        />
      );
    }
    if (["audio/mpeg", "audio/wav", "audio/ogg"].includes(data.media_type))
      return <audio controls src={src} />;
    if (["video/mp4", "video/webm"].includes(data.media_type))
      return (
        <video className="result-media" controls src={src}>
          <track kind="captions" />
        </video>
      );
    if (
      [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
      ].includes(data.media_type)
    )
      return (
        <a
          className="action"
          href={src}
          download={
            data.media_type === "application/pdf"
              ? "report.pdf"
              : data.media_type === "text/plain"
                ? "report.txt"
                : "report.docx"
          }
        >
          Download report
        </a>
      );
  }
  return (
    <SafeMarkdown
      text={`\`\`\`json\n${JSON.stringify(value, null, 2)}\n\`\`\``}
    />
  );
}

export function JobResult({ detail }: { detail: JobDetail }) {
  const [message, setMessage] = useState("");
  const snapshot = object(detail.output);
  const result = object(detail.job.result);
  const selection = object(detail.job.requirements?.model_selection);
  const final = snapshot.output ?? snapshot.result ?? detail.job.result;
  const data =
    detail.job.type === "inference.text"
      ? snapshot.valid
        ? snapshot.text
        : snapshot.partial_text || result.text
      : final;
  const metadata = object(snapshot.metadata);
  const stepMetadata = object(detail.steps?.at(-1)?.metadata);
  const usage = object(metadata.usage ?? result.usage);
  const deployment = object(
    metadata.deployment ?? result.deployment ?? stepMetadata.model,
  );
  const completed = detail.job.status === "COMPLETED";
  const last = detail.attempts.at(-1);
  const duration =
    last?.started_at && last.finished_at
      ? Math.max(
          0,
          (new Date(last.finished_at).getTime() -
            new Date(last.started_at).getTime()) /
            1000,
        )
      : usage.duration_seconds;
  const artifact = object(result.final_output);
  const hasOutput = data !== null && data !== undefined && data !== "";
  return (
    <section className="job-result" aria-label="Task result">
      <h3>{completed ? "Result" : "Output so far"}</h3>
      {detail.workflow?.status === "REVIEW_REQUIRED" && (
        <p className="notice">
          Recovery requires review:{" "}
          {detail.workflow.recovery_error?.replaceAll("_", " ") ||
            "inspect committed artifacts and execution history"}
          . Commands are not replayed automatically.
        </p>
      )}
      <p className="muted">
        {completed
          ? "Completed"
          : "Partial or unavailable; the job has not completed"}
        {typeof deployment.identifier === "string"
          ? ` · Model: ${deployment.identifier}`
          : ""}
        {detail.workflow ? ` · Agent v${detail.workflow.agent_version}` : ""}
        {typeof duration === "number"
          ? ` · ${duration.toFixed(2)} seconds`
          : ""}
      </p>
      {typeof snapshot.output_error === "string" && (
        <p role="alert">{snapshot.output_error}</p>
      )}
      {!!selection.connection_id && detail.job.status === "FAILED" && (
        <p className="notice">
          Paid attempts require usage and reservation review. Submit a
          separately authorized new task rather than replaying an uncertain paid
          call.
        </p>
      )}
      {result.finish_reason === "length" && (
        <p className="notice">
          Output reached the configured token limit and may be incomplete.
        </p>
      )}
      {Array.isArray(result.tool_calls) && result.tool_calls.length > 0 && (
        <>
          <p>Requested tool calls; these have not been executed.</p>
          <ReadableValue value={result.tool_calls} />
        </>
      )}
      {hasOutput ? (
        <ReadableValue value={data} />
      ) : (
        <p>
          {completed
            ? "The worker returned no answer text. Inspect the finish reason and token usage below."
            : detail.job.status === "FAILED"
              ? `Task failed: ${String(last?.error.code || "unknown error")}`
              : "No committed output is available yet."}
        </p>
      )}
      {hasOutput && (
        <div className="actions">
          <button
            className="action secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(
                  typeof data === "string"
                    ? data
                    : JSON.stringify(data, null, 2),
                );
                setMessage("Result copied");
              } catch {
                setMessage("Copy unavailable; select the output");
              }
            }}
          >
            Copy result
          </button>
          <button
            className="action secondary"
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob(
                  [
                    typeof data === "string"
                      ? data
                      : JSON.stringify(data, null, 2),
                  ],
                  { type: "text/plain;charset=utf-8" },
                ),
              );
              const link = document.createElement("a");
              link.href = url;
              link.download = `job-${detail.job.id}${completed ? "" : "-partial"}.txt`;
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download {completed ? "result" : "partial output"}
          </button>
          {typeof artifact.id === "string" && (
            <a
              className="action secondary"
              href={`/api/control/workflow/jobs/${detail.job.id}/artifacts/${artifact.id}?download=1`}
            >
              Download verified artifact
            </a>
          )}
        </div>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}

function DownloadText({
  text,
  filename,
  label,
}: {
  text: string;
  filename: string;
  label: string;
}) {
  return (
    <button
      className="action secondary"
      onClick={() => {
        const url = URL.createObjectURL(
          new Blob([text], { type: "text/plain;charset=utf-8" }),
        );
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);
      }}
    >
      {label}
    </button>
  );
}
