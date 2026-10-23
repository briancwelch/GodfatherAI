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
        target: ts.ScriptTarget.ES2017,
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
const results = require("../apps/dashboard/src/components/job-result.tsx");
const outcomes = require("../apps/dashboard/src/lib/job-outcome.ts");
const modelUse = require("../apps/dashboard/src/components/model-use.tsx");
const avatars = require("../apps/dashboard/src/components/avatar.tsx");
const workspaces = require("../apps/dashboard/src/components/workspace-directory.tsx");
const client = require("../apps/dashboard/src/lib/control-client.ts");

test("cloud image models use Images and Gemini account writes retain scoped routes", () => {
  assert.equal(
    modelUse.modelAgentUrl("workspace", {
      deployment: {
        provider: "gemini",
        identifier: "gemini-3.1-flash-image",
        operations: ["image_generation"],
      },
    }),
    "/images",
  );
  const markup = renderToStaticMarkup(
    React.createElement(modelUse.UseModel, {
      workspace: "workspace",
      model: {
        deployment: {
          provider: "openai",
          identifier: "gpt-image-1.5",
          operations: ["image_generation"],
        },
      },
    }),
  );
  assert.match(markup, /href="\/images"/);
  assert.match(markup, /Generate images/);
  for (const suffix of ["", "/computers", "/disconnect"]) {
    assert.equal(
      server.allowedPath("account/providers/gemini" + suffix, "POST"),
      true,
    );
  }
  assert.equal(server.allowedPath("account/providers/gemini", "GET"), false);
  assert.equal(
    server.allowedPath("account/providers/gemini/keys", "POST"),
    false,
  );
  assert.equal(
    server.allowedPath("account/providers/unreviewed", "POST"),
    false,
  );
});

test("control errors preserve field locations without echoing rejected input and support bounded submission waits", async (context) => {
  let requestedSignal;
  let response = new Response(
    JSON.stringify({
      detail: [
        {
          loc: ["body", "tasks", 0, "input", "instruction"],
          msg: "String should have at most 4096 characters",
          input: "private goal",
          ctx: { secret: "private key" },
        },
      ],
    }),
    { status: 422 },
  );
  context.mock.method(globalThis, "fetch", async (_url, init) => {
    requestedSignal = init.signal;
    return response;
  });
  await assert.rejects(
    client.control("distributed/jobs", {}, 30000),
    (error) => {
      assert.match(error.message, /tasks > 0 > input > instruction/);
      assert.doesNotMatch(error.message, /private goal|private key/);
      return true;
    },
  );
  assert.ok(requestedSignal instanceof AbortSignal);
  response = new Response(
    JSON.stringify({ detail: "Node-owner consent required" }),
    { status: 403 },
  );
  await assert.rejects(
    client.control("distributed/jobs", {}),
    /Node-owner consent required/,
  );
  assert.equal(requestedSignal, undefined);
  response = new Response("Proxy unavailable", { status: 503 });
  await assert.rejects(
    client.control("distributed/jobs", {}),
    /Operation not confirmed \(503\)/,
  );
});

test("account settings is available to members while admin navigation is role-gated", () => {
  const html = renderToStaticMarkup(
    React.createElement(shell.ApplicationShell, {
      section: "account",
      account: { display_name: "Invited member", roles: ["member"] },
      refresh: () => {},
    }),
  );
  assert.match(html, /href="\/account"/);
  assert.doesNotMatch(html, /Admin settings/);
  assert.match(html, /Workspaces/);
  assert.match(html, /Analytics and Reports/);
  assert.equal(server.allowedPath("account/profile", "POST"), true);
  assert.equal(server.allowedPath("account/profile/other-user", "POST"), false);
});

test("avatars use branded initials or safe HTTPS images at 16 pixels", () => {
  let html = renderToStaticMarkup(
    React.createElement(avatars.Avatar, { name: "Invited member" }),
  );
  assert.match(html, /avatar-fallback/);
  assert.match(html, />IM<\/span>/);
  html = renderToStaticMarkup(
    React.createElement(avatars.Avatar, {
      name: "Member",
      picture: "https://example.invalid/avatar.png",
    }),
  );
  assert.match(html, /width="16" height="16"/);
  assert.match(html, /referrerPolicy="no-referrer"/i);
  html = renderToStaticMarkup(
    React.createElement(avatars.Avatar, {
      name: "Member",
      picture: "javascript:alert(1)",
    }),
  );
  assert.doesNotMatch(html, /<img/);
});

