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
const login = require("../apps/dashboard/src/components/google-login.tsx");
const administration = require("../apps/dashboard/src/components/administration.tsx");
const shell = require("../apps/dashboard/src/components/application-shell.tsx");

test("desktop shell uses backend environment and accessible section navigation", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      shell.ApplicationShell,
      {
        section: "agents",
        data: {
          environment: "production",
          generated_at: "2026-10-20T20:00:00Z",
          workspace_id: "scope",
          workspaces: [{ id: "scope", name: "Private work" }],
        },
        account: { display_name: "Test owner", roles: ["platform_admin"] },
        refresh: () => {},
      },
      React.createElement("main", { id: "main-content" }, "Workspace"),
    ),
  );
  assert.match(html, /production environment/);
  assert.match(html, /Agents ribbon/);
  assert.match(html, /aria-current="page"/);
  assert.match(html, /Private work/);
  assert.ok(!/TRUSTED LOCAL|Phase 07|ElementCAD/.test(html));
  const unknown = renderToStaticMarkup(
    React.createElement(shell.ApplicationShell, {
      section: "overview",
      refresh: () => {},
    }),
  );
  assert.match(unknown, /Environment unavailable/);
  assert.ok(!unknown.includes("production environment"));
});

test("unavailable ribbon commands explain why and remain keyboard discoverable", () => {
  const html = renderToStaticMarkup(
    React.createElement(shell.UnavailableCommand, {
      label: "Run",
      reason: "Select an enabled version",
    }),
  );
  assert.match(html, /tabIndex="0"|tabindex="0"/);
  assert.match(html, /disabled/);
  assert.match(html, /Select an enabled version/);
  assert.equal(server.allowedPath("agent-options", "GET"), true);
  assert.equal(server.allowedPath("agent-options", "POST"), false);
});

test("Google sign-in has invitation-only onboarding and truthful unavailable state", () => {
  const html = renderToStaticMarkup(
    React.createElement(login.GoogleLogin, { error: "unavailable" }),
  );
  assert.match(html, /Continue with Google/);
  assert.match(html, /Invitation token/);
  assert.match(html, /unavailable or not configured/);
  assert.ok(!html.includes("Administrator credential"));
});

test("administration renders backend account identity and hides platform controls for contributors", () => {
  const user = {
    id: "test-only-id",
    display_name: "<Test contributor>",
    email: "test@example.invalid",
    roles: ["contributor"],
    permissions: ["nodes.contribute"],
    enabled: true,
    picture: null,
  };
  const html = renderToStaticMarkup(
    React.createElement(administration.default, { initialUser: user }),
  );
  assert.match(html, /&lt;Test contributor&gt;/);
  assert.match(html, /Owned node onboarding/);
  assert.ok(!html.includes("<h2>Users</h2>"));
  assert.ok(!html.includes("<h2>Invitations</h2>"));
  assert.match(html, /Loading authorized workspaces/);
});
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
