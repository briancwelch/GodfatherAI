// Fixture API only: no real account, model calls, worker or database writes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);
const ts = require("typescript");
const appearance = { exports: {} };
new Function(
  "module",
  "exports",
  ts.transpileModule(
    fs.readFileSync("apps/dashboard/src/lib/appearance.ts", "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } },
  ).outputText,
)(appearance, appearance.exports);
const folder = path.resolve(".cache/usage-history/browser");
fs.mkdirSync(folder, { recursive: true });
const id = (n) => `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`;
const workspace = id(1),
  node = id(2),
  owner = id(3),
  completed = id(4),
  queued = id(5);
const now = "2026-10-25T12:00:00Z";
const events = { items: [], total: 0, offset: 0, limit: 25 };
const models = ["measured-model", "unknown-counters-model", "unused-model"].map(
  (identifier) => ({
    node_id: node,
    node_name: "Fixture worker",
    owner_id: owner,
    state: "online",
    available: true,
    deployment: {
      identifier,
      provider: "ollama",
      provider_id: "local",
      available: true,
      verified_capabilities: ["completion"],
      declared_capabilities: [],
      operations: ["chat"],
      context_window: 4096,
      estimated_ram_bytes: null,
      estimated_vram_bytes: null,
    },
  }),
);
const job = {
  id: completed,
  owner_id: owner,
  owner_name: "Fixture owner",
  workspace_id: workspace,
  type: "agent.workflow",
  status: "COMPLETED",
  priority: 0,
  assigned_node_id: null,
  current_attempt_id: id(6),
  attempt_count: 2,
  fencing_token: 2,
  checkpoint_ref: null,
  cancel_requested_at: null,
  next_run_at: null,
  requirements: {},
  result: {},
  created_at: now,
  retry: { limit: 1, backoff_seconds: 1 },
  execution: {
    attempt_id: id(6),
    attempt_number: 2,
    node_id: node,
    node_name: "Fixture worker",
    owner_id: owner,
    owner_name: "Fixture owner",
    can_inspect_node: false,
  },
};
const snapshot = {
  environment: "test",
  generated_at: now,
  actor_id: owner,
  workspace_id: workspace,
  workspaces: [
    {
      id: workspace,
      name: "Fixture workspace",
      owner_id: owner,
      can_manage: false,
    },
  ],
  nodes: [
    {
      node_id: node,
      name: "Fixture worker",
      owner_id: owner,
      owner_name: "Fixture owner",
      os: "windows",
      os_version: "fixture",
      architecture: "x86_64",
      state: "online",
      connection_status: "online",
      last_heartbeat_at: now,
      protocol_version: 1,
      scheduling_policy: "shared",
      concurrency_limit: 1,
      visible_active_jobs: 0,
      primary_capabilities: ["inference"],
      secondary_capabilities: [],
      runtimes: [],
      toolchains: [],
      dependencies: [],
      sandbox_modes: [],
      worker_tools: [],
      tool_permissions: [],
      installed_models: [],
      model_deployments: [],
      resources: {
        source: "physical",
        cpu_name: "Fixture CPU",
        cpu_count: 2,
        ram_bytes: 6 * 1024 ** 3,
        available_ram_bytes: 4 * 1024 ** 3,
        cpu_percent: 10,
        gpus: [],
        hardware: {
          cpu_count: 32,
          ram_bytes: 64 * 1024 ** 3,
          available_ram_bytes: 48 * 1024 ** 3,
          gpus: [
            {
              name: "Fixture GPU",
              backend: "cuda",
              memory_bytes: 24 * 1024 ** 3,
              memory_used_bytes: 0,
            },
          ],
        },
      },
    },
  ],
  jobs: [
    job,
    {
      ...job,
      id: queued,
      status: "PENDING",
      current_attempt_id: null,
      attempt_count: 0,
      execution: null,
    },
  ],
  models,
  node_counts: { online: 1 },
  job_counts: { COMPLETED: 1, PENDING: 1 },
  agent_counts: {
    enabled_versions: 0,
    disabled_versions: 0,
    active_versions: 0,
    compatible_online_versions: 0,
  },
  agents: [],
  events,
  capabilities: [],
  runtimes: [],
  toolchains: [],
  permissions: [],
  totals: { nodes: 1, jobs: 2, agents: 0 },
  limit: 25,
  offset: 0,
  metrics: {
    recent_attempts: [],
    recent_measurements: models.slice(0, 2).map((model, index) => ({
      measurement_id: id(10 + index),
      source: "workflow_step",
      attempt_id: id(6),
      job_id: completed,
      node_id: node,
      step_id: "answer",
      measured_at: now,
      deployment: model.deployment,
      usage: {
        duration_seconds: index ? 3 : 2,
        input_tokens: index ? null : 11,
        output_tokens: index ? null : 5,
        tokens_per_second: index ? null : 2.5,
        rate_source: index ? "unknown" : "provider_reported",
      },
    })),
  },
};
const mutations = [];
const server = http.createServer((req, res) => {
  const route = new URL(req.url, "http://localhost").pathname.replace(
    /^\/api\/v1\//,
    "",
  );
  let data;
  if (req.method !== "GET") mutations.push(`${req.method} ${route}`);
  if (route === "auth/me")
    data = { id: owner, display_name: "Fixture owner", roles: ["member"] };
  else if (route === "appearance") data = appearance.exports.defaults;
  else if (route === "command-center") data = snapshot;
  else if (route === `command-center/nodes/${node}`)
    data = {
      node: snapshot.nodes[0],
      can_control: false,
      jobs: snapshot.jobs,
      events,
    };
  else if (route === `command-center/jobs/${completed}`)
    data = {
      can_control: false,
      job,
      attempts: [],
      workflow: null,
      checkpoints: [],
      steps: [],
      events,
      output: null,
    };
  else {
    res.statusCode = 404;
    data = { detail: "Fixture route unavailable" };
  }
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(data));
});
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = "http://127.0.0.1:18368";
  const child = spawn(
    process.execPath,
    [
      path.resolve("node_modules/next/dist/bin/next"),
      "start",
      path.resolve("apps/dashboard"),
      "-p",
      "18368",
      "-H",
      "127.0.0.1",
    ],
    {
      stdio: "pipe",
      env: {
        ...process.env,
        GODFATHER_API_URL: `http://127.0.0.1:${server.address().port}`,
        GODFATHER_WEB_ORIGIN: origin,
      },
    },
  );
  const log = fs.createWriteStream(path.join(folder, "server.log"));
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Dashboard startup timeout")),
        30000,
      );
      child.stdout.on("data", (data) => {
        if (data.toString().includes("Ready in")) {
          clearTimeout(timer);
          resolve();
        }
      });
      child.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.once("exit", (code) => {
        clearTimeout(timer);
        reject(new Error(`Dashboard exited: ${code}`));
      });
    });
    browser = await chromium.launch({
      headless: true,
      ...(process.platform === "win32" ? { channel: "msedge" } : {}),
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1050 },
    });
    await context.addCookies([
      { name: "godfather_session", value: "x".repeat(43), url: origin },
    ]);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/downloads/manifest.json", (route) =>
      route.fulfill({ json: { artifacts: [] } }),
    );
    await page.goto(`${origin}/models`);
    const modelRow = (name) =>
      page
        .getByRole("row")
        .filter({ has: page.getByRole("button", { name, exact: true }) });
    await modelRow("measured-model").waitFor();
    assert.match(
      await modelRow("measured-model").innerText(),
      /2\.00s[\s\S]*11 input \/ 5 output tokens[\s\S]*2\.5 tokens\/s \(provider\)/,
    );
    assert.match(
      await modelRow("unknown-counters-model").innerText(),
      /3\.00s[\s\S]*Unknown input \/ Unknown output tokens[\s\S]*Unknown tokens\/s/,
    );
    assert.match(
      await modelRow("unused-model").innerText(),
      /No recent measurement/,
    );
    assert.equal(
      await modelRow("unknown-counters-model")
        .getByText("11 input / 5 output tokens")
        .count(),
      0,
    );
    await page.screenshot({
      path: path.join(folder, "models-desktop.png"),
      fullPage: true,
    });
    await page.goto(`${origin}/nodes`);
    const nodeRow = page
      .getByRole("row")
      .filter({ has: page.locator(`a[href="/nodes/${node}"]`) });
    await nodeRow.waitFor();
    assert.match(
      await nodeRow.innerText(),
      /Scheduling capacity: 2 CPUs.*6.0 GiB/,
    );
    assert.match(
      await nodeRow.innerText(),
      /Measured hardware:.*32 CPUs.*64.0 GiB/s,
    );
    assert.match(
      await nodeRow.innerText(),
      /Detected GPUs are not shared for scheduling/,
    );
    assert.doesNotMatch(await nodeRow.innerText(), /Physical report/);
    await page.screenshot({
      path: path.join(folder, "capacity-desktop.png"),
      fullPage: true,
    });
    await nodeRow.locator(`a[href="/nodes/${node}"]`).click();
    const ram = page
      .locator("dt")
      .filter({ hasText: /^RAM scheduling capacity$/ })
      .locator("+ dd");
    await ram.waitFor();
    assert.match(await ram.innerText(), /6.0 GiB limit.*4.0 GiB available/);
    assert.match(
      await page
        .locator("dt")
        .filter({ hasText: /^GPU \/ VRAM shared for scheduling$/ })
        .locator("+ dd")
        .innerText(),
      /No GPU shared for scheduling/,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await ram.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(folder, "capacity-mobile.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1050 });
    await page.goto(`${origin}/jobs`);
    const jobRow = (jobId) =>
      page
        .getByRole("row")
        .filter({ has: page.locator(`a[href="/jobs/${jobId}"]`) });
    await jobRow(completed).waitFor();
    assert.match(
      await jobRow(completed).innerText(),
      /Fixture worker[\s\S]*Owner[\s\S]*Fixture owner[\s\S]*Last attempt 2/,
    );
    assert.equal(
      await jobRow(completed).locator(`a[href="/nodes/${node}"]`).count(),
      0,
    );
    assert.match(await jobRow(queued).innerText(), /Not yet assigned/);
    await page.screenshot({
      path: path.join(folder, "jobs-desktop.png"),
      fullPage: true,
    });
    await jobRow(completed).locator(`a[href="/jobs/${completed}"]`).click();
    const execution = page
      .locator("dt")
      .filter({ hasText: /^Execution$/ })
      .locator("+ dd");
    await execution.waitFor();
    assert.match(
      await execution.innerText(),
      /Fixture worker[\s\S]*Owner[\s\S]*Fixture owner[\s\S]*Last attempt 2/,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await execution.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(folder, "job-mobile.png"),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(mutations, []);
    console.log(
      "Usage/history browser checks passed: exact model attribution, unknown counters, terminal execution, queued state, scoped links, job detail and mobile layout (fixture API).",
    );
  } finally {
    if (browser) await browser.close();
    child.kill();
    server.close();
    log.end();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