test("workspace directory lists authorized containers with scoped overview links", () => {
  const html = renderToStaticMarkup(
    React.createElement(workspaces.WorkspaceList, {
      data: {
        workspaces: [
          { id: "workspace-id", name: "My project", can_manage: true },
        ],
      },
    }),
  );
  assert.match(html, /href="\/workspaces\/workspace-id"/);
  assert.match(html, /My project/);
  const empty = renderToStaticMarkup(
    React.createElement(workspaces.WorkspaceList, { data: { workspaces: [] } }),
  );
  assert.match(empty, /Create your first workspace/);
});

test("local and API models show installed, workspace and worker status independently", () => {
  const model = {
    node_id: "node",
    node_name: "Computer",
    workspace_allowed: false,
    can_enable: true,
    available: false,
    worker_available: true,
    deployment: {
      provider: "openai",
      identifier: "gpt-4.1",
      provider_id: "account",
      connection_id: "connection",
    },
  };
  let html = renderToStaticMarkup(
    React.createElement(modelUse.ModelAvailability, { model }),
  );
  assert.match(html, /Connected OpenAI API/);
  assert.match(html, /workspace access required/);
  assert.match(html, /worker online/);
  html = renderToStaticMarkup(
    React.createElement(modelUse.UseModel, { workspace: "workspace", model }),
  );
  assert.match(html, /Allow in workspace \/ create agent/);
  assert.doesNotMatch(html, /disabled/);
  html = renderToStaticMarkup(
    React.createElement(modelUse.UseModel, {
      workspace: "workspace",
      model: { ...model, can_enable: false },
    }),
  );
  assert.match(html, /disabled/);
  assert.match(html, /workspace administrator/);
  model.deployment.provider = "ollama";
  model.deployment.identifier = "qwen3:8b";
  model.deployment.connection_id = null;
  html = renderToStaticMarkup(
    React.createElement(modelUse.ModelAvailability, {
      model: { ...model, workspace_allowed: true, worker_available: false },
    }),
  );
  assert.match(html, /Installed locally/);
  assert.match(html, /worker offline/);
  assert.equal(
    modelUse.modelAgentUrl("workspace", model),
    "/agents?workspace=workspace&model=ollama%3Aqwen3%3A8b",
  );
  assert.equal(server.allowedPath("models/workspace-access", "POST"), true);
  assert.equal(server.allowedPath("models/workspace-access", "GET"), false);
});

test("workload results show persisted calculations and scoped downloads", () => {
  const detail = codingDetail();
  detail.context.coding = false;
  detail.output.output = {
    kind: "report",
    summary: "Analyzed 3 rows from an isolated fixture.",
    analysis: {
      source: "fixture.csv",
      source_checksum: "a".repeat(64),
      row_count: 3,
      metrics: {
        revenue: {
          count: 3,
          missing: 0,
          sum: 75,
          mean: 25,
          median: 20,
          min: 10,
          max: 45,
          anomaly_count: 0,
        },
      },
      periods: [
        { label: "2026-01", value: 30, change: null, change_percent: null },
        { label: "2026-02", value: 45, change: 15, change_percent: 50 },
      ],
    },
    files: [{ filename: "report.html", media_type: "text/html" }],
    limitations: ["Deterministic calculations"],
  };
  const html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail }),
  );
  assert.match(html, /Analyzed 3 rows/);
  assert.match(html, /Supporting calculations/);
  assert.match(html, /Monthly values/);
  assert.match(html, /workloads\/jobs\/coding-fixture\/files\/artifact\/0/);
  assert.match(html, /Download report.html/);
  const id = "00000000-0000-0000-0000-000000000000";
  assert.equal(
    server.allowedPath(`workloads/jobs/${id}/files/${id}/0`, "GET"),
    true,
  );
  assert.equal(server.allowedPath("workloads/jobs", "POST"), true);
  assert.equal(server.allowedPath("workloads/options", "POST"), false);
  assert.equal(
    server.allowedPath(`workloads/jobs/${id}/files/${id}/../secret`, "GET"),
    false,
  );
});

