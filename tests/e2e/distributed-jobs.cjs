// Browser acceptance uses an isolated fixture API, never production or Google.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);
const folder = path.resolve(".cache/distributed-ui");
fs.mkdirSync(folder, { recursive: true });
const uuid = (n) => `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`;
const workspace = uuid(1),
  owner = uuid(2),
  agent = uuid(3),
  parent = uuid(4);
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
let submitted = null,
  parentStatus = "RUNNING",
  stale = false,
  rejection = null,
  posts = 0;
const nodes = [1, 2].map((i) => ({
  node_id: uuid(10 + i),
  name: `Test computer ${i}`,
  state: "online",
  connection_status: "online",
  context_supported: true,
  variables_supported: true,
  model_deployments: [{ identifier: `model-${i}`, available: true }],
}));
const agents = [1, 2].map((i) => ({
  id: agent,
  version_id: uuid(20 + i),
  version: i,
  enabled: true,
  definition: {
    name: `Model agent ${i}`,
    requirements: { model_selection: { identifier: `model-${i}` } },
    workflow: { steps: [{ kind: "model" }] },
  },
}));
const summary = () => ({
  id: parent,
  name: submitted?.name || "Fixture investigation",
  workspace_id: workspace,
  status: parentStatus,
  error: null,
  created_at: new Date().toISOString(),
});
const detail = () => ({
  ...summary(),
  instruction: submitted?.instruction || "Shared investigation",
  final_task: "final",
  generated_at: new Date().toISOString(),
  can_control: true,
  contribution_basis:
    "Share of recorded attempt execution time; not GPU usage or completion.",
  nodes: nodes.map((node, i) => ({
    id: node.node_id,
    name: node.name,
    state: i === 1 ? "offline" : "online",
    connection_status: i === 1 ? "offline" : "online",
    last_heartbeat_at: new Date().toISOString(),
    execution_seconds: i === 0 ? 90 : 10,
    contribution_percent: i === 0 ? 90 : 10,
    resources: i === 1 ? null : { cpu_percent: 24, gpus: [] },
  })),
  tasks: (submitted?.tasks || []).map((task, i) => ({
    ...task,
    job_id: uuid(30 + i),
    allowed_node_ids: task.node_ids,
    ready: i < 2 || parentStatus === "COMPLETED",
    status:
      parentStatus === "CANCELLED"
        ? "CANCELLED"
        : i < 2 || parentStatus === "COMPLETED"
          ? "COMPLETED"
          : "PENDING",
    assigned_node_id: i === 0 ? nodes[0].node_id : null,
    attempt_count: i < 2 ? 1 : 0,
    checkpoint_version: i < 2 ? 1 : 0,
    model: { identifier: `model-${(i % 2) + 1}` },
    result:
      i === 2 && parentStatus === "COMPLETED"
        ? { final_output: { id: uuid(40) } }
        : null,
  })),
});
let sharedSubmitted = null,
  sharedStatus = "RUNNING",
  nodeOffline = false;
