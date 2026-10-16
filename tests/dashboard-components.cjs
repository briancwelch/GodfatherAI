// TypeScript transpilation uses the existing compiler; no test runtime dependency.
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const assert = require("node:assert/strict");
const test = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
for (const extension of [".tsx", ".ts"]) {
  require.extensions[extension] = (module, filename) => {
    const source = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true,
      },
    }).outputText;
    module._compile(source, filename);
  };
}
const ui = require("../apps/dashboard/src/components/operational.tsx");
const contracts = require("../apps/dashboard/src/lib/contracts.ts");
const server = require("../apps/dashboard/src/lib/control-server.ts");
test("status labels remain explicit and output is escaped", () => {
  const html = renderToStaticMarkup(
    React.createElement(ui.StatusBadge, { value: "REVIEW_REQUIRED" }),
  );
  assert.match(html, /REVIEW REQUIRED/);
  const json = renderToStaticMarkup(
    React.createElement(ui.JsonDetails, {
      label: "Output",
      value: { text: "<script>attack</script>" },
    }),
  );
  assert.ok(!json.includes("<script>"));
});
test("tables use semantic headers and expose empty state", () => {
  const html = renderToStaticMarkup(
    React.createElement(ui.DataTable, {
      caption: "Real nodes",
      rows: [],
      columns: [{ label: "Node", cell: (x) => x }],
      rowKey: (x) => x,
    }),
  );
  assert.match(html, /<caption>Real nodes<\/caption>/);
  assert.match(html, /scope="col"/);
  assert.match(html, /No matching records/);
});
test("unknown telemetry differs from zero", () => {
  assert.equal(contracts.bytes(null), "Unavailable");
  assert.equal(contracts.bytes(0), "0.0 GiB");
});
test("manual retry refuses unsafe errors and exhausted budgets", () => {
  const detail = {
    job: { status: "FAILED", attempt_count: 2, cancel_requested_at: null },
    workflow: null,
    attempts: [{ error: { code: "lease_expired" } }],
  };
  assert.equal(contracts.retryEligible(detail), true);
  detail.attempts[0].error.code = "permanent_error";
  assert.equal(contracts.retryEligible(detail), false);
  detail.attempts[0].error.code = "lease_expired";
  detail.job.attempt_count = 11;
  assert.equal(contracts.retryEligible(detail), false);
});
test("local credential bridge rejects foreign hosts, CSRF and nonallowlisted writes", () => {
  const request = (host, origin) => ({
    headers: new Headers({ host, ...(origin ? { origin } : {}) }),
  });
  assert.equal(
    server.localRequest(
      request("127.0.0.1:3000", "http://127.0.0.1:3000"),
      true,
    ),
    true,
  );
  assert.equal(
    server.localRequest(
      request("attacker.invalid", "http://attacker.invalid"),
      true,
    ),
    false,
  );
  assert.equal(
    server.localRequest(
      request("localhost:3000", "https://attacker.invalid"),
      true,
    ),
    false,
  );
  assert.equal(server.allowedPath("workers/register", "POST"), false);
  assert.equal(
    server.allowedPath(
      "jobs/00000000-0000-0000-0000-000000000000/cancel",
      "POST",
    ),
    true,
  );
  const before = process.env.GODFATHER_API_URL;
  try {
    process.env.GODFATHER_API_URL = "https://outside.invalid";
    assert.throws(() => server.apiBase());
  } finally {
    if (before === undefined) delete process.env.GODFATHER_API_URL;
    else process.env.GODFATHER_API_URL = before;
  }
});