function codingDetail(overrides = {}) {
  return {
    can_control: true,
    job: {
      id: "coding-fixture",
      type: "agent.workflow",
      status: "COMPLETED",
      input: { instruction: "Fix plugin compatibility" },
      result: { final_output: { id: "artifact", checksum: "a".repeat(64) } },
    },
    output: {
      output: {
        summary: "Updated the compatibility check.",
        diff: "diff --git a/plugin.php b/plugin.php\n--- a/plugin.php\n+++ b/plugin.php\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed: ["plugin.php"],
        base_commit: "b".repeat(40),
        tests: [
          {
            command: ["php", "tests.php"],
            exit_code: 0,
            output: "12 tests passed",
          },
        ],
      },
    },
    context: {
      agent_name: "Coding Agent",
      node_name: "My computer",
      apply_enabled: true,
    },
    workflow: { agent_version: 1 },
    attempts: [],
    steps: [],
    ...overrides,
  };
}

test("coding outcome leads with accomplishments and verified per-file evidence", () => {
  const html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail: codingDetail() }),
  );
  assert.ok(
    html.indexOf("Updated the compatibility check") <
      html.indexOf("Test evidence and source"),
  );
  for (const text of [
    "Fix plugin compatibility",
    "Run agent",
    "Preview changes",
    "Apply to my project",
    "plugin.php",
    "1 test command passed",
    "1 file changed",
    "Patch ready for review",
  ])
    assert.ok(html.includes(text), text);
  assert.match(html, /class="diff-added"/);
  assert.match(html, /class="diff-removed"/);
  assert.match(html, /disabled="">Apply to my project/);
  assert.deepEqual(
    outcomes
      .fileChanges(codingDetail().output.output.diff, ["plugin.php"])
      .map(({ path, additions, deletions }) => ({
        path,
        additions,
        deletions,
      })),
    [{ path: "plugin.php", additions: 1, deletions: 1 }],
  );
});

test("coding results distinguish produced, blocked, uncertain and actually applied changes", () => {
  for (const [status, state, expected] of [
    ["COMPLETED", "blocked", "Application blocked"],
    ["FAILED", null, "Application needs inspection"],
    ["RUNNING", null, "Applying changes"],
    ["COMPLETED", "applied", "Changes applied"],
  ]) {
    const html = renderToStaticMarkup(
      React.createElement(results.JobResult, {
        detail: codingDetail({
          result_action: {
            job_id: "action",
            status,
            result: state ? { state, summary: "Worker response" } : null,
          },
        }),
      }),
    );
    assert.ok(html.includes(expected));
    if (state !== "applied") assert.ok(!html.includes("Applied to project"));
  }
  const partial = codingDetail();
  partial.job.status = "FAILED";
  const html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail: partial }),
  );
  assert.match(html, /job has not completed/);
  assert.match(html, /disabled="">Apply to my project/);
});

test("coding tests are never invented and missing output is not a reference object", () => {
  const detail = codingDetail();
  detail.output.output.tests = [];
  let html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail }),
  );
  assert.match(html, /No tests were run/);
  detail.output.output.tests = [
    { command: ["test"], exit_code: 1, output: "failure" },
  ];
  html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail }),
  );
  assert.match(html, /0 test commands passed.*1 failed/);
  assert.match(html, /Tests need attention/);
  detail.job.status = "RUNNING";
  detail.output = {
    output: null,
    result: { final_output: { id: "reference-only" } },
  };
  html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail }),
  );
  assert.match(html, /No committed output is available yet/);
  assert.ok(!html.includes("reference-only"));
});

test("results retain image, report and analysis renderers without worker coupling", () => {
  const html = (value) =>
    renderToStaticMarkup(React.createElement(results.ReadableValue, { value }));
  assert.match(
    html({
      title: "Report",
      media_type: "application/pdf",
      base64: "Zml4dHVyZQ==",
    }),
    /Download report/,
  );
  assert.match(
    html({ title: "Image", media_type: "image/png", base64: "Zml4dHVyZQ==" }),
    /alt="Image"/,
  );
  assert.match(
    html({ title: "Analysis", columns: ["Value"], rows: [[42]] }),
    /<td>42<\/td>/,
  );
  assert.match(
    html({ title: "Chart", series: [{ label: "Sales", value: 42 }] }),
    /<svg/,
  );
  assert.equal(
    server.allowedPath(
      "jobs/00000000-0000-0000-0000-000000000000/result-actions",
      "POST",
    ),
    true,
  );
  assert.equal(
    server.allowedPath(
      "workers/00000000-0000-0000-0000-000000000000/jobs/00000000-0000-0000-0000-000000000000/result-action/begin",
      "POST",
    ),
    false,
  );
});