const sharedId = uuid(90);
const inferenceGroups = ["single_host", "local_network", "wide_area"].map(
  (mode, index) => ({
    id: uuid(80 + index),
    name: `Inference group ${index + 1}`,
    mode,
    model: "shared-model",
    engine: "llama_cpp",
    parallelism: "pipeline",
    device_count: 2,
    available: true,
    reason: "Owner configured; physical performance unverified",
    computers: nodes.map((node) => ({ id: node.node_id, name: node.name })),
  }),
);
const sharedJob = () => ({
  id: sharedId,
  workspace_id: workspace,
  owner_id: owner,
  type: "inference.text",
  status: sharedStatus,
  created_at: new Date().toISOString(),
  input: { prompt: "Add 1+1" },
  requirements: {},
  result: sharedStatus === "COMPLETED" ? { text: "2" } : null,
});
const nodeInventory = () =>
  nodes.map((node) => ({
    ...node,
    owner_id: owner,
    owner_name: "Fixture owner",
    os: "windows",
    os_version: "Fixture",
    architecture: "x86_64",
    state: nodeOffline ? "offline" : "online",
    connection_status: nodeOffline ? "offline" : "online",
    last_heartbeat_at: new Date().toISOString(),
    protocol_version: 1,
    resources: {
      source: "physical",
      cpu_name: "Fixture CPU",
      cpu_count: 8,
      ram_bytes: 16000000000,
      gpus: [],
    },
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
  }));
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const route = url.pathname.replace(/^\/api\/v1\//, "");
  let raw = "";
  for await (const chunk of req) raw += chunk;
  res.setHeader("Content-Type", "application/json");
  let data;
  if (route === "auth/me")
    data = {
      id: owner,
      display_name: "Isolated test administrator",
      roles: ["platform_admin"],
    };
  else if (route === "appearance") data = appearance.exports.defaults;
  else if (route === "command-center")
    data = {
      actor_id: owner,
      environment: "test",
      generated_at: new Date().toISOString(),
      workspace_id: null,
      workspaces: [{ id: workspace, name: "Test workspace", can_manage: true }],
      nodes: url.searchParams.get("section") === "nodes" ? nodeInventory() : [],
      totals: { nodes: 2, jobs: 0, agents: 0 },
      limit: 25,
      offset: 0,
      jobs: [],
      agents: [],
      models: [],
    };
  else if (route === "shared-inference/options")
    data = { groups: inferenceGroups };
  else if (route === "shared-inference/jobs" && req.method === "POST") {
    sharedSubmitted = JSON.parse(raw);
    res.statusCode = 201;
    data = sharedJob();
  } else if (route === "shared-inference/jobs")
    data = {
      items: sharedSubmitted ? [sharedJob()] : [],
      total: sharedSubmitted ? 1 : 0,
      offset: 0,
      limit: 25,
    };
  else if (route === `command-center/jobs/${sharedId}`)
    data = {
      job: sharedJob(),
      attempts: [],
      steps: [],
      workflow: null,
      checkpoints: [],
      events: { items: [], total: 0 },
      output: {
        status: sharedStatus,
        valid: sharedStatus === "COMPLETED",
        text: sharedStatus === "COMPLETED" ? "2" : "",
        metadata: {},
      },
    };
  else if (route === "distributed/tasks/options")
    data = {
      nodes,
      agents,
      node_total: 2,
      agent_total: 2,
      node_offset: 0,
      agent_offset: 0,
      limit: 25,
    };
  else if (route === "distributed/tasks" && req.method === "POST") {
    posts += 1;
    if (rejection) {
      res.statusCode = rejection.status;
      res.end(JSON.stringify({ detail: rejection.detail }));
      return;
    }
    submitted = JSON.parse(raw);
    res.statusCode = 201;
    data = summary();
  } else if (route === "distributed/tasks") {
    if (stale) {
      res.statusCode = 503;
      data = { detail: "Isolated test outage" };
    } else
      data = {
        items: submitted ? [summary()] : [],
        total: submitted ? 1 : 0,
        offset: 0,
        limit: 25,
      };
  } else if (route === `distributed/tasks/${parent}`) data = detail();
  else if (route === `distributed/tasks/${parent}/cancel`) {
    parentStatus = "CANCELLED";
    data = summary();
  } else if (route === `workflow/jobs/${uuid(32)}/artifacts/${uuid(40)}`)
    data = {
      text: "# Combined answer\nBoth selected computers contributed evidence.",
    };
  else {
    res.statusCode = 404;
    data = { detail: "Fixture route unavailable" };
  }
  res.end(JSON.stringify(data));
});
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = "http://127.0.0.1:18365";
  const child = spawn(
    process.execPath,
    [
      path.resolve("node_modules/next/dist/bin/next"),
      "start",
      path.resolve("apps/dashboard"),
      "-p",
      "18365",
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
      child.on("error", reject);
    });
    browser = await chromium.launch({ headless: true, channel: "msedge" });
    const context = await browser.newContext({
      viewport: { width: 1500, height: 1050 },
    });
    await context.addCookies([
      { name: "godfather_session", value: "x".repeat(43), url: origin },
    ]);
    const page = await context.newPage(),
      errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/downloads/manifest.json", (route) =>
      route.fulfill({ json: { artifacts: [] } }),
    );
    await page.goto(`${origin}/distributed-tasks`);
    const run = page.getByRole("button", {
      name: "Run distributed tasks",
      exact: true,
    });
    await run.click();
    const feedback = page.locator(".submission-feedback");
    await feedback.getByText("Enter a job name.", { exact: true }).waitFor();
    assert.match(
      await feedback.innerText(),
      /Select at least two participating computers/,
    );
    assert.match(await feedback.innerText(), /Task 1: choose an agent/);
    assert.match(await feedback.innerText(), /Choose a synthesis agent/);
    assert.equal(posts, 0);
    assert.equal(
      await feedback.evaluate((element) => document.activeElement === element),
      true,
    );
    await feedback.screenshot({
      path: path.join(folder, "submission-blockers.png"),
    });
    // A selected old worker must explain the synthesis blocker beside Run.
    nodes.forEach((node) => {
      node.context_supported = false;
    });
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByText(/Test computer 1.*Worker update required for synthesis/)
      .waitFor();
    await page.getByRole("checkbox", { name: /Test computer 1/ }).check();
    await run.click();
    assert.match(
      await feedback.innerText(),
      /No selected computer supports final synthesis/,
    );
    assert.equal(posts, 0);
    nodes.forEach((node) => {
      node.context_supported = true;
    });
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByLabel("Synthesis computer")
      .locator("option")
      .filter({ hasText: "Test computer 1" })
      .waitFor({ state: "attached" });
    await page.getByRole("checkbox", { name: /Test computer 1/ }).check();
    await page.getByRole("checkbox", { name: /Test computer 2/ }).check();
    await page
      .getByLabel("Job name", { exact: true })
      .fill("Parallel browser acceptance");
    await page
      .getByLabel("Shared goal")
      .fill("Compare two independent investigations.");
    for (let i = 0; i < 2; i++) {
      const group = page.getByRole("group", {
        name: `Task ${i + 1} - task${i + 1}`,
        exact: true,
      });
      await group
        .getByLabel("Agent / model")
        .selectOption(agents[i].version_id);
      await group
        .getByLabel("Task instructions")
        .fill(`Investigate part ${i + 1}`);
    }
    await page.getByRole("button", { name: "Variables", exact: true }).click();
    await page.getByRole("region", { name: "Variable legend" }).waitFor();
    assert.match(
      await page.locator(".variable-popout").innerText(),
      /tasks.task1.output/,
    );
    await page.getByRole("button", { name: "Close variables" }).click();
    const secondTask = page.getByRole("group", {
      name: "Task 2 - task2",
      exact: true,
    });
    await secondTask
      .getByLabel("Task instructions")
      .fill("Add 2+2 then add {{tasks.task1.output}}");
    await page.getByLabel("Synthesis agent").selectOption(agents[0].version_id);
    await page
      .getByRole("checkbox", {
        name: /Allow any selected compatible updated computer/,
      })
      .check();
    rejection = {
      status: 403,
      detail:
        "Task participants require workspace access and node-owner contribution consent",
    };
    await run.click();
    await feedback.getByText(rejection.detail, { exact: true }).waitFor();
    await feedback.screenshot({
      path: path.join(folder, "submission-rejected.png"),
    });
    await page.locator(".corner-toasts .toast-error").first().waitFor();
    await page.evaluate(() => window.scrollTo(0, 0));
    assert.equal(await page.locator(".corner-toasts").isVisible(), true);
    await page
      .locator(".corner-toasts")
      .screenshot({ path: path.join(folder, "error-toast.png") });
    // Refreshing catalogs must not erase a failed submission's message.
    await Promise.all([
      page.waitForResponse((response) =>
        response.url().includes("distributed/tasks/options"),
      ),
      page.getByRole("button", { name: "Refresh", exact: true }).click(),
    ]);
    assert.match(await feedback.innerText(), /node-owner contribution consent/);
    rejection = {
      status: 422,
      detail: [
        {
          loc: ["body", "tasks", 0, "input", "instruction"],
          msg: "String should have at most 4096 characters",
          input: "PRIVATE INPUT MUST NOT APPEAR",
        },
      ],
    };
    await run.click();
    await feedback.getByText(/tasks > 0 > input > instruction/).waitFor();
    assert.doesNotMatch(await feedback.innerText(), /PRIVATE INPUT/);
    rejection = null;
    await page.route("**/api/control/distributed/tasks", (route) =>
      route.request().method() === "POST"
        ? route.abort("failed")
        : route.continue(),
    );
    await run.click();
    await feedback.getByText(/coordinator could not be reached/).waitFor();
    assert.match(
      await feedback.innerText(),
      /Refresh job history before retrying/,
    );
    await page.unroute("**/api/control/distributed/tasks");
    await page
      .getByRole("button", { name: "Run distributed tasks", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Participating computers", exact: true })
      .waitFor();
    await feedback.getByText("Submission confirmed", { exact: true }).waitFor();
    assert.equal(submitted.workspace_id, workspace);
    assert.equal(submitted.tasks.length, 3);
    assert.deepEqual(
      submitted.tasks[2].node_ids,
      nodes.map((node) => node.node_id),
    );
    assert.deepEqual(submitted.tasks[0].node_ids, [nodes[0].node_id]);
    assert.deepEqual(submitted.tasks[1].node_ids, [nodes[1].node_id]);
    assert.deepEqual(submitted.tasks[2].depends_on, ["task1", "task2"]);
    assert.equal(
      await page.locator(".distributed-network path[marker-end]").count(),
      3,
    );
    assert.deepEqual(submitted.tasks[1].depends_on, ["task1"]);
    await page.locator(".toast-processing progress").first().waitFor();
    assert.match(
      await page
        .getByRole("region", { name: "Node contribution", exact: true })
        .innerText(),
      /10.0%/,
    );
    assert.match(
      await page
        .getByRole("region", { name: "Node contribution", exact: true })
        .innerText(),
      /Unknown/,
    );
    await page.screenshot({
      path: path.join(folder, "desktop.png"),
      fullPage: true,
    });
    // Pending toasts outlive the notification duration; terminal state replaces them.
    await page.waitForTimeout(8500);
    assert.equal(await page.locator(".toast-processing progress").count(), 1);
    parentStatus = "COMPLETED";
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByRole("heading", { name: "Combined answer", exact: true })
      .waitFor();
    assert.match(
      await page.locator(".distributed-output").innerText(),
      /Both selected computers/,
    );
    await page
      .locator(".toast-success")
      .filter({ hasText: "Completed successfully" })
      .waitFor();
    await page.getByLabel("Theme", { exact: true }).selectOption("dark");
    await page.screenshot({
      path: path.join(folder, "dark.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: path.join(folder, "narrow.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1500, height: 1050 });
    parentStatus = "RUNNING";
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByRole("button", { name: "Cancel distributed tasks", exact: true })
      .waitFor();
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Cancel distributed tasks", exact: true })
      .click();
    await page
      .locator("main")
      .getByText("Cancellation confirmed. Committed results are retained.", {
        exact: true,
      })
      .waitFor();
    stale = true;
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByText(
        "Status is stale. Waiting for the API; controls are disabled.",
        { exact: true },
      )
      .waitFor();
    assert.equal(
      await page
        .getByRole("button", { name: "Run distributed tasks", exact: true })
        .isDisabled(),
      true,
    );
    stale = false;
    await page.goto(`${origin}/distributed`);
    await page
      .getByRole("heading", { name: "Distributed Jobs", exact: true })
      .waitFor();
    assert.equal(await page.getByRole("radio").count(), 3);
    await page
      .getByLabel("Computers across locations", { exact: false })
      .check();
    await page
      .getByLabel("Inference group")
      .selectOption(inferenceGroups[2].id);
    await page.getByLabel("Job prompt", { exact: true }).fill("Add 1+1");
    await page
      .getByRole("button", { name: "Run distributed job", exact: true })
      .click();
    await page
      .locator("main [role=alert]")
      .getByText(/Confirm sharing this prompt/)
      .waitFor();
    assert.equal(sharedSubmitted, null);
    await page.getByRole("checkbox", { name: /I confirm sharing/ }).check();
    await page
      .getByRole("button", { name: "Run distributed job", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Job information", exact: true })
      .waitFor();
    assert.equal(sharedSubmitted.wide_area_consent, true);
    await page.screenshot({
      path: path.join(folder, "shared-inference.png"),
      fullPage: true,
    });
    await page.reload();
    await page.locator(".toast-processing").first().waitFor();
    sharedStatus = "COMPLETED";
    await page
      .locator(".toast-success")
      .filter({ hasText: "Completed successfully" })
      .waitFor();
    await page.goto(`${origin}/nodes`);
    await page.locator(".node-heartbeat svg").first().waitFor();
    await page.waitForFunction(
      () =>
        document.querySelector(".node-heartbeat path")?.getAttribute("d") !==
        "M0 14 H144",
    );
    await page
      .locator(".node-heartbeat")
      .first()
      .screenshot({ path: path.join(folder, "heartbeat.png") });
    nodeOffline = true;
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector(".node-heartbeat path")?.getAttribute("d") ===
        "M0 14 H144",
    );
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(folder, "result.json"),
      JSON.stringify(
        {
          passed: true,
          checks: [
            "selected-node submission",
            "empty form validation without native silent blocking",
            "explicit synthesis readiness blockers",
            "permission rejection beside Run persists after refresh",
            "structured field validation without private input echo",
            "network failure with duplicate submission guidance",
            "default workspace fallback and confirmed submission",
            "parallel task assignments",
            "dependency graph",
            "time-share bars",
            "unknown telemetry",
            "durable final result renderer",
            "dark theme",
            "390px viewport",
            "confirmed cancellation",
            "stale controls",
            "named task result variables and inferred dependencies",
            "corner errors stay visible while scrolling",
            "processing toast survives eight seconds and becomes success",
            "three shared inference setup choices",
            "cross-location prompt consent before submission",
            "processing tracking restored after reload",
            "received and offline heartbeat EKG",
          ],
          pageErrors: errors,
        },
        null,
        2,
      ),
    );
    console.log(
      "Distributed Jobs browser acceptance passed (isolated fixture API).",
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
