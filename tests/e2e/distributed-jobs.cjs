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
  stale = false;
const nodes = [1, 2].map((i) => ({
  node_id: uuid(10 + i),
  name: `Test computer ${i}`,
  state: "online",
  connection_status: "online",
  context_supported: true,
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
      environment: "test",
      generated_at: new Date().toISOString(),
      workspace_id: workspace,
      workspaces: [{ id: workspace, name: "Test workspace", can_manage: true }],
      nodes: [],
      jobs: [],
      agents: [],
      models: [],
    };
  else if (route === "distributed/jobs/options")
    data = {
      nodes,
      agents,
      node_total: 2,
      agent_total: 2,
      node_offset: 0,
      agent_offset: 0,
      limit: 25,
    };
  else if (route === "distributed/jobs" && req.method === "POST") {
    submitted = JSON.parse(raw);
    res.statusCode = 201;
    data = summary();
  } else if (route === "distributed/jobs") {
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
  } else if (route === `distributed/jobs/${parent}`) data = detail();
  else if (route === `distributed/jobs/${parent}/cancel`) {
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
    await page.goto(`${origin}/distributed?workspace=${workspace}`);
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
        name: `Parallel task ${i + 1}`,
        exact: true,
      });
      await group
        .getByLabel("Agent / model")
        .selectOption(agents[i].version_id);
      await group
        .getByLabel("Task instructions")
        .fill(`Investigate part ${i + 1}`);
    }
    await page.getByLabel("Synthesis agent").selectOption(agents[0].version_id);
    await page
      .getByRole("checkbox", {
        name: /Allow any selected compatible updated computer/,
      })
      .check();
    await page
      .getByRole("button", { name: "Run distributed job", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Participating computers", exact: true })
      .waitFor();
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
      2,
    );
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
    parentStatus = "COMPLETED";
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByRole("heading", { name: "Combined answer", exact: true })
      .waitFor();
    assert.match(
      await page.locator(".distributed-output").innerText(),
      /Both selected computers/,
    );
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
      .getByRole("button", { name: "Cancel distributed job", exact: true })
      .waitFor();
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Cancel distributed job", exact: true })
      .click();
    await page
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
        .getByRole("button", { name: "Run distributed job", exact: true })
        .isDisabled(),
      true,
    );
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(folder, "result.json"),
      JSON.stringify(
        {
          passed: true,
          checks: [
            "selected-node submission",
            "parallel task assignments",
            "dependency graph",
            "time-share bars",
            "unknown telemetry",
            "durable final result renderer",
            "dark theme",
            "390px viewport",
            "confirmed cancellation",
            "stale controls",
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