test("account provider bridge allows only scoped account operations", () => {
  assert.equal(server.allowedPath("account/providers", "GET"), true);
  assert.equal(server.allowedPath("account/providers/openai", "POST"), true);
  assert.equal(
    server.allowedPath("account/providers/anthropic/computers", "POST"),
    true,
  );
  assert.equal(
    server.allowedPath("account/providers/anthropic/disconnect", "POST"),
    true,
  );
  assert.equal(
    server.allowedPath("account/providers/openai/key", "GET"),
    false,
  );
  assert.equal(
    server.allowedPath("workers/fake/account-providers", "POST"),
    false,
  );
});

test("job results sanitize Markdown, disable tracking images and highlight code", () => {
  const html = renderToStaticMarkup(
    React.createElement(results.SafeMarkdown, {
      text: '# Answer\n<script>alert(1)</script>\n[unsafe](javascript:alert(1))\n![pixel](https://attacker.invalid/track)\n\n```python\nprint("hello")\n```',
    }),
  );
  assert.match(html, /<h1>Answer<\/h1>/);
  assert.ok(
    !html.includes("<script>") &&
      !html.includes('href="javascript:') &&
      !html.includes('src="https://attacker'),
  );
  assert.match(html, /hljs/);
  assert.match(html, /Copy/);
});

test("persisted answer is primary and partial output is never labeled completed", () => {
  const detail = {
    job: {
      id: "fixture",
      type: "inference.text",
      status: "RUNNING",
      result: null,
    },
    output: {
      valid: true,
      text: "Partial answer",
      metadata: {
        deployment: { identifier: "fixture-model" },
        usage: { duration_seconds: 2 },
      },
    },
    attempts: [],
    workflow: null,
  };
  const html = renderToStaticMarkup(
    React.createElement(results.JobResult, { detail }),
  );
  assert.match(html, /Partial answer/);
  assert.match(html, /job has not completed/);
  assert.match(html, /fixture-model/);
  assert.match(html, /Download partial output/);
  assert.ok(!html.includes("Authoritative result"));
});

test("provider management bridge has no secret upload endpoint", () => {
  assert.equal(server.allowedPath("provider-connections", "POST"), true);
  assert.equal(
    server.allowedPath(
      "provider-connections/00000000-0000-0000-0000-000000000000/policy",
      "POST",
    ),
    true,
  );
  assert.equal(server.allowedPath("provider-connections/keys", "POST"), false);
  assert.equal(
    server.allowedPath(
      "workers/00000000-0000-0000-0000-000000000000/provider-checks",
      "POST",
    ),
    false,
  );
});

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
  assert.match(html, /No invitation code is needed/);
  assert.match(html, /Tailscale is optional/);
  assert.match(html, /unavailable or not configured/);
  assert.ok(!html.includes("Administrator credential"));
});

test("invitation delivery describes manual sharing and provides usable instructions", () => {
  const html = renderToStaticMarkup(
    React.createElement(administration.InvitationDelivery, {
      invitation: {
        id: "fixture",
        email: "invited@example.invalid",
        roles: ["member"],
        expires_at: "2099-01-01T00:00:00Z",
        revoked: false,
        used_by: null,
      },
    }),
  );
  assert.match(html, /No email sent/);
  assert.match(html, /Copy sign-in instructions/);
  assert.ok(!html.includes("invitation_token"));
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
  assert.match(html, /Owned computers and credentials/);
  assert.match(html, /Consigliere downloads/);
  assert.match(
    html,
    /<details><summary>Advanced: manual command-line worker credential/,
  );
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
    process.env.GODFATHER_API_URL = "http://outside.invalid";
    assert.throws(() => server.apiBase());
    process.env.GODFATHER_API_URL = "https://selfhosted.example.invalid";
    assert.equal(server.apiBase(), "https://selfhosted.example.invalid");
  } finally {
    if (before === undefined) delete process.env.GODFATHER_API_URL;
    else process.env.GODFATHER_API_URL = before;
  }
});

test("self-hosted HTTPS uses the configured origin and still rejects foreign requests", () => {
  const before = process.env.GODFATHER_WEB_ORIGIN;
  try {
    process.env.GODFATHER_WEB_ORIGIN = "https://cluster.example.invalid";
    assert.equal(server.webOrigin(), "https://cluster.example.invalid");
    const request = (host, origin) => ({
      headers: new Headers({ host, origin }),
    });
    assert.equal(
      server.localRequest(
        request("cluster.example.invalid", "https://cluster.example.invalid"),
        true,
      ),
      true,
    );
    assert.equal(
      server.localRequest(
        request("cluster.example.invalid", "https://attacker.invalid"),
        true,
      ),
      false,
    );
    assert.equal(
      server.localRequest(
        request("attacker.invalid", "https://cluster.example.invalid"),
        true,
      ),
      false,
    );
  } finally {
    if (before === undefined) delete process.env.GODFATHER_WEB_ORIGIN;
    else process.env.GODFATHER_WEB_ORIGIN = before;
  }
});

test("bulk tables expose scoped eligible selection and workspace archive protection", () => {
  const bulk = require("../apps/dashboard/src/components/bulk-table.tsx");
  const archive = require("../apps/dashboard/src/components/workspace-delete.tsx");
  const html = renderToStaticMarkup(
    React.createElement(bulk.BulkTable, {
      kind: "jobs",
      scope: "workspace:0",
      rows: [
        { id: "done", state: "COMPLETED" },
        { id: "running", state: "RUNNING" },
      ],
      caption: "Jobs",
      rowKey: (j) => j.id,
      deleteKey: (j) => j.id,
      label: (j) => j.id,
      eligible: (j) => j.state === "COMPLETED",
      onDeleted: () => {},
      columns: [{ label: "Job", cell: (j) => j.id }],
    }),
  );
  assert.match(html, /Select all eligible jobs on this page/);
  assert.match(html, /aria-label="Select running" disabled/);
  assert.match(html, /0 selected on this page/);
  const dialog = renderToStaticMarkup(
    React.createElement(archive.WorkspaceDelete, {
      ids: ["workspace"],
      names: ["My workspace"],
      disabled: false,
      onDelete: async () => {},
    }),
  );
  assert.match(dialog, /Archive &amp; download/);
  assert.match(dialog, /Keep a copy before you go/);
  assert.match(dialog, /disabled="">Delete workspaces/);
  assert.match(dialog, /Automatic restore is not available/);
  assert.equal(
    server.allowedPath("administration/workspace-archive", "POST"),
    true,
  );
  assert.equal(
    server.allowedPath("administration/workspace-archive", "GET"),
    false,
  );
  assert.equal(server.allowedPath("administration/bulk-delete", "POST"), true);
  assert.equal(server.allowedPath("administration/bulk-delete", "GET"), false);
  const id = "00000000-0000-0000-0000-000000000000";
  assert.equal(
    server.allowedPath(`administration/workspaces/${id}/members/${id}`, "GET"),
    true,
  );
  assert.equal(
    server.allowedPath(`administration/workspaces/${id}/members/${id}`, "POST"),
    false,
  );
});

const identity = require("../apps/dashboard/src/components/node-identity.tsx");
const appearance = require("../apps/dashboard/src/lib/appearance.ts");
const appearanceUI = require("../apps/dashboard/src/components/appearance-settings.tsx");
test("worker build comparison uses semantic precedence and platform installers", () => {
  for (const [a, b, expected] of [
    ["0.4.1-rc.9", "0.4.1-rc.10", -1],
    ["0.4.1", "0.4.1-rc.10", 1],
    ["0.4.1+abc", "0.4.1+def", 0],
    ["0.10.0", "0.9.0", 1],
  ])
    assert.equal(Math.sign(identity.compareVersions(a, b)), expected);
  assert.equal(identity.compareVersions("unknown", "0.4.1"), null);
  const builds = identity.availableBuilds({
    artifacts: [
      {
        filename: "consigliere-0.4.1-rc.4-windows-x64-setup.exe",
        sha256: "a".repeat(64),
      },
      {
        filename: "consigliere-0.3.0-macos-arm64-installer.dmg",
        sha256: "a".repeat(64),
      },
    ],
  });
  assert.deepEqual(builds, {
    "windows-x86_64": "0.4.1-rc.4",
    "macos-arm64": "0.3.0",
  });
  assert.deepEqual(
    identity.availableBuilds({
      artifacts: [null, { filename: "untrusted.exe" }],
    }),
    {},
  );
});
test("owner is readable with full UUID on hover and keyboard focus", () => {
  const html = renderToStaticMarkup(
    React.createElement(identity.OwnerName, {
      node: { owner_name: "Brian", owner_id: "owner-uuid" },
    }),
  );
  assert.match(html, /Brian/);
  assert.match(html, /title="owner-uuid"/);
  assert.match(html, /tabindex="0"/);
  assert.match(html, /role="tooltip"/);
});
test("appearance defaults are accessible and bridge operations stay allowlisted", () => {
  assert.deepEqual(appearance.paletteErrors(appearance.defaults.light), []);
  assert.deepEqual(appearance.paletteErrors(appearance.defaults.dark), []);
  assert.ok(
    appearance.paletteErrors({
      ...appearance.defaults.light,
      foreground: "#ffffff",
    }).length,
  );
  assert.equal(server.allowedPath("appearance", "GET"), true);
  assert.equal(server.allowedPath("appearance", "POST"), true);
  assert.equal(server.allowedPath("appearance/arbitrary-css", "POST"), false);
  const html = renderToStaticMarkup(
    React.createElement(appearanceUI.AppearanceSettings),
  );
  assert.match(html, /Loading saved appearance/);
});

test("audit actor identity has a readable name and full UUID tooltip", () => {
  const html = renderToStaticMarkup(
    React.createElement(identity.UserName, {
      id: "actor-uuid",
      name: "Audit user",
    }),
  );
  assert.match(html, /Audit user/);
  assert.match(html, /title="actor-uuid"/);
  assert.match(html, /role="tooltip"/);
});

const distributed = require("../apps/dashboard/src/components/distributed-jobs.tsx");
test("distributed workload shows dependency edges, measured shares and unknown host telemetry", () => {
  const detail = {
    id: "test-job",
    final_task: "final",
    contribution_basis: "Share of recorded attempt execution time",
    nodes: [
      {
        id: "one",
        name: "Selected node",
        state: "offline",
        connection_status: "offline",
        last_heartbeat_at: null,
        execution_seconds: 10,
        contribution_percent: 100,
        resources: null,
      },
    ],
    tasks: [
      {
        key: "task1",
        name: "Independent work",
        job_id: "child1",
        depends_on: [],
        allowed_node_ids: ["one"],
        ready: true,
        status: "COMPLETED",
        assigned_node_id: null,
        attempt_count: 1,
        checkpoint_version: 1,
        model: { identifier: "local-model" },
      },
      {
        key: "final",
        name: "Combined answer",
        job_id: "child2",
        depends_on: ["task1"],
        allowed_node_ids: ["one"],
        ready: false,
        status: "PENDING",
        assigned_node_id: null,
        attempt_count: 0,
        checkpoint_version: 0,
        model: null,
      },
    ],
  };
  const html = renderToStaticMarkup(
    React.createElement(distributed.DistributedWorkload, { detail }),
  );
  assert.match(html, /marker-end="url/);
  assert.match(html, /Selected node/);
  assert.match(html, /100.0%/);
  assert.match(html, /Host CPU: Unknown/);
  assert.match(html, /WAITING FOR DEPENDENCIES/);
  assert.match(html, /not attributed to this job/);
  assert.match(html, /href="\/jobs\/child2"/);
});
test("distributed bridge and navigation retain explicit scoped operations", () => {
  const uuid = "00000000-0000-0000-0000-000000000001";
  for (const route of [
    "distributed/jobs",
    "distributed/jobs/options",
    `distributed/jobs/${uuid}`,
  ])
    assert.equal(server.allowedPath(route, "GET"), true);
  assert.equal(server.allowedPath("distributed/jobs", "POST"), true);
  assert.equal(
    server.allowedPath(`distributed/jobs/${uuid}/cancel`, "POST"),
    true,
  );
  assert.equal(
    server.allowedPath(`distributed/jobs/${uuid}/execute-shell`, "POST"),
    false,
  );
  assert.equal(
    server.allowedPath(`distributed/jobs/${uuid}/retry`, "POST"),
    false,
  );
  assert.equal(shell.navigation.distributed, "Distributed Jobs");
});

const notifications = require("../apps/dashboard/src/lib/notifications.ts");
const toasts = require("../apps/dashboard/src/components/toast-notifications.tsx");
const heartbeat = require("../apps/dashboard/src/components/node-heartbeat.tsx");
const sharedInference = require("../apps/dashboard/src/components/shared-inference-jobs.tsx");
test("toasts expose persistent errors, measured or indeterminate processing, type icons and dismissal", () => {
  for (const kind of ["error", "success", "notification", "processing"]) {
    const html = renderToStaticMarkup(
      React.createElement(toasts.ToastCard, {
        toast: { id: "test", kind, title: "Status", message: "Safe message" },
        dismiss: () => {},
      }),
    );
    assert.match(html, new RegExp(`toast-${kind}`));
    assert.match(html, /Dismiss Status/);
    assert.match(html, kind === "error" ? /role="alert"/ : /role="status"/);
    if (kind === "processing") {
      assert.match(html, /role="progressbar"/);
      assert.doesNotMatch(html, /aria-valuenow="/);
    }
  }
});
test("pending and error toasts have no expiry while success expires; duplicates do not stack", (context) => {
  const originalWindow = globalThis.window;
  globalThis.window = {};
  const delays = [];
  context.mock.method(globalThis, "setTimeout", (_fn, delay) => {
    delays.push(delay);
    return 1;
  });
  try {
    notifications.clearNotifications();
    notifications.notifyToast({
      id: "pending",
      kind: "processing",
      title: "Job",
      message: "Queued",
    });
    notifications.notifyToast({
      id: "pending",
      kind: "processing",
      title: "Job",
      message: "Running",
    });
    notifications.notifyError("Denied");
    notifications.notifyError("Denied");
    assert.equal(delays.length, 0);
    assert.equal(notifications.toastSnapshot().length, 2);
    notifications.notifyToast({
      id: "pending",
      kind: "success",
      title: "Job",
      message: "Completed",
    });
    assert.deepEqual(delays, [8000]);
    assert.equal(notifications.toastSnapshot().length, 2);
  } finally {
    notifications.clearNotifications();
    globalThis.window = originalWindow;
  }
});
test("heartbeat graph marks only an actual recent receipt and stops for stale or unknown data", () => {
  assert.equal(heartbeat.heartbeatPath(Infinity, true), "M0 14 H144");
  assert.equal(heartbeat.heartbeatPath(31, true), "M0 14 H144");
  assert.equal(heartbeat.heartbeatPath(1, false), "M0 14 H144");
  assert.notEqual(
    heartbeat.heartbeatPath(1, true),
    heartbeat.heartbeatPath(15, true),
  );
  const html = renderToStaticMarkup(
    React.createElement(heartbeat.NodeHeartbeat, {
      at: null,
      connection: "offline",
    }),
  );
  assert.match(html, /unknown.*offline/);
});
test("shared inference exposes all three distinct setups and both task and job navigation", () => {
  const html = renderToStaticMarkup(
    React.createElement(sharedInference.InferenceSetups, {
      mode: "single_host",
      select: () => {},
    }),
  );
  assert.match(html, /GPUs inside one computer/);
  assert.match(html, /fast local network/);
  assert.match(html, /across locations/);
  assert.equal(shell.navigation["distributed-tasks"], "Distributed Tasks");
  for (const path of [
    "distributed/tasks",
    "distributed/tasks/options",
    "shared-inference/jobs",
    "shared-inference/options",
  ])
    assert.equal(server.allowedPath(path, "GET"), true);
  assert.equal(server.allowedPath("shared-inference/jobs", "POST"), true);
  assert.equal(
    server.allowedPath("shared-inference/execute-shell", "POST"),
    false,
  );
});

const taskVariables = require("../apps/dashboard/src/lib/task-variables.ts");
test("task variables infer result dependencies and reject unknown, malformed or future outputs before posting", () => {
  assert.deepEqual(
    taskVariables.taskReferences(
      "Add 2+2 and {{tasks.task1.output}} for {{workspace.name}} / {{vars.project}}",
      ["task1"],
      ["project"],
    ),
    ["task1"],
  );
  for (const text of [
    "{{tasks.task2.output}}",
    "{{workspace.secret}}",
    "{{vars.missing}}",
    "{{workspace.name",
  ])
    assert.throws(() => taskVariables.taskReferences(text, ["task1"], []));
});

test("dashboard sources are valid UTF-8 without corrupted display characters", () => {
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const corrupted =
    /\u00c2[\u0080-\u00bf]|\u00c3[\u0080-\u00bf]|\u00e2[\u0080-\u00bf\u20ac\u2020]|\u00f0\u0178|[\u0080-\u009f\ufffd]/u;
  function inspect(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const filename = path.join(directory, entry.name);
      if (entry.isDirectory()) inspect(filename);
      else {
        const source = decoder.decode(fs.readFileSync(filename));
        assert.doesNotMatch(source, corrupted, filename);
      }
    }
  }
  inspect(path.join(__dirname, "../apps/dashboard/src"));
});

test("worker readiness distinguishes online state from configured image models", () => {
  const {
    WorkerAvailabilityList,
  } = require("../apps/dashboard/src/components/workloads.tsx");
  const nodes = [
    {
      id: "a",
      name: "Ready computer",
      available: true,
      analytics: true,
      image_models: ["Local XL", "Alternate model"],
    },
    {
      id: "b",
      name: "Needs setup",
      available: true,
      analytics: false,
      image_models: [],
    },
    {
      id: "c",
      name: "Disconnected computer",
      available: false,
      analytics: true,
      image_models: ["Installed offline model"],
    },
  ];
  const html = renderToStaticMarkup(
    React.createElement(WorkerAvailabilityList, { nodes, workflow: "images" }),
  );
  assert.match(html, /aria-label="Worker availability"/);
  assert.equal((html.match(/status-online/g) || []).length, 2);
  assert.match(html, /status-unavailable[^>]*>Unavailable/);
  assert.match(html, /Image model: Local XL/);
  assert.match(html, /Image model: Alternate model/);
  assert.match(html, /Image model: Installed offline model/);
  assert.match(html, /status-warning[^>]*>No image models/);
  assert.equal(
    (html.match(/class="worker-availability-row"/g) || []).length,
    3,
  );
  const analytics = renderToStaticMarkup(
    React.createElement(WorkerAvailabilityList, {
      nodes,
      workflow: "analytics",
    }),
  );
  assert.match(analytics, /Analytics configured/);
  assert.match(analytics, /Analytics unavailable/);
  assert.doesNotMatch(analytics, /Image model:/);
});

test("Bootstrap progress bars preserve measured zero and never invent unknown progress", () => {
  const {
    ProgressBar,
  } = require("../apps/dashboard/src/components/progress-bar.tsx");
  for (const [value, expected] of [
    [0, 0],
    [42, 42],
    [120, 100],
    [-5, 0],
  ]) {
    const html = renderToStaticMarkup(
      React.createElement(ProgressBar, { value, "aria-label": "Job progress" }),
    );
    assert.match(html, new RegExp('aria-valuenow="' + expected + '"'));
    assert.match(html, new RegExp("width:" + expected + "%"));
    assert.match(
      html,
      /progress-bar progress-bar-striped progress-bar-animated/,
    );
  }
  for (const value of [undefined, NaN]) {
    const html = renderToStaticMarkup(
      React.createElement(ProgressBar, { value, "aria-label": "Job progress" }),
    );
    assert.match(html, /Progress not reported/);
    assert.doesNotMatch(html, /aria-valuenow/);
  }
});

test("Bootstrap admin controls bind to validated shared settings and safe theme variables", () => {
  const {
    BootstrapSettings,
  } = require("../apps/dashboard/src/components/bootstrap-settings.tsx");
  const appearance = require("../apps/dashboard/src/lib/appearance.ts");
  const html = renderToStaticMarkup(
    React.createElement(BootstrapSettings, {
      draft: appearance.defaults,
      change() {},
      disabled: false,
    }),
  );
  for (const label of [
    "Button style",
    "Control size",
    "Panel shadow",
    "Toast position",
    "Progress bar height",
    "Striped progress bars",
    "Error / danger color",
  ])
    assert.ok(html.includes(label));
  const custom = {
    ...appearance.defaults,
    button_variant: "outline",
    toast_position: "top-start",
    progress_animated: false,
    table_hover: false,
    toast_width: 420,
  };
  const style = appearance.appearanceStyle(custom, "dark");
  assert.equal(style["--gf-button-bg"], "transparent");
  assert.equal(style["--gf-toast-top"], "16px");
  assert.equal(style["--gf-toast-right"], "auto");
  assert.equal(style["--gf-toast-width"], "420px");
  assert.equal(style["--gf-progress-animation"], "none");
  assert.equal(style["--gf-table-hover"], appearance.defaults.dark.card);
  const reduced = appearance.appearanceStyle(
    { ...appearance.defaults, reduced_motion: true },
    "light",
  );
  assert.equal(reduced["--gf-progress-animation"], "none");
  const legacySettings = { ...appearance.defaults };
  delete legacySettings.progress_height;
  const legacy = appearance.appearanceStyle(legacySettings, "light");
  assert.equal(legacy["--gf-progress-height"], "12px");
  assert.equal(legacy["--primary"], appearance.defaults.light.primary);
});
